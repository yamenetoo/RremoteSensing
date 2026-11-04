"""Offline smoke test + real-download example for geedownload.

Offline part (no Earth Engine account, no internet needed): datasets, boundary shapefile from a bbox,
a synthetic GeoTIFF, a JPG map, the REST API and the 3-language GUI.
Real part: set EE_PROJECT=<your-project> and the script also downloads Sentinel-2 for a bbox.
"""
import os
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

import geedownload as gd
from geedownload import maps
from geedownload.aoi import AOI

out = Path(tempfile.mkdtemp(prefix="gd_test_"))
print("geedownload", gd.__version__, "->", out)

# 1) datasets
keys = [d.key for d in gd.list_datasets()]
assert {"sentinel2", "landsat8", "srtm"} <= set(keys), keys
print("1) datasets:", len(keys))

# 2) boundary shapefile for a bounding box (Masyaf area)
aoi = gd.resolve_aoi([36.30, 34.99, 36.38, 35.07])
shp = gd.save_boundary(aoi, out / "boundary")
assert Path(shp).exists()
print("2) shapefile:", shp)

# 3) synthetic 4-band raster + JPG map (grid, lat/lon, scale bar, legend outside the map)
tif = out / "demo.tif"
yy, xx = np.mgrid[0:100, 0:100]
with rasterio.open(tif, "w", driver="GTiff", height=100, width=100, count=4, dtype="float32", crs="EPSG:32637",
                   transform=from_origin(250000, 3880000, 30, 30)) as d:
    for i, n in enumerate(["B4", "B3", "B2", "NDVI"], 1):
        d.write((50 + 40 * np.sin(xx / (8 + i)) + 10 * np.cos(yy / 12)).astype("float32"), i)
        d.set_band_description(i, n)
maps._ne_available = lambda *a, **k: False          # skip Natural Earth download in this test
jpg = gd.plot_map(tif, out / "rgb.jpg", bands=["B4", "B3", "B2"], inset=False, title="Demo")
assert Path(jpg).read_bytes()[:3] == b"\xff\xd8\xff"
print("3) map:", jpg)

# 4) REST API + web GUI (real local server, standard library client)
import json, threading, time, urllib.request
import uvicorn
from geedownload.api import create_app
os.environ["GEEDOWNLOAD_WORKDIR"] = str(out / "jobs")
server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=8765, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()
for _ in range(50):
    try:
        health = json.load(urllib.request.urlopen("http://127.0.0.1:8765/health")); break
    except OSError:
        time.sleep(0.2)
assert health["status"] == "ok"
page = urllib.request.urlopen("http://127.0.0.1:8765/app").read().decode()
assert "فارسی" in page and "العربية" in page
server.should_exit = True
print("4) API + GUI ok  (open it yourself with:  geedownload gui)")

# 4b) desktop GUI (Tkinter) - skipped when tkinter or a display is missing
import subprocess, sys
r = subprocess.run([sys.executable, "-c",
    "import sys, tkinter\nfrom geedownload.gui import App\n"
    "try: a = App('fa')\nexcept tkinter.TclError: sys.exit(77)\n"
    "a.update(); a.set_lang('ar'); a.update(); a.destroy()"], capture_output=True, text=True)
print("4b) Tkinter GUI:", "ok" if r.returncode == 0 else "skipped (no tkinter / no display)" if r.returncode in (77, 1) and "tkinter" in r.stderr + "" or r.returncode == 77 else r.stderr[-200:])

# 5) real download (optional)
proj = os.environ.get("EE_PROJECT")
if proj:
    res = gd.download_area([36.30, 34.99, 36.38, 35.07], "sentinel2", "2023-06-01", "2023-09-30", out_dir=out,
                           cloud_max=10, bands=["B4", "B3", "B2"], mask_clouds=True, project=proj)
    gd.plot_map(res.stack, out / "masyaf_rgb.jpg", area=res.shapefile, bands=["B4", "B3", "B2"])
    print("5) real download:", res.stack)
else:
    print("5) skipped real download (set EE_PROJECT=<your Earth Engine project> to enable)")
print("ALL CHECKS PASSED")
