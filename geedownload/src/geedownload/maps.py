"""Publication-style maps with cartopy: satellite rasters or area outlines, saved as JPG/PNG.

Every map has: lat/lon grid with degree labels, scale bar, north arrow, legend (or colour bar),
the area boundary, optional country / state borders, and an optional inset showing where the
area lies inside its country.

Needs the optional extras:  pip install "geedownload[maps]"
Country borders and coastlines come from Natural Earth (downloaded once by cartopy). If they cannot be
downloaded (offline), the map is still drawn without those layers.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple, Union

import numpy as np
from shapely.geometry import box, mapping
from shapely.geometry.base import BaseGeometry

from .aoi import AOI, aoi_from_place, resolve_aoi
from .errors import AreaNotFound, GeeDownloadError
from .geocode import search_area
from .utils import logger

# value -> (label, hex colour) for categorical products
CLASS_LEGENDS: Dict[str, Dict[int, Tuple[str, str]]] = {
    "worldcover": {
        10: ("Tree cover", "#006400"), 20: ("Shrubland", "#ffbb22"), 30: ("Grassland", "#ffff4c"),
        40: ("Cropland", "#f096ff"), 50: ("Built-up", "#fa0000"), 60: ("Bare / sparse", "#b4b4b4"),
        70: ("Snow and ice", "#f0f0f0"), 80: ("Water", "#0064c8"), 90: ("Herbaceous wetland", "#0096a0"),
        95: ("Mangroves", "#00cf75"), 100: ("Moss and lichen", "#fae6a0"),
    },
    "dynamic_world": {
        0: ("Water", "#419bdf"), 1: ("Trees", "#397d49"), 2: ("Grass", "#88b053"),
        3: ("Flooded vegetation", "#7a87c6"), 4: ("Crops", "#e49635"), 5: ("Shrub and scrub", "#dfc35a"),
        6: ("Built area", "#c4281b"), 7: ("Bare ground", "#a59b8f"), 8: ("Snow and ice", "#b39fe1"),
    },
}

_NICE_STEPS = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 30]
# The legend (below the map) and the country inset (right of the map) are ALWAYS outside the map frame,
# so they never hide any data.
_INSET_BOUNDS = {"right": [1.03, 0.60, 0.34, 0.38]}
_ne_cache: Dict[tuple, bool] = {}


def _require_maps():
    try:
        import cartopy.crs as ccrs  # noqa: F401
        import matplotlib  # noqa: F401
    except ImportError as exc:
        raise ImportError('Maps need extra packages: pip install "geedownload[maps]"') from exc


# ----------------------------------------------------------------------------- country / admin areas
def _ne_records(name: str, resolution: str):
    import cartopy.io.shapereader as shpreader

    path = shpreader.natural_earth(resolution=resolution, category="cultural", name=name)
    return list(shpreader.Reader(path).records())


@lru_cache(maxsize=32)
def country_aoi(country: str, admin1: Optional[str] = None, resolution: str = "10m") -> AOI:
    """Boundary of a country (or of a state/province inside it) as an AOI.

    Uses Natural Earth through cartopy; if that is unavailable (offline) it falls back to a
    Nominatim search restricted to countries / states.  ``country_aoi("Syria")``,
    ``country_aoi("Syria", admin1="Hama")``.
    """
    _require_maps()
    key = country.strip().lower()
    try:
        recs = _ne_records("admin_0_countries", resolution)

        def names(r):
            keys = ("NAME", "NAME_LONG", "ADMIN", "NAME_EN", "SOVEREIGNT", "ISO_A2", "ISO_A3", "ABBREV", "FORMAL_EN")
            return {str(r.attributes.get(k, "")).lower() for k in keys}

        hit = [r for r in recs if key in names(r)] or [r for r in recs if any(key in n for n in names(r) if len(n) > 3)]
        if hit:
            rec = hit[0]
            geom, label = rec.geometry, rec.attributes.get("NAME_LONG") or country
            if admin1:
                akey = admin1.strip().lower()
                admin = str(rec.attributes.get("ADMIN", "")).lower()
                subs = [s for s in _ne_records("admin_1_states_provinces", resolution)
                        if str(s.attributes.get("admin", "")).lower() == admin
                        and akey in {str(s.attributes.get(k, "")).lower() for k in ("name", "name_en", "name_local")}]
                if not subs:
                    raise AreaNotFound(f"'{admin1}' not found in {label} (Natural Earth).")
                from shapely.ops import unary_union

                geom, label = unary_union([s.geometry for s in subs]), f"{admin1}, {label}"
            return AOI(label, geom, label, "natural_earth")
    except AreaNotFound:
        raise
    except Exception as exc:  # offline / download blocked -> fall back to OSM
        logger.info("Natural Earth unavailable (%s); using Nominatim for the country boundary.", type(exc).__name__)
    query = f"{admin1}, {country}" if admin1 else country
    place = search_area(query, limit=3, feature_type="state" if admin1 else "country")[0]
    return aoi_from_place(place)


def _infer_country(aoi: AOI) -> Optional[str]:
    if aoi.source == "search" and "," in aoi.display_name:
        return aoi.display_name.split(",")[-1].strip()
    return None


# ----------------------------------------------------------------------------- helpers
def _nice_step(span_deg: float, target_lines: int = 5) -> float:
    raw = span_deg / target_lines
    return next((s for s in _NICE_STEPS if s >= raw), _NICE_STEPS[-1])


def _ne_available(category: str, name: str, resolution: str) -> bool:
    key = (category, name, resolution)
    if key not in _ne_cache:
        try:
            import warnings

            import cartopy.io.shapereader as shpreader

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                shpreader.natural_earth(resolution=resolution, category=category, name=name)
            _ne_cache[key] = True
        except Exception:
            _ne_cache[key] = False
            logger.warning("Natural Earth layer '%s' (%s) unavailable - drawn without it.", name, resolution)
    return _ne_cache[key]


def _add_context(ax, resolution: str, admin1: bool = False) -> set:
    """Add Natural Earth layers that are available; returns the set of layer names actually drawn."""
    import cartopy.feature as cfeature

    specs = [
        ("physical", "ocean", dict(facecolor="#d6e8f5", edgecolor="none", zorder=0)),
        ("physical", "land", dict(facecolor="#f4f1ea", edgecolor="none", zorder=0)),
        ("physical", "coastline", dict(facecolor="none", edgecolor="#555555", linewidth=0.6, zorder=3)),
        ("cultural", "admin_0_boundary_lines_land", dict(facecolor="none", edgecolor="#222222", linewidth=1.0,
                                                          linestyle="--", zorder=3)),
    ]
    if admin1:
        specs.append(("cultural", "admin_1_states_provinces_lines",
                      dict(facecolor="none", edgecolor="#777777", linewidth=0.5, zorder=3)))
    drawn = set()
    for category, name, style in specs:
        if _ne_available(category, name, resolution):
            ax.add_feature(cfeature.NaturalEarthFeature(category, name, resolution, **style))
            drawn.add(name)
    return drawn


def _add_grid(ax, extent, step: Optional[float]) -> None:
    import cartopy.crs as ccrs
    import matplotlib.ticker as mticker
    from cartopy.mpl.ticker import LatitudeFormatter, LongitudeFormatter

    w, e, s, n = extent
    step = step or _nice_step(max(e - w, n - s))
    dec = max(0, -int(math.floor(math.log10(step))))
    fmt = f".{dec}f"
    gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True, linewidth=0.6, color="gray", alpha=0.7, linestyle="--")
    gl.top_labels = gl.right_labels = False
    gl.xlocator = mticker.FixedLocator(np.arange(math.floor(w / step) * step, e + step, step))
    gl.ylocator = mticker.FixedLocator(np.arange(math.floor(s / step) * step, n + step, step))
    gl.xformatter = LongitudeFormatter(number_format=fmt, degree_symbol="°")
    gl.yformatter = LatitudeFormatter(number_format=fmt, degree_symbol="°")
    gl.xlabel_style = gl.ylabel_style = {"size": 8}
    ax.text(0.5, -0.09, "Longitude", transform=ax.transAxes, ha="center", va="top", fontsize=9)
    ax.text(-0.11, 0.5, "Latitude", transform=ax.transAxes, ha="right", va="center", rotation=90, fontsize=9)


def _add_scalebar(ax, extent) -> None:
    import cartopy.crs as ccrs
    import matplotlib.patheffects as pe
    from matplotlib.patches import Rectangle

    w, e, s, n = extent
    km_per_deg = 111.32 * math.cos(math.radians((s + n) / 2))
    target = (e - w) * km_per_deg * 0.2
    nice = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000]
    length = max([k for k in nice if k <= target] or [nice[0]])
    deg = length / km_per_deg
    x0, y0, h = e - 0.05 * (e - w) - deg, s + 0.06 * (n - s), 0.012 * (n - s)
    pc = ccrs.PlateCarree()
    ax.add_patch(Rectangle((x0, y0), deg / 2, h, fc="k", ec="k", transform=pc, zorder=10))
    ax.add_patch(Rectangle((x0 + deg / 2, y0), deg / 2, h, fc="w", ec="k", transform=pc, zorder=10))
    halo = [pe.withStroke(linewidth=2.5, foreground="white")]
    for dx, txt in ((0, "0"), (deg / 2, f"{length / 2:g}"), (deg, f"{length:g} km")):
        ax.text(x0 + dx, y0 - 0.012 * (n - s), txt, transform=pc, ha="center", va="top", fontsize=8,
                zorder=11, path_effects=halo)


def _add_north_arrow(ax) -> None:
    ax.annotate("N", xy=(0.95, 0.96), xytext=(0.95, 0.84), xycoords="axes fraction", textcoords="axes fraction",
                ha="center", va="bottom", fontsize=12, fontweight="bold", zorder=12,
                arrowprops=dict(facecolor="black", width=4, headwidth=11, headlength=12))


def _add_inset(ax, country_geom: BaseGeometry, area_bbox, label: str, loc: str) -> None:
    import cartopy.crs as ccrs

    pc = ccrs.PlateCarree()
    ins = ax.inset_axes(_INSET_BOUNDS[loc], projection=pc)
    ins.set_zorder(20)
    cw, cs, ce, cn = country_geom.bounds[0], country_geom.bounds[1], country_geom.bounds[2], country_geom.bounds[3]
    padx, pady = 0.1 * (ce - cw), 0.1 * (cn - cs)
    ins.set_extent([cw - padx, ce + padx, cs - pady, cn + pady], crs=pc)
    ins.add_geometries([country_geom], pc, facecolor="#cfe3c4", edgecolor="#444444", linewidth=0.6)
    w, s, e, n = area_bbox
    min_w, min_h = 0.03 * (ce - cw), 0.03 * (cn - cs)           # keep tiny areas visible
    cx, cy = (w + e) / 2, (s + n) / 2
    rw, rh = max(e - w, min_w), max(n - s, min_h)
    ins.add_geometries([box(cx - rw / 2, cy - rh / 2, cx + rw / 2, cy + rh / 2)], pc,
                       facecolor="red", edgecolor="red", alpha=0.6, linewidth=1)
    ins.set_title(label, fontsize=7, pad=2)


def _read_wgs84(path, band_idx: Sequence[int], max_px: int, nodata, clip_geom: Optional[BaseGeometry]):
    """Warp selected bands of a GeoTIFF to lon/lat. Returns (arrays, (w, e, s, n))."""
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.warp import Resampling, calculate_default_transform, reproject

    with rasterio.open(path) as src:
        if src.crs is None:
            raise GeeDownloadError(f"{path} has no CRS; cannot map it.")
        dst_crs = "EPSG:4326"
        tr, w, h = calculate_default_transform(src.crs, dst_crs, src.width, src.height, *src.bounds)
        f = max(w, h) / max_px
        if f > 1:
            tr, w, h = calculate_default_transform(src.crs, dst_crs, src.width, src.height, *src.bounds,
                                                   dst_width=max(1, int(w / f)), dst_height=max(1, int(h / f)))
        nd = nodata if nodata is not None else src.nodata
        arrays = []
        for i in band_idx:
            dst = np.full((h, w), np.nan, dtype="float32")
            reproject(rasterio.band(src, i), dst, src_transform=src.transform, src_crs=src.crs,
                      src_nodata=nd, dst_transform=tr, dst_crs=dst_crs, dst_nodata=np.nan,
                      resampling=Resampling.nearest)
            arrays.append(dst)
    if clip_geom is not None:
        inside = geometry_mask([mapping(clip_geom)], out_shape=(h, w), transform=tr, invert=True)
        for a in arrays:
            a[~inside] = np.nan
    left, top = tr.c, tr.f
    return arrays, (left, left + w * tr.a, top + h * tr.e, top)


def _band_indexes(path, bands) -> Tuple[list, list]:
    import rasterio

    with rasterio.open(path) as src:
        desc = [d or f"band{i + 1}" for i, d in enumerate(src.descriptions)]
        count = src.count
    if bands is None:
        bands = [1]
    elif isinstance(bands, (str, int)):
        bands = [bands]
    idx, labels = [], []
    for b in bands:
        if isinstance(b, int):
            if not 1 <= b <= count:
                raise GeeDownloadError(f"Band index {b} out of range 1..{count}")
            idx.append(b)
        else:
            low = [d.lower() for d in desc]
            if str(b).lower() not in low:
                raise GeeDownloadError(f"Band '{b}' not in {path}. Available: {desc}")
            idx.append(low.index(str(b).lower()) + 1)
        labels.append(desc[idx[-1] - 1])
    return idx, labels


def _stretch(a: np.ndarray, lo: float, hi: float, vmin=None, vmax=None):
    valid = a[np.isfinite(a)]
    if valid.size == 0:
        return np.zeros_like(a), 0.0, 1.0
    vmin = np.percentile(valid, lo) if vmin is None else vmin
    vmax = np.percentile(valid, hi) if vmax is None else vmax
    if vmax <= vmin:
        vmax = vmin + 1e-9
    return np.clip((a - vmin) / (vmax - vmin), 0, 1), float(vmin), float(vmax)


def _colorize_classes(a: np.ndarray, classes: Dict[int, Tuple[str, str]]) -> np.ndarray:
    from matplotlib.colors import to_rgba

    rgba = np.zeros(a.shape + (4,), dtype="float32")
    for value, (_, color) in classes.items():
        rgba[a == value] = to_rgba(color)
    return rgba


def _save(fig, out_path, dpi: int) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    is_jpg = out.suffix.lower() in (".jpg", ".jpeg")
    fig.savefig(out, dpi=dpi, format="jpeg" if is_jpg else None, facecolor="white", bbox_inches="tight",
                **({"pil_kwargs": {"quality": 95}} if is_jpg else {}))
    return out


# ----------------------------------------------------------------------------- public API
def preview_args(info: dict) -> dict:
    """Sensible `plot_map` arguments (bands / classes / colour map) for a finished download.

    `info` is the metadata dict of `download_area` (``DownloadResult.info`` or ``metadata.json``).
    """
    bands, key = list(info.get("bands") or []), info.get("dataset_key", "")
    if key in CLASS_LEGENDS:
        return {"bands": bands[:1], "classes": key}
    for rgb in (["B4", "B3", "B2"], ["SR_B4", "SR_B3", "SR_B2"], ["sur_refl_b01", "sur_refl_b04", "sur_refl_b03"]):
        if all(b in bands for b in rgb):
            return {"bands": rgb}
    cmap = "RdYlGn" if bands[:1] in (["NDVI"], ["EVI"]) else "terrain" if bands[:1] in (["elevation"], ["DEM"]) else "viridis"
    return {"bands": bands[:1] or None, "cmap": cmap}


def plot_map(raster=None, out_path="map.jpg", *, area=None, bands=None, cmap: str = "viridis",
             vmin: Optional[float] = None, vmax: Optional[float] = None, stretch: Tuple[float, float] = (2, 98),
             classes: Union[None, str, Dict[int, Tuple[str, str]]] = None, title: Optional[str] = None,
             legend_label: Optional[str] = None, source: Optional[str] = None, country: Optional[str] = None,
             admin1: bool = False, context: bool = True, inset: bool = True, inset_loc: str = "right",
             extent: str = "area", grid_step: Optional[float] = None, mask_to_area: bool = True,
             boundary_color: str = "red", nodata: Optional[float] = None, dpi: int = 200,
             figsize: Tuple[float, float] = (10, 8), max_px: int = 2500, pad: float = 0.12, show: bool = False) -> Path:
    """Draw a map and save it as JPG (or PNG, from the file extension).

    raster   GeoTIFF path (e.g. the ``*_stack.tif`` from ``download_area``); None = outline-only map of `area`
    area     place name / AOI / bbox / shapefile for the boundary overlay (default: the raster extent)
    bands    None = band 1; one name/index = single band with colour bar; three = RGB composite, e.g. ["B4","B3","B2"]
    classes  "worldcover" / "dynamic_world" or {value: (label, "#hex")} for categorical rasters (legend patches)
    country  country name for the border context and the inset (default: guessed from a place search)
    The legend / colour bar is drawn below or beside the map and the country inset to its right: both are
    always outside the map frame (`inset_loc` only accepts "right").
    extent   when raster is None: "area" (zoom to the area) or "country" (show the whole country)
    """
    _require_maps()
    import cartopy.crs as ccrs
    import matplotlib

    matplotlib.use("Agg")          # file output only; never open a Tk window (maps are drawn in worker threads)
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    if inset_loc not in _INSET_BOUNDS:
        raise GeeDownloadError(f"inset_loc must be one of {sorted(_INSET_BOUNDS)} (the inset stays outside the map).")
    pc = ccrs.PlateCarree()
    aoi = resolve_aoi(area) if area is not None else None
    arrays, labels, img_extent = [], [], None
    if raster is not None:
        idx, labels = _band_indexes(raster, bands)
        arrays, img_extent = _read_wgs84(raster, idx, max_px, nodata, aoi.geometry if (aoi and mask_to_area) else None)
        if aoi is None:
            w, e, s, n = img_extent
            aoi = AOI(Path(str(raster)).stem, box(w, s, e, n), source="raster")
    elif aoi is None:
        raise GeeDownloadError("Give a raster, an area, or both.")

    country_aoi_obj = None
    if inset or extent == "country" or context:
        cname = country or _infer_country(aoi)
        if cname and (inset or extent == "country"):
            try:
                country_aoi_obj = country_aoi(cname, resolution="50m")
            except Exception as exc:
                logger.warning("Country boundary for '%s' unavailable (%s); inset skipped.", cname, exc)

    # map extent
    if img_extent is not None:
        w, e, s, n = img_extent
        padx, pady = 0.02 * (e - w), 0.02 * (n - s)
        w, e, s, n = w - padx, e + padx, s - pady, n + pady
    elif extent == "country" and country_aoi_obj is not None:
        w, s, e, n = country_aoi_obj.bbox
        w, e, s, n = w - 0.03 * (e - w), e + 0.03 * (e - w), s - 0.03 * (n - s), n + 0.03 * (n - s)
    else:
        w, s, e, n = aoi.bbox
        side = max(e - w, n - s, 0.01)
        w, e, s, n = w - pad * side, e + pad * side, s - pad * side, n + pad * side

    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(1, 1, 1, projection=pc)
    ax.set_extent([w, e, s, n], crs=pc)
    drawn_layers: set = set()
    if context:
        span = e - w
        drawn_layers = _add_context(ax, "110m" if span > 40 else "50m" if span > 4 else "10m", admin1)

    handles = []
    if arrays:
        iextent = [img_extent[0], img_extent[1], img_extent[2], img_extent[3]]
        if classes is not None:
            table = CLASS_LEGENDS[classes] if isinstance(classes, str) else classes
            ax.imshow(_colorize_classes(arrays[0], table), origin="upper", extent=iextent, transform=pc,
                      interpolation="nearest", zorder=2)
            present = set(np.unique(arrays[0][np.isfinite(arrays[0])]).astype(int).tolist())
            handles += [Patch(facecolor=c, edgecolor="#444444", label=lab) for v, (lab, c) in table.items() if v in present]
        elif len(arrays) == 3:
            chans = [_stretch(a, *stretch)[0] for a in arrays]
            rgba = np.dstack(chans + [np.where(np.isfinite(arrays[0]), 1.0, 0.0)]).astype("float32")
            rgba[..., :3] = np.nan_to_num(rgba[..., :3])
            ax.imshow(rgba, origin="upper", extent=iextent, transform=pc, interpolation="nearest", zorder=2)
            handles += [Patch(facecolor=c, label=f"{lab}") for c, lab in zip(("#d62728", "#2ca02c", "#1f77b4"), labels)]
        elif len(arrays) == 1:
            _, lo, hi = _stretch(arrays[0], *stretch, vmin, vmax)
            im = ax.imshow(np.ma.masked_invalid(arrays[0]), origin="upper", extent=iextent, transform=pc,
                           cmap=cmap, vmin=lo, vmax=hi, interpolation="nearest", zorder=2)
            outside_inset = inset and country_aoi_obj is not None and inset_loc == "right"
            cb = fig.colorbar(im, ax=ax, shrink=0.5 if outside_inset else 0.75, pad=0.07,
                              anchor=(0.0, 0.0) if outside_inset else (0.0, 0.5))
            cb.set_label(legend_label or labels[0], fontsize=9)
        else:
            raise GeeDownloadError("Choose 1 band (colour bar) or 3 bands (RGB).")
    else:
        ax.add_geometries([aoi.geometry], pc, facecolor=boundary_color, alpha=0.25, edgecolor="none", zorder=2)

    ax.add_geometries([aoi.geometry], pc, facecolor="none", edgecolor=boundary_color, linewidth=1.6, zorder=6)
    handles.insert(0, Line2D([0], [0], color=boundary_color, lw=2, label=f"{aoi.name} boundary"))
    if "admin_0_boundary_lines_land" in drawn_layers:
        handles.append(Line2D([0], [0], color="#222222", lw=1, ls="--", label="International border"))
    if "admin_1_states_provinces_lines" in drawn_layers:
        handles.append(Line2D([0], [0], color="#777777", lw=0.8, label="State / province border"))

    _add_grid(ax, (w, e, s, n), grid_step)
    _add_scalebar(ax, (w, e, s, n))
    _add_north_arrow(ax)
    leg_title = "Legend" if classes is None else (legend_label or "Classes")
    ncol = min(len(handles), 4)
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=ncol, fontsize=8,
              title=leg_title, title_fontsize=9, framealpha=0.95, fancybox=False, edgecolor="#444444")
    if inset and country_aoi_obj is not None:
        _add_inset(ax, country_aoi_obj.geometry, aoi.bbox, country_aoi_obj.name.split(",")[-1].strip(), inset_loc)
    ax.set_title(title or aoi.name, fontsize=13, fontweight="bold", pad=10)
    foot = [t for t in (source, "Coordinate system: WGS 84 (EPSG:4326), degrees") if t]
    rows = math.ceil(len(handles) / ncol)
    ax.text(0.0, -0.24 - 0.05 * rows, " | ".join(foot), transform=ax.transAxes, fontsize=7, color="#555555",
            ha="left", va="top")

    out = _save(fig, out_path, dpi)
    if show:
        plt.show()
    plt.close(fig)
    logger.info("Map saved: %s", out)
    return out


def plot_area(area, out_path="area_map.jpg", *, country: Optional[str] = None, extent: str = "area", **kwargs) -> Path:
    """Outline-only map of an area (name / country / shapefile / bbox) with grid, borders and country inset.

    ``plot_area("Syria", extent="country")`` maps a whole country; ``plot_area("Masyaf, Syria")`` zooms to the
    area and shows where it sits in Syria in the inset.
    """
    return plot_map(None, out_path, area=area, country=country, extent=extent, **kwargs)
