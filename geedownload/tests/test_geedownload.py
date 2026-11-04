import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon

from geedownload import grid
from geedownload.aoi import buffer_aoi, resolve_aoi
from geedownload.boundary import read_boundary, save_boundary
from geedownload.catalog import get_dataset, list_datasets
from geedownload.download import merge_tiles, resolve_bands, stack_bands
from geedownload.errors import AreaNotFound, GeeDownloadError
from geedownload import geocode

NOMINATIM_SAMPLE = [
    {"name": "Masyaf", "display_name": "Masyaf, Hama, Syria", "boundingbox": ["35.0", "35.1", "36.3", "36.4"],
     "osm_type": "relation", "osm_id": 1, "category": "boundary", "type": "administrative", "importance": 0.4,
     "geojson": {"type": "Polygon", "coordinates": [[[36.3, 35.0], [36.4, 35.0], [36.4, 35.1], [36.3, 35.1], [36.3, 35.0]]]}},
    {"name": "Masyaf", "display_name": "Masyaf point", "boundingbox": ["35.05", "35.06", "36.34", "36.35"],
     "osm_type": "node", "osm_id": 2, "category": "place", "type": "town", "importance": 0.9,
     "geojson": {"type": "Point", "coordinates": [36.34, 35.05]}},
]


class FakeResp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


def test_search_area_prefers_polygon(monkeypatch):
    monkeypatch.setattr(geocode.requests, "get", lambda *a, **k: FakeResp(NOMINATIM_SAMPLE))
    monkeypatch.setattr(geocode.time, "sleep", lambda s: None)
    places = geocode.search_area("Masyaf, Syria")
    assert places[0].has_polygon and places[0].bbox == (36.3, 35.0, 36.4, 35.1)
    assert not places[1].has_polygon and places[1].polygon.bounds == (36.34, 35.05, 36.35, 35.06)


def test_search_area_not_found(monkeypatch):
    monkeypatch.setattr(geocode.requests, "get", lambda *a, **k: FakeResp([]))
    monkeypatch.setattr(geocode.time, "sleep", lambda s: None)
    with pytest.raises(AreaNotFound):
        geocode.search_area("zzzz nowhere")


def test_resolve_aoi_variants(monkeypatch):
    assert resolve_aoi([42.35, 33.84, 42.55, 33.96]).bbox == (42.35, 33.84, 42.55, 33.96)
    assert resolve_aoi("42.35,33.84,42.55,33.96").source == "bbox"
    monkeypatch.setattr(geocode.requests, "get", lambda *a, **k: FakeResp(NOMINATIM_SAMPLE))
    monkeypatch.setattr(geocode.time, "sleep", lambda s: None)
    assert resolve_aoi("Masyaf, Syria").source == "search"
    with pytest.raises(GeeDownloadError):
        resolve_aoi([200, 0, 210, 5])


def test_shapefile_roundtrip(tmp_path):
    poly = Polygon([(36.3, 35.0), (36.4, 35.0), (36.4, 35.1), (36.3, 35.0)])
    aoi = resolve_aoi(poly, name="مصياف Masyaf")
    shp = save_boundary(aoi, tmp_path)
    assert shp.suffix == ".shp" and shp.exists() and shp.with_suffix(".dbf").exists()
    back = read_boundary(shp)
    assert back.equals(poly)   # shapefiles may reverse ring orientation
    assert resolve_aoi(str(shp)).source == "file"


def test_buffer_grows_area():
    aoi = resolve_aoi([36.3, 35.0, 36.4, 35.1])
    assert buffer_aoi(aoi, 1000).geometry.area > aoi.geometry.area


def test_grid_tiles_cover_bounds_without_gaps():
    crs = grid.utm_crs_for(42.45, 33.9)
    assert crs == "EPSG:32638"
    b = grid.snap_bounds(grid.project_bbox((42.0, 33.0, 43.5, 34.5), crs), 10)
    tiles = grid.make_tiles(b, 10, 1500)
    rows, cols = grid.grid_shape(b, 10)
    assert len(tiles) == -(-rows // 1500) * -(-cols // 1500) > 1
    assert min(t[0] for t in tiles) == b[0] and max(t[2] for t in tiles) == pytest.approx(b[2])
    assert min(t[1] for t in tiles) == pytest.approx(b[1]) and max(t[3] for t in tiles) == b[3]
    assert all((t[2] - t[0]) / 10 <= 1500 and (t[3] - t[1]) / 10 <= 1500 for t in tiles)
    assert all(((t[0] - b[0]) / 10) % 1 == 0 for t in tiles)   # tiles stay on the same pixel grid


def test_geographic_step():
    assert grid.step_in_crs_units(30, "EPSG:4326") == pytest.approx(30 / 111320)


def _write(path, arr, x0, y1, step=10.0, crs="EPSG:32637"):
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype=arr.dtype, crs=crs, transform=from_origin(x0, y1, step, step)) as d:
        d.write(arr, 1)


def test_merge_and_stack(tmp_path):
    full = np.arange(40, dtype="uint16").reshape(4, 10)
    _write(tmp_path / "a.tif", full[:, :5], 0, 40)
    _write(tmp_path / "b.tif", full[:, 5:], 50, 40)
    out = merge_tiles([tmp_path / "a.tif", tmp_path / "b.tif"], tmp_path / "m.tif")
    with rasterio.open(out) as r:
        assert (r.read(1) == full).all()
    _write(tmp_path / "f.tif", full.astype("float32") / 2, 0, 40)
    st = stack_bands({"B4": out, "ndvi": tmp_path / "f.tif"}, tmp_path / "stack.tif")
    with rasterio.open(st) as r:
        assert r.count == 2 and r.descriptions == ("B4", "ndvi") and r.dtypes[0] == "float32"


def test_catalog():
    keys = {d.key for d in list_datasets()}
    assert {"sentinel2", "landsat8", "sentinel1", "srtm", "modis_ndvi"} <= keys
    assert get_dataset("s2").key == "sentinel2"
    assert get_dataset("COPERNICUS/S2_SR_HARMONIZED").key == "sentinel2"
    assert get_dataset("MY/CUSTOM/ASSET").collection_id == "MY/CUSTOM/ASSET"
    with pytest.raises(GeeDownloadError):
        get_dataset("nonsense")


def test_resolve_bands():
    s2 = get_dataset("sentinel2")
    avail = ["B2", "B3", "B4", "B8", "SCL"]
    assert resolve_bands(s2, ["B4", "B3", "B2"], avail) == ["B4", "B3", "B2"]
    assert resolve_bands(s2, "all", avail) == avail
    assert resolve_bands(s2, "10m_bands", avail) == ["B2", "B3", "B4", "B8"]
    with pytest.raises(GeeDownloadError):
        resolve_bands(s2, ["B12"], avail)
