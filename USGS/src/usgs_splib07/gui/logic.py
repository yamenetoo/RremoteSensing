"""GUI logic without any GUI code, so it can be tested: preprocessing steps and reading a pasted/uploaded spectrum."""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

from ..sensors import sensor_from_wavelengths

# Arabic-Indic and Persian digits and their decimal separators -> ASCII
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")
_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

STEP_KEYS = ["clip", "smooth", "derivative", "continuum", "snv", "normalize", "to_sensor"]
NORMALIZE_METHODS = ["l2", "max", "minmax", "area"]


def parse_spectrum(source: Union[str, bytes]) -> Tuple[np.ndarray, np.ndarray]:
    """Read ``wavelength, reflectance`` pairs from text (comma, semicolon, tab or space separated).

    Header lines are skipped, Arabic/Persian digits are accepted, and wavelengths below 50 are taken as
    micrometres and converted to nm. Returns (wavelengths in nm sorted ascending, values).
    """
    text = source.decode("utf-8-sig", errors="replace") if isinstance(source, bytes) else source
    text = text.translate(_DIGITS)
    rows: List[Tuple[float, float]] = []
    for line in text.splitlines():
        parts = [p for p in re.split(r"[,;\t ]+", line.strip()) if p]
        if len(parts) < 2:
            continue
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except ValueError:
            continue  # header or junk line
    if len(rows) < 3:
        raise ValueError("need at least 3 lines with two numbers each (wavelength, reflectance)")
    arr = np.array(rows, float)
    wl, y = arr[:, 0], arr[:, 1]
    if np.nanmax(wl) < 50:
        wl = wl * 1000.0
    order = np.argsort(wl)
    wl, y = wl[order], y[order]
    if np.any(np.diff(wl) <= 0):
        raise ValueError("wavelengths must be distinct")
    return wl, y


def validate_params(selected: List[str], p: Dict) -> Optional[str]:
    """Return a message key for the first problem in the step parameters, else None."""
    for key in ("smooth", "derivative"):
        if key in selected:
            w, poly = int(p.get("window", 11)), int(p.get("poly", 3))
            if w % 2 == 0 or w <= poly:
                return "bad_window"
    if "to_sensor" in selected and p.get("sensor") == "custom":
        if not (p["start"] < p["stop"] and p["spacing"] > 0):
            return "bad_grid"
    return None


def build_steps(selected: List[str], p: Dict) -> list:
    """Turn the ticked steps (in order) and their parameters into a ``SpectralLibrary.pipeline`` list."""
    steps: list = []
    for key in selected:
        if key == "clip":
            steps.append(("clip", {"lo": 0.0}))
        elif key == "smooth":
            steps.append(("smooth", {"window": int(p["window"]), "poly": int(p["poly"])}))
        elif key == "derivative":
            steps.append(("derivative", {"order": int(p["order"]), "window": int(p["window"]), "poly": int(p["poly"])}))
        elif key == "continuum":
            steps.append("continuum_removed")
        elif key == "snv":
            steps.append("snv")
        elif key == "normalize":
            steps.append(("normalized", {"method": p["method"]}))
        elif key == "to_sensor":
            if p["sensor"] == "custom":
                centres = np.arange(p["start"], p["stop"] + p["spacing"] / 2, p["spacing"])
                sensor = sensor_from_wavelengths("custom", centres, p["fwhm"])
            else:
                sensor = p["sensor"]
            steps.append(("to_sensor", {"sensor": sensor}))
        else:
            raise KeyError(key)
    return steps
