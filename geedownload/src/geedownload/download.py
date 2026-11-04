"""Low-level Earth Engine work: build an image for an area, download it tile by tile, merge, stack."""
from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import requests

from . import grid
from .catalog import Dataset
from .errors import DownloadError, GeeDownloadError, NoImagesError
from .utils import file_size_mb, logger

REDUCERS = ("median", "mean", "min", "max", "sum", "mode", "first", "mosaic")


# ----------------------------------------------------------------------------- image building
def _s2_scl_mask(img):
    scl = img.select("SCL")
    bad = scl.eq(3).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10)).Or(scl.eq(11))
    return img.updateMask(bad.Not())


def _landsat_qa_mask(img):
    qa = img.select("QA_PIXEL")
    bad = qa.bitwiseAnd(1 << 1).neq(0).Or(qa.bitwiseAnd(1 << 3).neq(0)).Or(qa.bitwiseAnd(1 << 4).neq(0))
    return img.updateMask(bad.Not())


_MASKS = {"s2_scl": _s2_scl_mask, "landsat_qa": _landsat_qa_mask}


def asset_kind(ds: Dataset) -> str:
    if ds.kind:
        return ds.kind
    import ee

    t = ee.data.getAsset(ds.collection_id).get("type", "")
    return "image" if t == "IMAGE" else "collection"


def filter_collection(ds: Dataset, region, start, end, cloud_max):
    import ee

    col = ee.ImageCollection(ds.collection_id).filterBounds(region)
    if start and end:
        col = col.filterDate(start, end)
    elif start:
        col = col.filterDate(start, "2100-01-01")
    if ds.cloud_property and cloud_max is not None:
        col = col.filter(ee.Filter.lt(ds.cloud_property, cloud_max))
    for prop, val in ds.filters:
        col = col.filter(ee.Filter.eq(prop, val))
    return col


def apply_scale_factors(img, ds: Dataset):
    names = img.bandNames().getInfo()
    import re

    for rule in ds.scale_factors:
        hit = [n for n in names if re.fullmatch(rule["pattern"], n)]
        if hit:
            scaled = img.select(hit).multiply(rule["mult"]).add(rule["add"])
            img = img.addBands(scaled, None, True)
    return img


def resolve_bands(ds: Dataset, requested, available: Sequence[str]) -> List[str]:
    if requested in (None, "default"):
        wanted = list(ds.default_bands) if ds.default_bands else list(available)
    elif requested == "all":
        wanted = list(available)
    else:
        wanted = ds.expand_bands([requested] if isinstance(requested, str) else list(requested))
    missing = [b for b in wanted if b not in available]
    if missing:
        raise GeeDownloadError(f"Band(s) {missing} not in {ds.collection_id}. Available: {list(available)}")
    return wanted


def build_composite(ds: Dataset, region, start=None, end=None, cloud_max: Optional[float] = 20,
                    reducer: Optional[str] = None, mask_clouds: bool = False):
    """Return (image, n_images, available_bands) for the dataset over `region` (ee.Geometry)."""
    import ee

    if asset_kind(ds) == "image":
        img = ee.Image(ds.collection_id)
        return img, 1, img.bandNames().getInfo()
    col = filter_collection(ds, region, start, end, cloud_max)
    n = col.size().getInfo()
    if n == 0:
        raise NoImagesError(
            f"No {ds.collection_id} images for this area / dates / cloud<{cloud_max}. "
            "Widen the date range or raise cloud_max.")
    bands = col.first().bandNames().getInfo()
    if mask_clouds:
        fn = _MASKS.get(ds.cloud_mask or "")
        if fn is None:
            logger.warning("No cloud mask available for %s; skipping.", ds.key)
        else:
            col = col.map(fn)
    red = (reducer or ds.reducer).lower()
    if red not in REDUCERS:
        raise GeeDownloadError(f"reducer must be one of {REDUCERS}")
    return getattr(col, red)(), n, bands


def detect_scale(ds: Dataset, image, band: str) -> float:
    if ds.scale:
        return float(ds.scale)
    return float(image.select(band).projection().nominalScale().getInfo())


# ----------------------------------------------------------------------------- downloading
def _fetch(url: str, dest: Path, retries: int = 4, timeout: int = 300) -> Path:
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code != 200:
                raise DownloadError(f"HTTP {r.status_code}: {r.text[:300]}")
            data = r.content
            if data[:4] == b"PK\x03\x04":   # zipped GeoTIFF(s)
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    tif = next(n for n in zf.namelist() if n.lower().endswith((".tif", ".tiff")))
                    data = zf.read(tif)
            dest.write_bytes(data)
            return dest
        except (requests.RequestException, DownloadError, StopIteration) as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise DownloadError(f"Download failed after {retries} attempts: {last}")


def merge_tiles(tile_paths: Sequence[Path], out_path: Path) -> Path:
    import rasterio
    from rasterio.merge import merge

    if len(tile_paths) == 1:
        Path(tile_paths[0]).replace(out_path)
        return out_path
    srcs = [rasterio.open(p) for p in tile_paths]
    try:
        mosaic, transform = merge(srcs)
        profile = srcs[0].profile.copy()
        profile.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform, compress="deflate")
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(mosaic)
    finally:
        for s in srcs:
            s.close()
    for p in tile_paths:
        Path(p).unlink(missing_ok=True)
    return out_path


def download_band(image, band: str, region_bbox, out_path: Path, scale: float, crs: str,
                  max_tile_px: int = 1500, clip_geometry=None) -> Path:
    """Download one band over `region_bbox` (lon/lat) to a GeoTIFF, tiling large areas automatically."""
    import ee

    step = grid.step_in_crs_units(scale, crs)
    bounds = grid.snap_bounds(grid.project_bbox(region_bbox, crs), step)
    tiles = grid.make_tiles(bounds, step, max_tile_px)
    img = image.select([band])
    if clip_geometry is not None:
        img = img.clip(clip_geometry)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    parts: List[Path] = []
    for i, tb in enumerate(tiles):
        region = ee.Geometry.Rectangle(list(tb), proj=crs, geodesic=False)
        url = img.getDownloadURL({"region": region, "crs": crs, "crs_transform": grid.crs_transform(tb, step),
                                  "format": "GEO_TIFF"})
        part = out_path.with_suffix(f".part{i}.tif") if len(tiles) > 1 else out_path
        _fetch(url, part)
        parts.append(part)
    if len(parts) > 1:
        merge_tiles(parts, out_path)
    return out_path


def download_bands(image, bands: Sequence[str], region_bbox, folder_for_band, prefix: str, scale: float,
                   crs: str, max_tile_px: int = 1500, clip_geometry=None) -> Dict[str, Path]:
    """Download several bands; `folder_for_band(band) -> Path`. Failed bands are logged and skipped."""
    out: Dict[str, Path] = {}
    for b in bands:
        path = Path(folder_for_band(b)) / f"{prefix}_{b}.tif"
        try:
            download_band(image, b, region_bbox, path, scale, crs, max_tile_px, clip_geometry)
            out[b] = path
            logger.info("  ok  %-14s %.1f MB", b, file_size_mb(path))
        except Exception as exc:  # keep going so one bad band does not lose the rest
            logger.warning("  FAIL %s: %s", b, exc)
    return out


def stack_bands(band_files: Dict[str, Path], out_path: Path) -> Path:
    """Combine single-band GeoTIFFs (same grid) into one multi-band GeoTIFF with band names."""
    import numpy as np
    import rasterio

    names = list(band_files)
    srcs = [rasterio.open(band_files[n]) for n in names]
    try:
        shapes = {(s.height, s.width) for s in srcs}
        if len(shapes) != 1:
            raise GeeDownloadError(f"Bands have different grids {shapes}; cannot stack.")
        dtype = np.result_type(*[np.dtype(s.dtypes[0]) for s in srcs])
        profile = srcs[0].profile.copy()
        profile.update(count=len(srcs), dtype=str(dtype), compress="deflate")
        with rasterio.open(out_path, "w", **profile) as dst:
            for i, (n, s) in enumerate(zip(names, srcs), start=1):
                dst.write(s.read(1).astype(dtype), i)
                dst.set_band_description(i, n)
    finally:
        for s in srcs:
            s.close()
    return Path(out_path)
