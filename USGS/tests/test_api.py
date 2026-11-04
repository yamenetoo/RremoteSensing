import numpy as np
import pandas as pd
import pytest

import usgs_splib07 as splib
from usgs_splib07 import api


def test_get_library_downloads_and_builds_once(fake_root, tmp_path, monkeypatch):
    calls = {"download": 0}

    def fake_download(dest, **kw):
        calls["download"] += 1
        return fake_root

    monkeypatch.setattr(api, "download_splib07", fake_download)
    home = tmp_path / "home"
    lib = splib.get_library(home, chapters="MV", step=10.0)
    assert calls["download"] == 1 and len(lib) >= 3
    cached = list((home / "libraries").glob("*.npz"))
    assert len(cached) == 1 and "MV" in cached[0].name

    again = splib.get_library(home, chapters="MV", step=10.0)  # served from the cache
    assert calls["download"] == 1
    np.testing.assert_allclose(again.X, lib.X, equal_nan=True)

    splib.get_library(home, chapters="MV", step=10.0, refresh=True)  # rebuild
    assert calls["download"] == 2
    splib.get_library(home, chapters="M", step=10.0)  # different arguments, different cache file
    assert len(list((home / "libraries").glob("*.npz"))) == 2


def test_default_home_env(monkeypatch, tmp_path):
    monkeypatch.setenv("USGS_SPLIB07_HOME", str(tmp_path / "x"))
    assert api.default_home() == tmp_path / "x"


def test_search_materials_spectrum_csv_plot():
    lib = splib.demo_library(step=5.0)
    hits = lib.search("calc")
    assert list(hits["material"]) == ["Calcite"] and hits.index[0] == 3
    mats = lib.materials()
    assert set(mats["material"]) == set(lib.meta["material"]) and mats["n_spectra"].sum() == len(lib)
    np.testing.assert_array_equal(lib.spectrum(3), lib.spectrum("Calcite_SYN1_ASDFRb_AREF"))
    with pytest.raises(KeyError, match="Similar names"):
        lib.spectrum("Calcite_nope")
    lib.spectrum(0)[0] = 99  # a copy: the library is untouched
    assert lib.X[0, 0] != 99

    import matplotlib

    matplotlib.use("Agg")
    ax = lib.plot("kaol")
    assert len(ax.lines) == 1
    assert len(lib.plot(["Calcite_SYN1_ASDFRb_AREF", 0]).lines) == 2

    csv = lib.to_csv(__import__("pathlib").Path(__file__).parent / "_tmp_lib.csv")
    try:
        df = pd.read_csv(csv)
        assert df.shape[0] == len(lib) and "name" in df.columns
    finally:
        csv.unlink()


def test_function_catalogue_is_complete_and_in_sync():
    from pathlib import Path

    df = splib.list_functions()
    assert (df["summary"].str.len() > 10).all(), df[df["summary"].str.len() <= 10]["name"].tolist()
    assert len(splib.list_functions("sensors")) == 4
    md = splib.catalogue_markdown()
    docs = Path(__file__).resolve().parents[1] / "docs" / "FUNCTIONS.md"
    assert docs.read_text() == md, "docs/FUNCTIONS.md is stale: run  splib07 functions --markdown > docs/FUNCTIONS.md"


def test_every_public_name_is_exported_and_importable():
    for name in splib.__all__:
        assert hasattr(splib, name), name
