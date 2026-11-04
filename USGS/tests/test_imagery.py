import numpy as np
import pytest

from usgs_splib07 import Image, get_sensor, match_image, sensor_from_wavelengths
from usgs_splib07.sensors import subset_sensor
from usgs_splib07.synthetic import demo_library, synthetic_scene

HS_CENTERS = np.arange(400, 2451, 10.0)


@pytest.fixture(scope="module")
def lib():
    return demo_library(step=1.0)


def accuracy(res, truth, labels):
    return float((res.names() == np.array(labels, dtype=object)[truth]).mean())


def test_image_from_array_scale_nodata_range():
    raw = np.array([[[1000, 20000, -9999]]], dtype=float)  # one band, 1x3 pixels
    img = Image.from_array(raw, [665.0], scale=1e-4, nodata=-9999)
    v = img.data[0, 0]
    assert v[0] == pytest.approx(0.1) and np.isnan(v[1]) and np.isnan(v[2])  # 2.0 out of range, nodata


def test_sensor_helpers():
    s = sensor_from_wavelengths("x", [500, 510, 520, 540])
    assert s.names == ["b1", "b2", "b3", "b4"] and s.fwhms[0] == pytest.approx(10)
    sub = subset_sensor("sentinel2a", ["B4", "B8", "B12"])
    assert sub.names == ["B4", "B8", "B12"] and sub.centers[0] == pytest.approx(664.6)
    with pytest.raises(KeyError):
        subset_sensor("sentinel2a", ["B99"])
    assert len(get_sensor("aster").bands) == 9


def test_hyperspectral_beats_multispectral_on_similar_minerals(lib):
    hs, t, labels = synthetic_scene(lib, HS_CENTERS, fwhm=10, noise=0.005, seed=1)
    ms, t2, _ = synthetic_scene(lib, "sentinel2a", noise=0.005, seed=1)
    acc_hs = accuracy(match_image(hs, lib), t, labels)
    acc_ms = accuracy(match_image(ms, lib), t2, labels)
    assert acc_hs >= 0.98
    assert acc_ms < acc_hs - 0.1  # S2 cannot separate clays / carbonates reliably


def test_outputs_labels_margin_and_excluded_bands(lib):
    hs, t, labels = synthetic_scene(lib, HS_CENTERS, fwhm=10, noise=0.005, seed=2)
    res = match_image(hs, lib)
    assert res.labels == sorted(labels)
    assert res.class_map.shape == (hs.rows, hs.cols) and res.angle_deg.shape == res.margin_deg.shape
    assert np.nanmedian(res.angle_deg) < 3 and np.nanmedian(res.margin_deg) > 1
    bad = (res.used_wavelengths >= 1340) & (res.used_wavelengths <= 1460)
    assert not bad.any()
    counts = res.counts()
    assert counts["pixels"].sum() == (res.class_map >= 0).sum()


def test_group_by_none_returns_single_spectra(lib):
    hs, t, labels = synthetic_scene(lib, HS_CENTERS, fwhm=10, noise=0.005, seed=3)
    res = match_image(hs, lib, group_by=None)
    assert res.labels[0].endswith("_AREF") and len(res.labels) == len(lib)


def test_max_angle_masks_vegetation_and_user_mask(lib):
    hs, t, labels = synthetic_scene(lib, HS_CENTERS, fwhm=10, noise=0.003, seed=4)
    cube = hs.data.copy()
    # pixel (0,0): odd sawtooth spectrum -> no good match; (0,1): green vegetation; (0,2): masked by user
    cube[:, 0, 0] = 0.3 + 0.2 * ((np.arange(cube.shape[0]) % 2) * 2 - 1)
    wl = hs.wavelengths
    veg = 0.04 + 0.46 / (1 + np.exp(-(wl - 710) / 14))
    cube[:, 0, 1] = veg
    img = Image(cube, wl, hs.fwhm, hs.band_names, name="t")
    user_mask = np.zeros((img.rows, img.cols), bool)
    user_mask[0, 2] = True

    res = match_image(img, lib, max_angle_deg=5.0, mask=user_mask)
    assert res.class_map[0, 0] == -1 and res.class_map[0, 1] == -1 and res.class_map[0, 2] == -1
    assert np.isnan(res.angle_deg[0, 1])  # vegetation was masked, never scored
    res2 = match_image(img, lib, max_angle_deg=None, mask_vegetation=None)
    assert res2.class_map[0, 1] >= 0  # without the mask it is matched to something


def test_library_with_deleted_channels_and_image_beyond_library_range(lib):
    holes = lib.apply(lambda wl, X: np.where(((wl > 1350) & (wl < 1420)) | (wl > 2480), np.nan, X), "holes")
    centers = np.arange(400, 2601, 10.0)  # image extends past 2500 nm where the library is empty
    hs, t, labels = synthetic_scene(lib, np.arange(400, 2451, 10.0), fwhm=10, noise=0.005, seed=5)
    hs2 = Image(np.concatenate([hs.data, np.full((15, hs.rows, hs.cols), 0.3, np.float32)]),
                np.r_[hs.wavelengths, np.arange(2460, 2610, 10.0)], np.r_[hs.fwhm, np.full(15, 10.0)], None, name="ext")
    assert accuracy(match_image(hs2, holes), t, labels) >= 0.97


def test_library_method_equals_function(lib):
    hs, t, labels = synthetic_scene(lib, HS_CENTERS, fwhm=10, noise=0.005, seed=6)
    a = match_image(hs, lib)
    b = lib.match_image(hs)
    np.testing.assert_array_equal(a.class_map, b.class_map)


# ----------------------------------------------------------------------- file I/O (needs rasterio)
rasterio = pytest.importorskip("rasterio")


def _write_tif(path, cube, transform, crs="EPSG:32636", dtype="int16", tags=None, band_tags=None, envi=None):
    with rasterio.open(path, "w", driver="GTiff", height=cube.shape[1], width=cube.shape[2], count=cube.shape[0],
                       dtype=dtype, crs=crs, transform=transform, nodata=-9999) as dst:
        dst.write(cube.astype(dtype))
        if envi:
            dst.update_tags(ns="ENVI", **envi)
        if band_tags:
            for i, t in enumerate(band_tags, 1):
                dst.update_tags(i, **t)


def test_read_geotiff_with_sensor_and_roundtrip(lib, tmp_path):
    from rasterio.transform import from_origin

    ms, truth, labels = synthetic_scene(lib, "sentinel2a", noise=0.003, seed=7)
    names = ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]
    idx = [ms.band_names.index(n) for n in names]
    tr = from_origin(500000, 4000000, 20, 20)
    p = tmp_path / "s2.tif"
    _write_tif(p, np.round(ms.data[idx] * 10000), tr)

    with pytest.raises(ValueError, match="scale"):
        Image.read(p, sensor="sentinel2a", band_names=names)
    img = Image.read(p, sensor="sentinel2a", band_names=names, scale=1e-4)
    assert img.n_bands == 10 and img.crs.to_epsg() == 32636 and img.transform == tr
    np.testing.assert_allclose(img.data, ms.data[idx], atol=1e-4)

    res = match_image(img, lib)
    out = res.to_geotiff(tmp_path / "match.tif")
    with rasterio.open(out) as src:
        assert src.count == 3 and src.crs.to_epsg() == 32636 and src.transform == tr
        cls = src.read(1)
    np.testing.assert_array_equal(np.where(cls < 0, -1, cls).astype(int), res.class_map)
    assert (tmp_path / "match_legend.csv").exists()


def test_read_wavelengths_from_envi_and_band_tags(lib, tmp_path):
    from rasterio.transform import from_origin

    hs, truth, labels = synthetic_scene(lib, np.arange(500, 2301, 100.0), fwhm=20, noise=0.003, seed=8)
    tr = from_origin(0, 0, 30, 30)
    envi = {"wavelength": "{ " + ", ".join(f"{w / 1000:.4f}" for w in hs.wavelengths) + " }",
            "wavelength_units": "Micrometers", "fwhm": "{ " + ", ".join("0.02" for _ in hs.wavelengths) + " }"}
    p1 = tmp_path / "envi_tags.tif"
    _write_tif(p1, hs.data * 10000, tr, envi=envi)
    a = Image.read(p1, scale=1e-4)
    np.testing.assert_allclose(a.wavelengths, hs.wavelengths, atol=0.1)
    np.testing.assert_allclose(a.fwhm, 20.0, atol=0.1)

    p2 = tmp_path / "band_tags.tif"
    _write_tif(p2, hs.data * 10000, tr, band_tags=[{"wavelength": f"{w:.1f}", "fwhm": "20"} for w in hs.wavelengths])
    b = Image.read(p2, scale=1e-4)
    np.testing.assert_allclose(b.wavelengths, hs.wavelengths, atol=0.1)

    p3 = tmp_path / "no_meta.tif"
    _write_tif(p3, hs.data * 10000, tr)
    with pytest.raises(ValueError, match="wavelengths"):
        Image.read(p3, scale=1e-4)
    c = Image.read(p3, scale=1e-4, wavelengths=hs.wavelengths, fwhm=20)
    assert c.n_bands == hs.n_bands
