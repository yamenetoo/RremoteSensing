import time
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon, box

pytest.importorskip("cartopy")
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import geedownload as gd  # noqa: E402
from geedownload import maps  # noqa: E402
from geedownload.aoi import AOI  # noqa: E402
from geedownload.errors import GeeDownloadError  # noqa: E402
from geedownload.geocode import Place  # noqa: E402


@pytest.fixture(autouse=True)
def offline_maps(monkeypatch):
    """No Natural Earth download and no geocoding during tests."""
    monkeypatch.setattr(maps, "_ne_available", lambda *a, **k: False)
    monkeypatch.setattr(maps, "country_aoi", lambda *a, **k: AOI("Syria", box(35.5, 32.3, 42.4, 37.3), "Syria", "natural_earth"))


def make_stack(path: Path, names=("B4", "B3", "B2", "NDVI")):
    n = 120
    yy, xx = np.mgrid[0:n, 0:n]
    with rasterio.open(path, "w", driver="GTiff", height=n, width=n, count=len(names), dtype="float32",
                       crs="EPSG:32637", transform=from_origin(780000.0, 3900000.0, 30.0, 30.0)) as d:
        for i, nm in enumerate(names, 1):
            d.write((50 + 40 * np.sin(xx / (10 + i)) + 10 * np.cos(yy / 15)).astype("float32"), i)
            d.set_band_description(i, nm)
    return path


AOI_LL = box(42.09, 35.10, 42.19, 35.19)      # inside the raster footprint


def is_jpeg(p: Path) -> bool:
    return p.exists() and p.stat().st_size > 5000 and p.read_bytes()[:3] == b"\xff\xd8\xff"


# ----------------------------------------------------------------------------- maps
def test_rgb_map_jpg(tmp_path):
    out = gd.plot_map(make_stack(tmp_path / "s.tif"), tmp_path / "rgb.jpg", area=AOI_LL, bands=["B4", "B3", "B2"],
                      country="Syria", source="test")
    assert is_jpeg(out)


def test_single_band_and_classes(tmp_path):
    s = make_stack(tmp_path / "s.tif")
    assert is_jpeg(gd.plot_map(s, tmp_path / "ndvi.jpg", area=AOI_LL, bands="NDVI", cmap="RdYlGn", legend_label="NDVI"))
    cls = tmp_path / "lc.tif"
    with rasterio.open(cls, "w", driver="GTiff", height=50, width=50, count=1, dtype="uint8", crs="EPSG:32637",
                       transform=from_origin(780000.0, 3900000.0, 30.0, 30.0)) as d:
        d.write(np.random.default_rng(0).choice([10, 40, 50, 80], (50, 50)).astype("uint8"), 1)
        d.set_band_description(1, "Map")
    assert is_jpeg(gd.plot_map(cls, tmp_path / "lc.jpg", bands="Map", classes="worldcover", inset=False))


def test_png_and_area_map(tmp_path):
    out = gd.plot_area(AOI("Test", AOI_LL, "Test, Hama, Syria", "search"), tmp_path / "a.png")
    assert out.read_bytes()[:4] == b"\x89PNG"
    assert is_jpeg(gd.plot_area(AOI("Test", AOI_LL), tmp_path / "b.jpg", extent="country", country="Syria"))


def test_map_errors(tmp_path):
    s = make_stack(tmp_path / "s.tif")
    with pytest.raises(GeeDownloadError):
        gd.plot_map(s, tmp_path / "x.jpg", bands=["B4", "B9"])
    with pytest.raises(GeeDownloadError):
        gd.plot_map(s, tmp_path / "x.jpg", inset_loc="upper left")     # inset must stay outside the map
    with pytest.raises(GeeDownloadError):
        gd.plot_map(None, tmp_path / "x.jpg")


def test_preview_args():
    assert maps.preview_args({"bands": ["B2", "B3", "B4", "B8"]})["bands"] == ["B4", "B3", "B2"]
    assert maps.preview_args({"bands": ["NDVI"], "dataset_key": "modis_ndvi"})["cmap"] == "RdYlGn"
    assert maps.preview_args({"bands": ["Map"], "dataset_key": "worldcover"})["classes"] == "worldcover"


# ----------------------------------------------------------------------------- REST API
@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from geedownload import api, pipeline
    from geedownload.boundary import save_boundary

    monkeypatch.setenv("GEEDOWNLOAD_WORKDIR", str(tmp_path / "jobs"))
    monkeypatch.delenv("GEEDOWNLOAD_API_KEY", raising=False)

    def fake_download(area, dataset, start, end, *, out_dir, **kw):
        folder = Path(out_dir) / "test_area_sentinel2_x"
        folder.mkdir(parents=True)
        shp = save_boundary(AOI("Test Area", AOI_LL, "Test Area, Hama, Syria", "search"), folder / "boundary")
        stack = make_stack(folder / "test_area_sentinel2_stack.tif")
        info = {"area": "Test Area", "dataset": "COPERNICUS/S2_SR_HARMONIZED", "dataset_key": "sentinel2",
                "bands": ["B4", "B3", "B2", "NDVI"], "start": start, "end": end, "country": "Syria"}
        return pipeline.DownloadResult(folder=folder, shapefile=shp, stack=stack, info=info)

    fake_places = lambda q, **k: [  # noqa: E731
        Place("Masyaf", "Masyaf, Hama, Syria", (36.3, 35.0, 36.4, 35.1), box(36.3, 35.0, 36.4, 35.1), "relation", 1, "boundary", "administrative")]
    from geedownload import aoi as aoi_mod

    monkeypatch.setattr(pipeline, "download_area", fake_download)
    monkeypatch.setattr(api, "search_area", fake_places)        # GET /search
    monkeypatch.setattr(aoi_mod, "search_area", fake_places)    # name -> AOI (GET /boundary)
    return TestClient(api.create_app())


def wait_done(client, jid):
    for _ in range(100):
        st = client.get(f"/jobs/{jid}").json()
        if st["status"] in ("done", "failed"):
            return st
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_api_basics(client):
    assert client.get("/health").json()["status"] == "ok"
    root = client.get("/").json()
    assert root["author"]["email"] == "yamenmohamad@tabrizu.ac.ir"
    assert client.get("/logo.png").headers["content-type"] == "image/png"
    keys = {d["key"] for d in client.get("/datasets").json()}
    assert {"sentinel2", "landsat8", "srtm"} <= keys
    hits = client.get("/search", params={"q": "Masyaf", "include_geometry": True}).json()
    assert hits[0]["has_polygon"] and hits[0]["geometry"]["type"] == "Polygon"
    assert client.get("/openapi.json").json()["info"]["contact"]["email"] == "yamenmohamad@tabrizu.ac.ir"


def test_api_boundary_zip(client):
    r = client.get("/boundary", params={"q": "Masyaf, Syria"})
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_api_job_flow_and_map(client):
    r = client.post("/jobs/download", json={"area": [42.0, 35.0, 42.3, 35.3], "dataset": "sentinel2",
                                           "start": "2023-06-01", "end": "2023-09-30"})
    assert r.status_code == 202
    jid = r.json()["job_id"]
    st = wait_done(client, jid)
    assert st["status"] == "done", st
    assert any(f.endswith("preview.jpg") for f in st["files"]) and "folder" not in st
    img = next(f for f in st["files"] if f.endswith("preview.jpg"))
    assert client.get(f"/jobs/{jid}/files/{img}").content[:3] == b"\xff\xd8\xff"
    m = client.post(f"/jobs/{jid}/map", json={"bands": ["NDVI"], "cmap": "RdYlGn", "dpi": 100})
    assert m.status_code == 200 and m.headers["content-type"] == "image/jpeg"
    assert client.get(f"/jobs/{jid}/archive.zip").content[:2] == b"PK"
    assert client.get(f"/jobs/{jid}/files/..%2F..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.delete(f"/jobs/{jid}").json() == {"deleted": jid}
    assert client.get(f"/jobs/{jid}").status_code == 404


def test_api_area_map_and_validation(client):
    r = client.post("/maps/area", json={"area": [42.09, 35.10, 42.19, 35.19], "country": "Syria", "dpi": 90})
    assert r.status_code == 200 and r.content[:3] == b"\xff\xd8\xff"
    assert client.post("/jobs/download", json={"area": "/etc/secret.shp"}).status_code == 400
    assert client.post("/jobs/download", json={"area": [1, 2, 3]}).status_code == 422
    assert client.get("/jobs/not-a-job").status_code == 404


def test_api_key(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from geedownload import api

    monkeypatch.setenv("GEEDOWNLOAD_WORKDIR", str(tmp_path / "j"))
    monkeypatch.setenv("GEEDOWNLOAD_API_KEY", "s3cret")
    c = TestClient(api.create_app())
    assert c.get("/health").status_code == 200
    assert c.get("/datasets").status_code == 401
    assert c.get("/datasets", headers={"X-API-Key": "wrong"}).status_code == 401
    assert c.get("/datasets", headers={"X-API-Key": "s3cret"}).status_code == 200
