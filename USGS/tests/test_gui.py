import re
from pathlib import Path

import numpy as np
import pytest

from usgs_splib07.gui.i18n import LANGS, RTL, STRINGS, t
from usgs_splib07.gui.logic import build_steps, parse_spectrum, validate_params

# ----------------------------------------------------------------------------- translations


def test_every_string_exists_in_all_languages_with_same_placeholders():
    for key, entry in STRINGS.items():
        assert set(entry) == set(LANGS), key
        assert all(entry[l].strip() for l in LANGS), key
        holes = {l: sorted(re.findall(r"{(\w+)}", entry[l])) for l in LANGS}
        assert holes["en"] == holes["ar"] == holes["fa"], (key, holes)


def test_arabic_and_persian_are_really_translated():
    arabic = re.compile(r"[؀-ۿ]")
    for key, entry in STRINGS.items():
        if key in {"app_title"}:  # contains the Latin acronym but is still translated
            continue
        assert arabic.search(entry["ar"]) and arabic.search(entry["fa"]), key
    # Persian-specific letters appear (not just copied Arabic)
    assert any(ch in "".join(e["fa"] for e in STRINGS.values()) for ch in "پچژگ")
    assert RTL == {"ar", "fa"}


def test_t_formats_and_falls_back():
    assert "5" in t("found", "ar", n=5) and "5" in t("found", "fa", n=5)
    assert t("run", "xx") == t("run", "en")


# ----------------------------------------------------------------------------- logic


def test_parse_spectrum_formats_units_and_digits():
    wl, y = parse_spectrum("wavelength,reflectance\n0.5,0.1\n0.6,0.2\n0.7,0.3\n")  # micrometres, header
    np.testing.assert_allclose(wl, [500, 600, 700])
    wl, y = parse_spectrum("700;0.3\n500;0.1\n600;0.2")  # semicolons, unsorted
    np.testing.assert_allclose(wl, [500, 600, 700])
    np.testing.assert_allclose(y, [0.1, 0.2, 0.3])
    wl, y = parse_spectrum("۵۰۰\t۰٫۱\n۶۰۰\t۰٫۲\n۷۰۰\t۰٫۳".encode("utf-8"))  # Persian digits and decimal mark, bytes
    np.testing.assert_allclose(wl, [500, 600, 700])
    np.testing.assert_allclose(y, [0.1, 0.2, 0.3])
    wl, _ = parse_spectrum("٥٠٠ ٠٫١\n٦٠٠ ٠٫٢\n٧٠٠ ٠٫٣")  # Arabic-Indic digits
    np.testing.assert_allclose(wl, [500, 600, 700])
    with pytest.raises(ValueError, match="at least 3"):
        parse_spectrum("500 0.1\n600 0.2")
    with pytest.raises(ValueError, match="distinct"):
        parse_spectrum("500 0.1\n500 0.2\n600 0.3")


def test_build_steps_and_validation():
    p = {"window": 11, "poly": 3, "order": 1, "method": "l2", "sensor": "sentinel2a"}
    steps = build_steps(["clip", "smooth", "derivative", "continuum", "snv", "normalize", "to_sensor"], p)
    assert [s if isinstance(s, str) else s[0] for s in steps] == [
        "clip", "smooth", "derivative", "continuum_removed", "snv", "normalized", "to_sensor"]
    assert validate_params(["smooth"], {"window": 10, "poly": 3}) == "bad_window"
    assert validate_params(["smooth"], {"window": 3, "poly": 3}) == "bad_window"
    assert validate_params(["smooth"], p) is None
    custom = {"sensor": "custom", "start": 500.0, "stop": 400.0, "spacing": 10.0, "fwhm": 10.0}
    assert validate_params(["to_sensor"], custom) == "bad_grid"
    import usgs_splib07 as splib

    lib = splib.demo_library(step=5.0)
    ok = dict(custom, stop=2400.0, start=400.0)
    out = lib.pipeline(build_steps(["to_sensor"], ok))
    assert out.shape == (len(lib), 201)


# ----------------------------------------------------------------------------- the app, headless
streamlit_testing = pytest.importorskip("streamlit.testing.v1")


def _app(lang):
    import usgs_splib07.gui as g

    at = streamlit_testing.AppTest.from_file(str(Path(g.__file__).with_name("app.py")), default_timeout=90)
    at.session_state["lang"] = lang
    return at.run()


@pytest.mark.parametrize("lang", ["en", "ar", "fa"])
def test_app_starts_in_each_language(lang):
    at = _app(lang)
    assert not at.exception
    assert at.title[0].value == t("app_title", lang)
    assert [x.label for x in at.tabs] == [t(k, lang) for k in ("tab_data", "tab_browse", "tab_pre", "tab_compare", "tab_about")]
    if lang in RTL:
        assert any("direction: rtl" in m.value for m in at.markdown)


def test_app_preprocess_and_compare_flow():
    at = _app("en")
    steps = next(m for m in at.multiselect if m.label == t("steps", "en"))
    steps.set_value(["smooth", "continuum", "normalize"]).run()
    next(b for b in at.button if b.label == t("run", "en")).click().run()
    assert not at.exception and not at.error
    assert "smooth(11,3)" in at.caption[-1].value or any("smooth(11,3)" in c.value for c in at.caption)

    next(c for c in at.checkbox if c.label == t("example_spec", "en")).set_value(True).run()
    next(b for b in at.button if b.label == t("btn_match", "en")).click().run()
    assert not at.exception and not at.error
    tables = [d.value for d in at.dataframe]
    assert any("Kaolinite" in " ".join(map(str, df.iloc[:, 0])) for df in tables)  # the example is the first (kaolinite) spectrum
