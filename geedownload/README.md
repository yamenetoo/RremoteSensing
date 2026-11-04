<p align="center">
  <img src="src/geedownload/assets/logo.png" alt="geedownload logo" width="640">
</p>

# geedownload

Search **any area by name**, save its boundary as a **shapefile**, download **satellite data from Google Earth Engine**
for it, draw **publication-style maps** with cartopy, and serve everything as a **REST API**.

- **Datasets:** Sentinel-2, Sentinel-1, Landsat 5/7/8/9, MODIS, SRTM and Copernicus DEM, ESA WorldCover, Dynamic World, CHIRPS, ERA5-Land, VIIRS, Sentinel-5P — or **any** Earth Engine asset id.
- **Areas:** a place name (`"Masyaf, Syria"`), a country or state, a shapefile / GeoJSON, or a bounding box.
- **Maps (JPG/PNG):** lat/lon grid with degree labels, scale bar, north arrow, legend or colour bar, area boundary, country borders, and a country inset. The legend and the inset are always drawn **outside** the map frame.
- **Large areas** are split into tiles on one pixel grid and merged automatically (no 32 MB request limit).
- **How to run it (code / GUI / localhost), step by step:** [`docs/HOW_TO_RUN.md`](docs/HOW_TO_RUN.md) (Arabic).
- Full reference of every function: [`docs/FUNCTION_CATALOGUE.md`](docs/FUNCTION_CATALOGUE.md).

## Install

```bash
pip install "geedownload[all]"            # core + maps + REST API
# or from a clone:  pip install -e ".[all]"
```
Extras: `[maps]` (cartopy, matplotlib), `[api]` (FastAPI, uvicorn), `[dev]` (tests).
You need an Earth Engine enabled Google Cloud project: `gd.init_ee("my-project")` or set `EE_PROJECT`.

## 1. Python quick start

```python
import geedownload as gd
gd.set_verbose()

# search an area by name (OpenStreetMap) and look at the candidates
for i, place in enumerate(gd.search_area("Masyaf, Syria")):
    print(i, place)

# boundary shapefile only (no Earth Engine needed)
shp = gd.search_and_save("Masyaf, Syria", out_dir="out")

# boundary + satellite image + preview map in one call
res = gd.download_area(
    "Masyaf, Syria", "sentinel2", "2023-06-01", "2023-09-30",
    out_dir="out", cloud_max=10, bands=["B4", "B3", "B2", "B8"], mask_clouds=True,
    project="my-ee-project")
print(res.shapefile, res.stack)
```

Output folder:

```
out/masyaf_sentinel2_20261105_001500/
  boundary/masyaf.shp (+ .shx .dbf .prj .cpg)       EPSG:4326
  bands/10m_bands/masyaf_B4.tif ...                 one GeoTIFF per band, grouped by band type
  masyaf_sentinel2_stack.tif                        all bands in one file, band names kept
  metadata.json                                     area, dates, bands, CRS, scale, versions, author
```

### Other datasets and options

```python
gd.list_datasets()                                                      # built-in registry
gd.download_area("Tabriz, Iran", "landsat8", "2023-06-01", "2023-09-01", apply_scale=True)
gd.download_area("Damascus, Syria", "srtm")                             # elevation
gd.download_area("Jableh, Syria", "modis_ndvi", "2023-01-01", "2023-12-31", reducer="max")
gd.download_area("Aleppo, Syria", "worldcover")                         # land cover
gd.download_area("Baghdad, Iraq", "COPERNICUS/S2_HARMONIZED", "2023-06-01", "2023-07-01")   # any EE asset id
gd.download_area([42.35, 33.84, 42.55, 33.96], "sentinel2", "2023-06-01", "2023-09-30")     # bbox (old S2.py area)
gd.download_area("Masyaf, Syria", "sentinel2", "2023-06-01", "2023-09-30", per_image=True, max_images=5)
gd.download_area("Masyaf, Syria", "sentinel2", "2023-06-01", "2023-09-30", buffer_m=2000)   # 2 km around the area
gd.register_dataset(gd.Dataset("my_ds", "ORG/ASSET/ID", scale=30))      # your own dataset
```

### Country and state areas

```python
gd.country_aoi("Syria")                    # Natural Earth, falls back to OpenStreetMap when offline
gd.country_aoi("Syria", admin1="Hama")     # a province
gd.download_area(gd.country_aoi("Lebanon"), "srtm", scale=250)
```

## 2. Maps (cartopy, JPG)

```python
stack = res.stack

# true-colour map: grid + lat/lon labels, scale bar, north arrow, legend below the map, country inset beside it
gd.plot_map(stack, "masyaf_rgb.jpg", area="Masyaf, Syria", bands=["B4", "B3", "B2"],
            source="Sentinel-2 SR, summer 2023")

# single band with a colour bar
gd.plot_map(stack, "masyaf_ndvi.jpg", area="Masyaf, Syria", bands="NDVI", cmap="RdYlGn", legend_label="NDVI")

# categorical product with a class legend ("worldcover" or "dynamic_world", or your own {value: (label, "#hex")})
gd.plot_map("aleppo_worldcover_stack.tif", "aleppo_lc.jpg", area="Aleppo, Syria", classes="worldcover")

# area outline maps (no raster, no Earth Engine)
gd.plot_area("Masyaf, Syria", "where.jpg")                              # zoom to the area, country inset
gd.plot_area("Syria", "syria.jpg", extent="country", admin1=True)       # the whole country with provinces
```

Country borders and coastlines come from Natural Earth (cartopy downloads them once). Offline, the maps are still drawn without those layers.

## 3. Command line

```bash
geedownload datasets
geedownload search "Masyaf, Syria" --save out                  # shapefile only
geedownload download "Masyaf, Syria" -d sentinel2 --start 2023-06-01 --end 2023-09-30 \
        --cloud 10 --bands B4 B3 B2 --out out --project my-ee-project --map --zip
geedownload map out/.../masyaf_sentinel2_stack.tif -o rgb.jpg --area "Masyaf, Syria" --bands B4 B3 B2
geedownload map - --area Syria --extent country --admin1 -o syria.jpg
geedownload catalogue -o docs/FUNCTION_CATALOGUE.md
geedownload serve --port 8000                                  # REST API
geedownload about
```

## 4. REST API

```bash
pip install "geedownload[api]"
export EE_PROJECT=my-ee-project                  # Earth Engine project
export EE_SERVICE_ACCOUNT=me@my-project.iam.gserviceaccount.com   # headless login (optional)
export EE_PRIVATE_KEY_FILE=/secure/key.json
export GEEDOWNLOAD_API_KEY=change-me             # optional: require header X-API-Key
geedownload serve --host 0.0.0.0 --port 8000     # interactive docs: http://localhost:8000/docs
```

| method | path | purpose |
|---|---|---|
| GET | `/search?q=Masyaf, Syria` | candidate areas (`include_geometry=true` for GeoJSON) |
| GET | `/boundary?q=Masyaf, Syria` | boundary as a zipped shapefile |
| GET | `/datasets` | built-in datasets |
| POST | `/jobs/download` | start a download job (returns `job_id`) |
| GET | `/jobs/{id}` | status, metadata and file list |
| GET | `/jobs/{id}/files/{path}` | one output file (GeoTIFF, `preview.jpg`, ...) |
| GET | `/jobs/{id}/archive.zip` | the whole job folder |
| POST | `/jobs/{id}/map` | render a JPG map from a finished job |
| POST | `/maps/area` | outline map of an area or country (JPG) |
| DELETE | `/jobs/{id}` | remove a job |

```bash
H='X-API-Key: change-me'

curl -H "$H" "http://localhost:8000/search?q=Masyaf,%20Syria"
curl -H "$H" -o masyaf_boundary.zip "http://localhost:8000/boundary?q=Masyaf,%20Syria"

# 1) start a job
curl -H "$H" -H 'Content-Type: application/json' -X POST http://localhost:8000/jobs/download -d '{
  "area": "Masyaf, Syria", "dataset": "sentinel2", "start": "2023-06-01", "end": "2023-09-30",
  "cloud_max": 10, "bands": ["B4","B3","B2","B8"], "mask_clouds": true }'
# -> {"job_id": "3f9c1a7b2d44", "status": "queued", "status_url": "/jobs/3f9c1a7b2d44"}

# 2) poll, then fetch files
curl -H "$H" http://localhost:8000/jobs/3f9c1a7b2d44
curl -H "$H" -o preview.jpg http://localhost:8000/jobs/3f9c1a7b2d44/files/<folder>/preview.jpg

# 3) custom map from the finished job
curl -H "$H" -H 'Content-Type: application/json' -X POST http://localhost:8000/jobs/3f9c1a7b2d44/map \
     -d '{"bands": ["B8"], "cmap": "gray", "title": "Masyaf NIR"}' -o nir.jpg

# area / country map without Earth Engine
curl -H "$H" -H 'Content-Type: application/json' -X POST http://localhost:8000/maps/area \
     -d '{"area": "Syria", "extent": "country", "admin1": true}' -o syria.jpg
```

Python client:

```python
import requests, time
base, h = "http://localhost:8000", {"X-API-Key": "change-me"}
job = requests.post(f"{base}/jobs/download", headers=h, json={
    "area": "Masyaf, Syria", "dataset": "landsat8", "start": "2023-06-01", "end": "2023-09-01",
    "apply_scale": True}).json()["job_id"]
while (st := requests.get(f"{base}/jobs/{job}", headers=h).json())["status"] in ("queued", "running"):
    time.sleep(5)
print(st["status"], st["files"])
```

Safety defaults: the API never reads server file paths, serves job files only from the job folder, limits the bounding box
(`GEEDOWNLOAD_MAX_AREA_KM2`, default 20 000 km²) and runs a limited number of parallel jobs (`GEEDOWNLOAD_WORKERS`, default 2).

## 5. Desktop GUI (Tkinter) in Arabic · فارسی · English

```bash
pip install "geedownload[all]"     # includes arabic-reshaper + python-bidi for Arabic/Persian text on Linux
geedownload gui                    # English;  geedownload gui --lang ar   /   --lang fa
```

A Tkinter window (needs `tkinter`: included with Python on Windows/macOS, `sudo apt install python3-tk` on Debian/Ubuntu).
Tabs: **find an area** (results list, "use this area", save the boundary shapefile) → **download** (dataset, dates, bands,
cloud limit, output folder, Earth Engine project; shows a preview map when finished) → **maps** (map from a GeoTIFF or an
outline map of an area/country; legend and country inset always outside the map frame) → **about**. The language can be
switched at any time; the text lives in `assets/gui/i18n.json`.

Prefer a browser? `geedownload webgui` starts the REST API and opens the same three-language interface at `/app`.

## Migrating from `S2.py`

`S2.py` hard-coded Sentinel-2 and a bounding box. The same run now is:

```python
gd.download_area([42.35, 33.84, 42.55, 33.96], "sentinel2", "2023-06-01", "2023-09-30",
                 out_dir="out", cloud_max=10, bands="all", crs="EPSG:32637", scale=10, project="my-ee-project")
```

## Notes

- Default CRS is the local UTM zone; default pixel size is the dataset's native scale. `clip=True` masks pixels outside the real boundary polygon.
- Place search uses OpenStreetMap Nominatim (max 1 request per second) — please respect its usage policy.
- The test-suite (`pytest`) mocks Earth Engine and the network; run a real download once on your own account to validate your setup.

## Author and contact

**M. Yamen AL-Mohamad** (Mohamad Yamen Al-Mohamad · محمد يامن المحمد)
Department of Statistics, University of Tabriz, Tabriz, Iran

- Email: [yamenmohamad@tabrizu.ac.ir](mailto:yamenmohamad@tabrizu.ac.ir)
- GitHub: [github.com/yamenetoo](https://github.com/yamenetoo) · Website: [yamenetoo.github.io](https://yamenetoo.github.io)
- Google Scholar: [profile](https://scholar.google.com/citations?user=un_6SQwAAAAJ) · ORCID: [0009-0009-1665-7203](https://orcid.org/0009-0009-1665-7203)

If you use geedownload in a publication, please cite it as: AL-Mohamad, M. Y. (2026). *geedownload: area search, Earth Engine downloads, maps and API* (v0.2.0).

## License

MIT — see [LICENSE](LICENSE).

---

## بالعربية

**geedownload** حزمة بايثون وواجهة REST: تبحث عن أي منطقة بالاسم (مدينة، محافظة، دولة)، وتحفظ حدودها كملف shapefile،
وتنزّل صور أي قمر صناعي من Google Earth Engine، وترسم خرائط JPG بمكتبة cartopy (شبكة خطوط الطول والعرض، مقياس رسم،
سهم الشمال، مفتاح الخريطة، وخريطة مصغّرة للدولة). المفتاح والخريطة المصغّرة يظهران دائماً **خارج** إطار الخريطة.

```python
import geedownload as gd
res = gd.download_area("مصياف, سوريا", "sentinel2", "2023-06-01", "2023-09-30", out_dir="out", project="my-ee-project")
gd.plot_map(res.stack, "map.jpg", area="Masyaf, Syria", bands=["B4", "B3", "B2"])
```

واجهة رسومية بثلاث لغات (العربية، الفارسية، الإنجليزية): `geedownload gui` (نافذة Tkinter) أو `geedownload webgui` (متصفح).

المؤلف: **محمد يامن المحمد** — قسم الإحصاء، جامعة تبريز — البريد: yamenmohamad@tabrizu.ac.ir
