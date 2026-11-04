from pathlib import Path

import pytest

pytest.importorskip("cartopy")
pytest.importorskip("fastapi")

import geedownload as gd  # noqa: E402


def test_author_info():
    assert gd.AUTHOR["email"] == "yamenmohamad@tabrizu.ac.ir" and gd.__author__ == "M. Yamen AL-Mohamad"
    assert "yamenetoo" in gd.about()


def test_catalogue_file_is_current():
    doc = Path(__file__).resolve().parents[1] / "docs" / "FUNCTION_CATALOGUE.md"
    def norm(t):    # argparse's option layout differs between Python versions: compare words only in those blocks
        import re
        return re.sub(r"[ \t]+", " ", re.sub(r"^\s+-.*$", "", t, flags=re.M))

    assert norm(doc.read_text(encoding="utf-8")) == norm(gd.function_catalogue()), \
        "run: geedownload catalogue -o docs/FUNCTION_CATALOGUE.md"


def test_catalogue_covers_public_api():
    text = gd.function_catalogue()
    for name in ("search_area", "download_area", "plot_map", "plot_area", "country_aoi", "save_boundary",
                 "sentinel2", "/jobs/download", "geedownload serve"):
        assert name in text
