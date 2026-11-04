import json
import re
from pathlib import Path

import pytest

GUI = Path(__file__).parent.parent / "src" / "geedownload" / "assets" / "gui"
I18N = json.loads((GUI / "i18n.json").read_text(encoding="utf-8"))
HTML = (GUI / "index.html").read_text(encoding="utf-8")


def test_same_keys_in_three_languages():
    assert set(I18N) == {"ar", "fa", "en"}
    assert set(I18N["ar"]) == set(I18N["fa"]) == set(I18N["en"])
    assert all(v.strip() for lg in I18N.values() for v in lg.values())


def test_html_keys_exist():
    used = set(re.findall(r'data-i18n(?:-ph)?="([a-z0-9_]+)"', HTML)) | set(re.findall(r'\bt\("([a-z0-9_]+)"\)', HTML))
    used |= {"st_" + s for s in ("queued", "running", "done", "failed")}
    assert used - set(I18N["en"]) == set()


def test_letter_forms():
    # Arabic uses ي/ك, Persian uses ی/ک
    assert not re.search("[یک]", "".join(I18N["ar"].values()))
    assert not re.search("[يك]", "".join(I18N["fa"].values()))


def test_gui_route(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from geedownload import api

    monkeypatch.setenv("GEEDOWNLOAD_WORKDIR", str(tmp_path))
    r = TestClient(api.create_app()).get("/app")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "/*I18N_JSON*/" not in r.text and "فارسی" in r.text and "جستجو" in r.text


def test_tk_gui_switches_languages():
    """Runs in a subprocess: Tk must be created and destroyed in one process without other threads around."""
    import subprocess
    import sys

    pytest.importorskip("tkinter")
    code = (
        "import sys, tkinter\n"
        "from geedownload.gui import App\n"
        "try:\n    app = App('ar')\nexcept tkinter.TclError:\n    sys.exit(77)\n"
        "for lang in ('fa', 'en', 'ar'):\n    app.set_lang(lang); app.update()\n"
        "assert len(app.nb.tabs()) == 4 and app.lang == 'ar'\n"
        "app.destroy()\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    if r.returncode == 77:
        pytest.skip("no display available")
    assert r.returncode == 0, r.stderr
