"""Graphical interface (English, Arabic, Persian). Start it with ``splib07 gui`` or :func:`launch_gui`."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Union


def launch_gui(port: int = 8501, library: Optional[Union[str, Path]] = None, lang: str = "en", open_browser: bool = True) -> int:
    """Start the web interface in your browser (needs ``pip install "usgs-splib07[gui]"``). Returns the exit code.

    ``library`` is an optional saved ``.npz`` library to open at start; ``lang`` is ``en``, ``ar`` or ``fa``.
    """
    try:
        import streamlit  # noqa: F401
    except ImportError as e:
        raise ImportError('The graphical interface needs Streamlit: pip install "usgs-splib07[gui]"') from e
    env = dict(os.environ)
    env["USGS_SPLIB07_GUI_LANG"] = lang
    if library:
        env["USGS_SPLIB07_GUI_LIB"] = str(Path(library).expanduser().resolve())
    app = Path(__file__).with_name("app.py")
    cmd = [sys.executable, "-m", "streamlit", "run", str(app), "--server.port", str(port),
           "--server.headless", "false" if open_browser else "true", "--browser.gatherUsageStats", "false", "--client.toolbarMode", "minimal"]
    return subprocess.call(cmd, env=env)
