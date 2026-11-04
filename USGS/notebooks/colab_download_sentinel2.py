# Download a Sentinel-2 L2A (surface reflectance) image from Google Earth Engine straight into Colab.
# No Drive. Output: /content/s2_scene.tif  (10 bands, int16, scale 1e-4, nodata -9999, 20 m, UTM)
import time, numpy as np, requests, ee, rasterio
from pathlib import Path
from rasterio.merge import merge

# ------------------------------- SETTINGS ------------------------------------
GEE_PROJECT = "ee-almohamadmohamad678"
WEST, SOUTH, EAST, NORTH = 34.9, 29.4, 35.1, 29.6     # area (degrees)
START, END, MAX_CLOUD = "2024-03-01", "2024-09-30", 10  # shorter period = lighter computation
TILE = 0.05                                            # tile size in degrees (~5 km)
BANDS = ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]
OUT = "/content/s2_scene.tif"
# ------------------------------------------------------------------------------

ee.Authenticate()
ee.Initialize(project=GEE_PROJECT)

region = ee.Geometry.Rectangle([WEST, SOUTH, EAST, NORTH])
col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
       .filterBounds(region).filterDate(START, END)
       .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD)))
n = col.size().getInfo()
print("scenes:", n)
if n == 0:
    raise SystemExit("No scenes: widen the dates or raise MAX_CLOUD.")

crs = col.first().select("B11").projection().crs().getInfo()     # UTM zone of the scenes
img = col.select(BANDS).median().unmask(-9999).toInt16().reproject(crs=crs, scale=20)


def download_tile(w, s, e, n_, path, tries=3):
    box = ee.Geometry.Rectangle([w, s, e, n_], proj="EPSG:4326", geodesic=False)
    for k in range(tries):
        url = img.getDownloadURL({"region": box, "scale": 20, "crs": crs, "format": "GEO_TIFF"})
        r = requests.get(url, timeout=600)
        if r.status_code == 200:
            Path(path).write_bytes(r.content)
            return
        print(f"  HTTP {r.status_code}: {r.text[:300]}")       # Earth Engine's real reason
        time.sleep(3 * (k + 1))
    raise RuntimeError(f"tile {path} failed; make TILE smaller or the period shorter")


paths = []
rows = np.arange(SOUTH, NORTH - 1e-9, TILE)
cols = np.arange(WEST, EAST - 1e-9, TILE)
for i, s in enumerate(rows):
    for j, w in enumerate(cols):
        p = f"/content/tile_{i}_{j}.tif"
        download_tile(w, s, min(w + TILE, EAST), min(s + TILE, NORTH), p)
        paths.append(p)
        print(f"tile {len(paths)}/{len(rows) * len(cols)} ok")

srcs = [rasterio.open(p) for p in paths]
mosaic, transform = merge(srcs, nodata=-9999)
meta = srcs[0].meta.copy()
meta.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform, nodata=-9999, count=mosaic.shape[0])
with rasterio.open(OUT, "w", **meta) as dst:
    dst.write(mosaic)
    dst.descriptions = tuple(BANDS)
for s_ in srcs:
    s_.close()
print(f"saved {OUT}: {mosaic.shape[2]} x {mosaic.shape[1]} px, {mosaic.shape[0]} bands, crs={crs}")

# quick look
import matplotlib.pyplot as plt
rgb = np.clip(np.moveaxis(mosaic[[2, 1, 0]].astype("float32"), 0, -1) * 1e-4 * 3.5, 0, 1)
plt.figure(figsize=(6, 6)); plt.imshow(rgb); plt.axis("off"); plt.title("Sentinel-2 RGB"); plt.show()
