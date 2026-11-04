import numpy as np
import pytest

from usgs_splib07 import SpectralLibrary, build_catalog, build_library, get_sensor
from usgs_splib07 import preprocess as pp


def test_catalog_filters_and_parsing(fake_root):
    cat = build_catalog(fake_root)  # AREF only, errorbars ignored
    assert len(cat) == 4
    assert set(cat["chapter"]) == {"M", "V"}
    row = cat[cat["material"] == "Calcite"].iloc[0]
    assert row["sample"] == "HS48.3B" and row["family"] == "ASD" and row["kind"] == "AREF"
    assert len(build_catalog(fake_root, kinds=None)) == 5
    assert len(build_catalog(fake_root, chapters="V")) == 1


def test_build_library_grid_nan_and_dropping(fake_root):
    lib = build_library(fake_root, step=10.0)
    assert lib.wavelengths[0] == 350 and lib.wavelengths[-1] == 2500
    names = set(lib.meta["material"])
    assert names == {"Calcite", "Flat_Mineral", "Grass_Dry"}  # Quartz (FTIR) dropped
    calcite = lib.select(name_contains="calcite").X[0]
    gap = (lib.wavelengths > 1405) & (lib.wavelengths < 1415)
    assert np.isnan(calcite[gap]).all() and np.isfinite(calcite[~gap]).mean() > 0.97
    assert (lib.X[np.isfinite(lib.X)] > -1e29).all()  # no -1.23e34 leaked


def test_negative_option(fake_root):
    lib = build_library(fake_root, step=10.0, negative="nan")
    assert not np.nanmin(lib.X) < 0


def test_resample_linear_exact():
    wl = np.arange(400, 1000, 1.0)
    y = 0.001 * wl
    out = pp.resample(wl, y, np.array([450.5, 700.0, 999.0, 1200.0]))[0]
    np.testing.assert_allclose(out[:3], 0.001 * np.array([450.5, 700.0, 999.0]), atol=1e-9)
    assert np.isnan(out[3])  # no extrapolation


def test_sensor_convolution_constant_and_coverage():
    wl = np.arange(350, 2501, 1.0)
    X = np.full((2, len(wl)), 0.4)
    Xb, s = pp.to_sensor(wl, X, "sentinel2a")
    np.testing.assert_allclose(Xb, 0.4)
    assert Xb.shape[1] == 13
    # band with mostly missing data becomes NaN
    X2 = X.copy()
    X2[:, (wl > 1300) & (wl < 1450)] = np.nan
    Xb2, _ = pp.to_sensor(wl, X2, "sentinel2a")
    assert np.isnan(Xb2[:, s.names.index("B10")]).all()
    assert np.isfinite(Xb2[:, s.names.index("B4")]).all()


def test_sensor_registry_aliases():
    assert get_sensor("S2").name == "sentinel2a"
    assert get_sensor("landsat9").name == "landsat8"
    with pytest.raises(KeyError):
        get_sensor("nope")


def test_continuum_removal_bounds_and_feature_depth():
    wl = np.arange(2000, 2400, 1.0)
    y = 0.8 - 0.3 * np.exp(-0.5 * ((wl - 2200) / 15) ** 2)
    cr = pp.continuum_removal(wl, y)[0]
    assert np.nanmax(cr) <= 1.0 + 1e-9
    assert cr[200] < 0.7 and cr[0] == pytest.approx(1.0) and cr[-1] == pytest.approx(1.0)
    d = pp.band_depth(wl, y, 2000, 2200, 2399)[0]
    assert 0.3 < d < 0.4


def test_derivative_of_line_and_smooth_keeps_gaps():
    wl = np.arange(400, 800, 2.0)
    y = 0.001 * wl
    d = pp.derivative(wl, y, 1, window=9, poly=2)[0]
    np.testing.assert_allclose(d[5:-5], 0.001, atol=1e-9)
    y2 = y.copy()
    y2[50:55] = np.nan
    assert np.isnan(pp.smooth(wl, y2)[0][50:55]).all()


def test_snv_normalize_sam():
    X = np.array([[1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0], [4.0, 3.0, 2.0, 1.0]])
    z = pp.snv(X)
    np.testing.assert_allclose(z[0], z[1])
    np.testing.assert_allclose(np.linalg.norm(pp.normalize(X, "l2"), axis=1), 1.0)
    ang = pp.spectral_angle(X, X[0])
    assert ang[0] == pytest.approx(0, abs=1e-7) and ang[1] == pytest.approx(0, abs=1e-7) and ang[2] > 0.5
    Xn = X.copy()
    Xn[0, 0] = np.nan  # shared-valid-channel handling
    assert np.isfinite(pp.spectral_angle(Xn, X[1])[0])


def test_library_pipeline_match_save_load(fake_root, tmp_path):
    lib = build_library(fake_root, step=5.0)
    out = lib.pipeline(["smooth", ("to_sensor", {"sensor": "sentinel2a"}), ("normalized", {"method": "l2"})])
    assert out.band_names[0] == "B1" and out.shape == (len(lib), 13)
    assert "to_sensor(sentinel2a)" in out.history[-2]
    df = out.to_frame()
    assert {"name", "B8A", "B12"} <= set(df.columns)

    q = lib.select(name_contains="grass").X[0]
    top = lib.match(q, k=1)
    assert top.loc[0, "material"] == "Grass_Dry" and top.loc[0, "angle_deg"] < 1e-6

    p = lib.save(tmp_path / "lib.npz")
    back = SpectralLibrary.load(p)
    np.testing.assert_allclose(back.X, lib.X, equal_nan=True)
    assert list(back.meta["name"]) == list(lib.meta["name"]) and back.history == lib.history

    idx = lib.indices(nd={"ndvi_like": (842, 665)}, depths={"carb": (2250, 2340, 2400)})
    assert idx.shape == (len(lib), 2)
