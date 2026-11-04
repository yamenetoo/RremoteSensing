"""High-level API: search an area by name, save its shapefile, download satellite data for it."""
from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import __version__, grid
from .aoi import AOI, buffer_aoi, resolve_aoi
from .auth import init_ee
from .boundary import save_boundary, to_ee_geometry
from .catalog import get_dataset
from .errors import GeeDownloadError
from .maps import _infer_country
from .download import (apply_scale_factors, build_composite, detect_scale, download_bands, filter_collection,
                       resolve_bands, stack_bands, _MASKS)
from .utils import logger, slugify, timestamp, zip_dir


@dataclass
class DownloadResult:
    folder: Path
    shapefile: Path
    band_files: Dict[str, Path] = field(default_factory=dict)
    stack: Optional[Path] = None
    scenes: List[Path] = field(default_factory=list)
    metadata: Optional[Path] = None
    zip: Optional[Path] = None
    info: dict = field(default_factory=dict)


def download_area(area, dataset="sentinel2", start: Optional[str] = None, end: Optional[str] = None, *,
                  out_dir=".", bands=None, cloud_max: Optional[float] = 20, reducer: Optional[str] = None,
                  scale: Optional[float] = None, crs: Optional[str] = None, clip: bool = True,
                  mask_clouds: bool = False, apply_scale: bool = False, per_image: bool = False,
                  max_images: int = 10, stack: bool = True, keep_band_files: bool = True,
                  zip_output: bool = False, buffer_m: float = 0, pick: int = 0, name: Optional[str] = None,
                  project: Optional[str] = None, max_tile_px: int = 1500,
                  max_area_km2: Optional[float] = None) -> DownloadResult:
    """Find `area`, save its boundary as a shapefile and download `dataset` imagery covering it.

    area       place name ("Masyaf, Syria"), shapefile/GeoJSON path, (w, s, e, n) bbox, shapely geometry, AOI or Place
    dataset    registry key (see `list_datasets()`: sentinel2, landsat8, modis_ndvi, srtm ...) or any EE asset id
    bands      None = dataset defaults/all, "all", band names or group names (e.g. "10m_bands")
    per_image  True = download each scene separately (up to `max_images`) instead of one composite
    clip       True = pixels outside the true boundary polygon are masked (bbox is always the file extent)
    apply_scale  convert to physical units (reflectance 0-1, Kelvin ...) -> float32 files
    max_area_km2 refuse areas whose bounding box is larger than this (protects servers / quotas)
    """
    ds = get_dataset(dataset)
    aoi: AOI = buffer_aoi(resolve_aoi(area, pick=pick, name=name), buffer_m)
    if max_area_km2:
        x0, y0, x1, y1 = grid.project_bbox(aoi.bbox, grid.utm_crs_for(*aoi.centroid))
        km2 = (x1 - x0) * (y1 - y0) / 1e6
        if km2 > max_area_km2:
            raise GeeDownloadError(f"Area bounding box is {km2:,.0f} km2, above the limit of {max_area_km2:,.0f} km2.")
    init_ee(project)
    stem = f"{slugify(aoi.name)}_{ds.key}_{timestamp()}"
    folder = Path(out_dir) / stem
    folder.mkdir(parents=True, exist_ok=True)

    shp = save_boundary(aoi, folder / "boundary")
    ee_geom = to_ee_geometry(aoi.geometry)
    bbox = aoi.bbox
    crs = crs or grid.utm_crs_for(*aoi.centroid)
    clip_geom = ee_geom if clip and aoi.source != "bbox" else None

    logger.info("Area: %s | bbox=%s | dataset=%s | crs=%s", aoi.display_name or aoi.name, tuple(round(v, 4) for v in bbox), ds.collection_id, crs)
    result = DownloadResult(folder=folder, shapefile=shp)

    image, n_img, available = build_composite(ds, ee_geom, start, end, cloud_max, reducer, mask_clouds)
    chosen = resolve_bands(ds, bands, available)
    if apply_scale:
        image = apply_scale_factors(image, ds)
    px_scale = scale or detect_scale(ds, image, chosen[0])
    rows, cols = grid.grid_shape(grid.snap_bounds(grid.project_bbox(bbox, crs), grid.step_in_crs_units(px_scale, crs)),
                                 grid.step_in_crs_units(px_scale, crs))
    logger.info("%d image(s) -> %d band(s), %dx%d px at %g m", n_img, len(chosen), cols, rows, px_scale)

    bands_dir = folder / "bands"
    folder_for = lambda b: bands_dir / ds.group_of(b)
    prefix = slugify(aoi.name)

    if not per_image:
        files = download_bands(image, chosen, bbox, folder_for, prefix, px_scale, crs, max_tile_px, clip_geom)
        if not files:
            raise RuntimeError("No band could be downloaded; see the warnings above.")
        result.band_files = files
        if stack:
            result.stack = stack_bands(files, folder / f"{prefix}_{ds.key}_stack.tif")
        if not keep_band_files and result.stack:
            for p in files.values():
                p.unlink(missing_ok=True)
            result.band_files = {}
    else:
        import ee

        col = filter_collection(ds, ee_geom, start, end, cloud_max).sort("system:time_start")
        ids = col.limit(max_images).aggregate_array("system:index").getInfo()
        mask_fn = _MASKS.get(ds.cloud_mask or "") if mask_clouds else None
        for sid in ids:
            scene = ee.Image(f"{ds.collection_id}/{sid}")
            if mask_fn:
                scene = mask_fn(scene)
            if apply_scale:
                scene = apply_scale_factors(scene, ds)
            sdir = folder / "scenes" / sid.replace("/", "_")
            files = download_bands(scene, chosen, bbox, lambda b: sdir, prefix, px_scale, crs, max_tile_px, clip_geom)
            if files:
                result.scenes.append(stack_bands(files, folder / "scenes" / f"{prefix}_{sid.replace('/', '_')}.tif"))
                for p in files.values():
                    p.unlink(missing_ok=True)
                if not any(sdir.glob("*")):
                    sdir.rmdir()

    result.info = {
        "area": aoi.name, "display_name": aoi.display_name, "bbox_lonlat": list(bbox), "dataset": ds.collection_id,
        "dataset_key": ds.key, "country": _infer_country(aoi), "author": "M. Yamen AL-Mohamad",
        "start": start, "end": end, "cloud_max": cloud_max, "reducer": reducer or ds.reducer,
        "mask_clouds": mask_clouds, "apply_scale": apply_scale, "bands": chosen, "scale_m": px_scale, "crs": crs,
        "n_source_images": n_img, "grid_px": [cols, rows], "per_image": per_image, "clipped_to_boundary": clip_geom is not None,
        "package": f"geedownload {__version__}", "python": platform.python_version(),
    }
    result.metadata = folder / "metadata.json"
    result.metadata.write_text(json.dumps(result.info, indent=2, ensure_ascii=False), encoding="utf-8")
    if zip_output:
        result.zip = zip_dir(folder, folder.with_suffix(".zip"))
    logger.info("Done: %s", folder)
    return result


def search_and_save(query: str, out_dir=".", pick: int = 0, name: Optional[str] = None, **search_kwargs) -> Path:
    """Search an area by name and save its boundary shapefile (no Earth Engine needed)."""
    aoi = resolve_aoi(query, pick=pick, name=name, **search_kwargs)
    return save_boundary(aoi, out_dir)
