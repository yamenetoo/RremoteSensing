# Download a Sentinel-2 L2A (surface reflectance) image from Google Earth Engine straight into Colab.
#   * tiles are downloaded in PARALLEL
#   * tiles already on disk are NOT downloaded again (re-run safely; resumes after a crash)
#   * result is shown on a CARTOPY map
# Output: /content/s2_scene.tif  (10 bands, int16, scale 1e-4, nodata -9999, 20 m, UTM)
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "-q", "install", "rasterio", "cartopy"], check=True)

import hashlib, json, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import ee, numpy as np, rasterio, requests
from rasterio.merge import merge

# ------------------------------- SETTINGS ------------------------------------
GEE_PROJECT = "ee-almohamadmohamad678"
WEST, SOUTH, EAST, NORTH = 34.9, 29.4, 35.1, 29.6     # area (degrees)
START, END, MAX_CLOUD = "2024-03-01", "2024-09-30", 10
TILE = 0.05              # tile size in degrees (~5 km)
WORKERS = 6              # parallel downloads (Earth Engine allows a limited number at once)
BANDS = ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]
OUT = "/content/s2_scene.tif"
# ------------------------------------------------------------------------------

# Tiles live in a folder named after the settings, so a re-run with the same settings reuses them
# and a run with different dates / area / bands never mixes old tiles in.
key = hashlib.md5(json.dumps([WEST, SOUTH, EAST, NORTH, START, END, MAX_CLOUD, TILE, BANDS]).encode()).hexdigest()[:10]
TILE_DIR = Path(f"/content/s2_tiles/{key}")
TILE_DIR.mkdir(parents=True, exist_ok=True)


def tile_ok(path: Path) -> bool:
    """True if the file exists and is a readable GeoTIFF with all bands."""
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with rasterio.open(path) as src:
            return src.count == len(BANDS)
    except Exception:
        return False


ee.Authenticate()
ee.Initialize(project=GEE_PROJECT)

region = ee.Geometry.Rectangle([WEST, SOUTH, EAST, NORTH])
col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
       .filterBounds(region).filterDate(START, END)
       .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD)))
n_scenes = col.size().getInfo()
print("scenes:", n_scenes)
if n_scenes == 0:
    raise SystemExit("No scenes: widen the dates or raise MAX_CLOUD.")

crs = col.first().select("B11").projection().crs().getInfo()     # UTM zone of the scenes
img = col.select(BANDS).median().unmask(-9999).toInt16().reproject(crs=crs, scale=20)


def download_tile(job, tries=3):
    i, j, w, s, e, n_ = job
    path = TILE_DIR / f"tile_{i}_{j}.tif"
    if tile_ok(path):
        return path, "cached"
    box = ee.Geometry.Rectangle([w, s, e, n_], proj="EPSG:4326", geodesic=False)
    last = ""
    for k in range(tries):
        try:
            url = img.getDownloadURL({"region": box, "scale": 20, "crs": crs, "format": "GEO_TIFF"})
            r = requests.get(url, timeout=600)
            if r.status_code == 200:
                tmp = path.with_suffix(".part")                  # write then rename: no half-written tiles
                tmp.write_bytes(r.content)
                os.replace(tmp, path)
                if tile_ok(path):
                    return path, "downloaded"
                last = "downloaded file is not a valid GeoTIFF"
            else:
                last = f"HTTP {r.status_code}: {r.text[:300]}"
        except Exception as exc:                                  # network / Earth Engine hiccup
            last = repr(exc)
        time.sleep(3 * (k + 1))
    raise RuntimeError(f"tile {path.name} failed: {last}")


ys = np.arange(SOUTH, NORTH - 1e-9, TILE)
xs = np.arange(WEST, EAST - 1e-9, TILE)
jobs = [(i, j, w, s, min(w + TILE, EAST), min(s + TILE, NORTH))
        for i, s in enumerate(ys) for j, w in enumerate(xs)]
print(f"{len(jobs)} tiles, {sum(tile_ok(TILE_DIR / f'tile_{j[0]}_{j[1]}.tif') for j in jobs)} already on disk")

paths, done, failed = [], 0, []
with ThreadPoolExecutor(max_workers=WORKERS) as pool:
    futs = {pool.submit(download_tile, job): job for job in jobs}
    for f in as_completed(futs):
        try:
            p, status = f.result()
            paths.append(p)
        except Exception as exc:
            failed.append((futs[f][:2], str(exc)))
            status = "FAILED"
        done += 1
        print(f"[{done}/{len(jobs)}] tile {futs[f][0]}_{futs[f][1]}: {status}")
if failed:
    for ij, msg in failed:
        print("  failed", ij, msg)
    raise RuntimeError(f"{len(failed)} tile(s) failed. Run this cell again: finished tiles are kept and skipped.")

# ----------------------------- mosaic -----------------------------------------
srcs = [rasterio.open(p) for p in sorted(paths)]
mosaic, transform = merge(srcs, nodata=-9999)
meta = srcs[0].meta.copy()
meta.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform, nodata=-9999, count=mosaic.shape[0])
for s_ in srcs:
    s_.close()
with rasterio.open(OUT, "w", **meta) as dst:
    dst.write(mosaic)
    dst.descriptions = tuple(BANDS)
print(f"saved {OUT}: {mosaic.shape[2]} x {mosaic.shape[1]} px, {mosaic.shape[0]} bands, crs={crs}")

# ----------------------------- cartopy map ------------------------------------
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt

with rasterio.open(OUT) as src:
    left, bottom, right, top = src.bounds
    epsg = src.crs.to_epsg()
if epsg and 32601 <= epsg <= 32660:
    proj = ccrs.UTM(epsg - 32600)
elif epsg and 32701 <= epsg <= 32760:
    proj = ccrs.UTM(epsg - 32700, southern_hemisphere=True)
else:
    proj = ccrs.PlateCarree()                                    # fallback for non-UTM grids
rgb = np.clip(np.moveaxis(mosaic[[2, 1, 0]].astype("float32"), 0, -1) * 1e-4 * 3.5, 0, 1)
rgb[(mosaic[[2, 1, 0]] == -9999).any(axis=0)] = np.nan          # nodata stays transparent

fig = plt.figure(figsize=(8, 8))
ax = plt.axes(projection=proj)
ax.imshow(rgb, origin="upper", extent=(left, right, bottom, top), transform=proj, interpolation="nearest")
ax.set_extent((left, right, bottom, top), crs=proj)
gl = ax.gridlines(draw_labels=True, linewidth=0.4, color="white", alpha=0.6, linestyle="--")
gl.top_labels = gl.right_labels = False
ax.add_feature(cfeature.BORDERS, linewidth=0.6, edgecolor="yellow")
ax.set_title(f"Sentinel-2 L2A median {START} to {END}  ({n_scenes} scenes)")
plt.show()
