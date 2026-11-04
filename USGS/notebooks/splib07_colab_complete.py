# =============================================================================
# Mineral mapping from Sentinel-2 with the USGS Spectral Library v7  (Google Colab, one cell)
# 1) install  2) download + build USGS library  3) download Sentinel-2 from Earth Engine
# 4) match every pixel to the library  5) maps + CSV + GeoTIFF
# Edit only the SETTINGS block, then run.
# =============================================================================
# ------------------------------- SETTINGS ------------------------------------
GEE_PROJECT = "ee-almohamadmohamad678"
WEST, SOUTH, EAST, NORTH = 34.9, 29.4, 35.1, 29.6      # area of interest (degrees)
START, END, MAX_CLOUD = "2024-01-01", "2024-12-31", 10
TILE = 0.05              # download tile size in degrees (smaller = safer)
CHAPTERS = "MS"          # USGS chapters: M minerals, S soils (add V for vegetation, C coatings...)
MAX_ANGLE = 10.0         # reject pixels whose best spectral angle (deg) is larger
TOP_CLASSES = 12         # how many materials get their own colour on the map
USE_DRIVE_CACHE = True   # keep the built library in Google Drive so it is not rebuilt next time
# ------------------------------------------------------------------------------

import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "-q", "install",
                "git+https://github.com/yamenetoo/RremoteSensing.git#subdirectory=USGS",
                "rasterio", "matplotlib", "tqdm"], check=True)

from pathlib import Path
import numpy as np, matplotlib.pyplot as plt, requests, rasterio, ee
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
from rasterio.merge import merge
from usgs_splib07 import Image, SpectralLibrary, build_library, download_splib07, match_image

# ------------------------- 1) USGS spectral library ---------------------------
if USE_DRIVE_CACHE:
    from google.colab import drive
    drive.mount("/content/drive")
    WORK = Path("/content/drive/MyDrive/splib07")
else:
    WORK = Path("/content/splib07")
WORK.mkdir(parents=True, exist_ok=True)
cache = WORK / f"splib07_{CHAPTERS}_vnir_swir.npz"
if cache.exists():
    lib = SpectralLibrary.load(cache)
else:
    root = download_splib07(WORK)
    lib = build_library(root, library="splib07b", chapters=CHAPTERS, kinds=("AREF",),
                        start=350, stop=2500, step=5)
    lib.save(cache)
print(lib)

# ----------------------- 2) Sentinel-2 from Earth Engine ----------------------
ee.Authenticate()
ee.Initialize(project=GEE_PROJECT)
BANDS = ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]
region = ee.Geometry.Rectangle([WEST, SOUTH, EAST, NORTH])
col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")           # surface reflectance (L2A)
       .filterBounds(region).filterDate(START, END)
       .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD)))
print("scenes:", col.size().getInfo())
crs = col.first().select("B11").projection().crs().getInfo()
img = col.select(BANDS).median().unmask(-9999).toInt16().reproject(crs=crs, scale=20)


def download_tile(w, s, e, n, path):
    box = ee.Geometry.Rectangle([w, s, e, n], proj="EPSG:4326", geodesic=False)
    url = img.getDownloadURL({"region": box, "scale": 20, "crs": crs, "format": "GEO_TIFF"})
    r = requests.get(url, timeout=600)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
    Path(path).write_bytes(r.content)


paths = []
for i, s in enumerate(np.arange(SOUTH, NORTH - 1e-9, TILE)):
    for j, w in enumerate(np.arange(WEST, EAST - 1e-9, TILE)):
        p = f"/content/tile_{i}_{j}.tif"
        download_tile(w, s, min(w + TILE, EAST), min(s + TILE, NORTH), p)
        paths.append(p)
srcs = [rasterio.open(p) for p in paths]
mosaic, transform = merge(srcs, nodata=-9999)
meta = srcs[0].meta.copy()
meta.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform, nodata=-9999)
IMG_PATH = "/content/s2_scene.tif"
with rasterio.open(IMG_PATH, "w", **meta) as dst:
    dst.write(mosaic)
for s_ in srcs:
    s_.close()
print(f"image: {mosaic.shape[2]} x {mosaic.shape[1]} px, {mosaic.shape[0]} bands")

# --------------------------------- 3) match ----------------------------------
image = Image.read(IMG_PATH, sensor="sentinel2a", band_names=BANDS, scale=1e-4, offset=0.0, nodata=-9999)
res = match_image(image, lib, group_by="material", max_angle_deg=MAX_ANGLE, mask_vegetation=0.4)
counts = res.counts()
print(counts.head(15).to_string(index=False))
confident = (res.angle_deg < 6) & (res.margin_deg > 1.0) & (res.class_map >= 0)
print(f"confident pixels (angle<6 deg, margin>1 deg): {confident.mean():.1%}")

# --------------------------------- 4) maps -----------------------------------
top = list(counts["label"].head(TOP_CLASSES))
colors = plt.get_cmap("tab20")(np.linspace(0, 1, 20))[:TOP_CLASSES]
lookup = {name: k for k, name in enumerate(top)}
idx = np.full(res.class_map.shape, -1)
names = np.array(res.labels, dtype=object)
valid = res.class_map >= 0
idx[valid] = [lookup.get(n, TOP_CLASSES) for n in names[res.class_map[valid]]]   # TOP_CLASSES = "other"
cmap = ListedColormap(list(colors) + [(0.75, 0.75, 0.75, 1)])

rgb_i = [image.band_names.index(b) for b in ("B4", "B3", "B2")]
rgb = np.clip(np.moveaxis(np.nan_to_num(image.data[rgb_i]), 0, -1) * 3.5, 0, 1)

fig, ax = plt.subplots(1, 4, figsize=(22, 5.5))
ax[0].imshow(rgb); ax[0].set_title("Sentinel-2 RGB")
ax[1].imshow(np.ma.masked_less(idx, 0), cmap=cmap, vmin=0, vmax=TOP_CLASSES, interpolation="nearest")
ax[1].set_title("best-matching material")
a = ax[2].imshow(res.angle_deg, cmap="viridis_r", vmin=0, vmax=MAX_ANGLE)
ax[2].set_title("spectral angle (deg, low = good)"); plt.colorbar(a, ax=ax[2], fraction=0.046)
ax[3].imshow(np.ma.masked_where(~confident, idx), cmap=cmap, vmin=0, vmax=TOP_CLASSES, interpolation="nearest")
ax[3].set_title("confident matches only")
for x in ax:
    x.set_xticks([]); x.set_yticks([])
fig.legend(handles=[Patch(color=colors[k], label=n) for k, n in enumerate(top)] + [Patch(color=(0.75,) * 3, label="other")],
           loc="lower center", ncol=min(7, TOP_CLASSES + 1), fontsize=8, frameon=False)
fig.tight_layout(rect=(0, 0.1, 1, 1))
fig.savefig("/content/mineral_map.png", dpi=130)
plt.show()

# -------------------------------- 5) save -----------------------------------
out = res.to_geotiff("/content/match.tif")          # 3 bands: class, angle, margin  + match_legend.csv
counts.to_csv("/content/material_counts.csv", index=False)
try:
    from google.colab import files
    for f in ("/content/mineral_map.png", "/content/match.tif", "/content/match_legend.csv",
              "/content/material_counts.csv"):
        files.download(f)
except Exception:
    pass
print("saved:", out)
