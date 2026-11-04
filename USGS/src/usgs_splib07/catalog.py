"""Scan an extracted USGS Splib07 ``ASCIIdata`` tree and read individual spectra.

No CSV index and no hard-coded drive letters are needed: the catalog is built
from the file system, so it works the same on Windows, Linux and macOS.

Expected layout (as in ``usgs_splib07.zip``)::

    ASCIIdata/
        ASCIIdata_splib07b/
            ChapterM_Minerals/splib07b_<Material>_<Sample>_<Spectrometer>_<Kind>.txt
            splib07b_Wavelengths_<...>.txt
            splib07b_Bandpass_(FWHM)_<...>.txt
            errorbars/...

Spectrum files have one title line followed by one value per line; deleted
channels are flagged with -1.23e34. Wavelengths are in micrometres.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

PathLike = Union[str, Path]
DELETED = -1.23e34
CHAPTERS = {
    "M": "Minerals", "S": "Soils and mixtures", "C": "Coatings", "L": "Liquids",
    "O": "Organics", "A": "Artificial", "V": "Vegetation",
}
_FAMILY_HINTS = (("BECK", "BECK"), ("ASD", "ASD"), ("NIC", "NIC"), ("AV", "AVIRIS"))


def find_library_dir(root: PathLike, library: str = "splib07b") -> Path:
    """Locate ``ASCIIdata_<library>`` below ``root`` (root may also be the library dir itself)."""
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {root}")
    if root.name == f"ASCIIdata_{library}":
        return root
    hits = sorted(p for p in root.rglob(f"ASCIIdata_{library}") if p.is_dir())
    if not hits:
        found = sorted({p.name for p in root.rglob("ASCIIdata_*") if p.is_dir()})
        raise FileNotFoundError(
            f"ASCIIdata_{library} not found under {root}. Libraries found: {found or 'none'}"
        )
    return hits[0]


def _family(spec_code: str) -> str:
    for hint, fam in _FAMILY_HINTS:
        if spec_code.upper().startswith(hint):
            return fam
    return spec_code.upper()


def parse_filename(path: Path, lib_tag: str) -> Optional[dict]:
    """Split ``<lib>_<Material>_<Sample>_<Spectrometer>_<Kind>.txt`` into fields."""
    stem = path.stem
    prefix = lib_tag + "_"
    if stem.startswith(prefix):
        stem = stem[len(prefix):]
    parts = stem.split("_")
    if len(parts) < 3:
        return None
    kind, spec = parts[-1], parts[-2]
    sample = parts[-3] if len(parts) >= 4 else ""
    material = "_".join(parts[:-3]) if len(parts) >= 4 else parts[0]
    return {
        "material": material, "sample": sample, "spectrometer": spec,
        "family": _family(spec), "kind": kind,
    }


def build_catalog(
    root: PathLike,
    library: str = "splib07b",
    chapters: Optional[Sequence[str]] = None,
    kinds: Optional[Sequence[str]] = ("AREF",),
    families: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Return a DataFrame describing every spectrum file (no spectra are read yet).

    Parameters
    ----------
    chapters : letters from ``MSCLOAV`` (None = all).
    kinds : measurement kinds to keep, e.g. ``("AREF",)`` absolute reflectance
        (default), ``("AREF", "RREF")``, or None for everything.
    families : spectrometer families to keep: BECK, ASD, NIC, AVIRIS (None = all).
    """
    lib_dir = find_library_dir(root, library)
    lib_tag = lib_dir.name.replace("ASCIIdata_", "", 1)
    want_ch = {c.upper() for c in chapters} if chapters else None
    want_kind = {k.upper() for k in kinds} if kinds else None
    want_fam = {f.upper() for f in families} if families else None

    rows = []
    for ch_dir in sorted(p for p in lib_dir.iterdir() if p.is_dir() and p.name.startswith("Chapter")):
        letter = ch_dir.name[len("Chapter"):][:1].upper()
        if want_ch and letter not in want_ch:
            continue
        for f in sorted(ch_dir.glob("*.txt")):
            info = parse_filename(f, lib_tag)
            if info is None:
                continue
            if want_kind and info["kind"].upper() not in want_kind:
                continue
            if want_fam and info["family"] not in want_fam:
                continue
            rows.append({
                "library": lib_tag, "chapter": letter, "chapter_name": CHAPTERS.get(letter, ch_dir.name),
                **info, "path": str(f),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        raise FileNotFoundError(f"No spectrum files matched in {lib_dir}")
    df.insert(0, "name", df["material"] + "_" + df["sample"] + "_" + df["spectrometer"] + "_" + df["kind"])
    return df.reset_index(drop=True)


def read_values(path: PathLike) -> np.ndarray:
    """Read a one-column USGS text file (title line skipped). Deleted channels become NaN."""
    arr = np.loadtxt(path, skiprows=1, dtype=np.float64, ndmin=1)
    arr[arr < -1e30] = np.nan
    return arr


def _wavelength_files(lib_dir: Path) -> List[Path]:
    files = [p for p in lib_dir.glob("*Wavelengths*.txt")]
    if not files:
        files = [p for p in lib_dir.rglob("*Wavelengths*.txt")]
    return sorted(files)


class WavelengthResolver:
    """Find the wavelength vector (nm) that belongs to a spectrum.

    The spectrometer family narrows the candidates by file name and the number
    of channels must match, which also copes with the oversampled/convolved libraries.
    """

    def __init__(self, lib_dir: Path):
        self._files = _wavelength_files(lib_dir)
        if not self._files:
            raise FileNotFoundError(f"No *Wavelengths*.txt files in {lib_dir}")
        self._cache: Dict[Path, np.ndarray] = {}

    def _load(self, p: Path) -> np.ndarray:
        if p not in self._cache:
            w = read_values(p)
            self._cache[p] = w * 1000.0  # micrometres -> nanometres
        return self._cache[p]

    def resolve(self, family: str, n: int) -> Optional[np.ndarray]:
        hinted = [p for p in self._files if family.lower() in p.name.lower()]
        for pool in (hinted, self._files):
            for p in pool:
                w = self._load(p)
                if len(w) == n:
                    return w
        return None


@dataclass
class RawSpectrum:
    wavelengths: np.ndarray  # nm
    values: np.ndarray  # NaN where channel was deleted


def load_spectra(
    catalog: pd.DataFrame,
    root: PathLike,
    library: str = "splib07b",
    workers: int = 8,
) -> Tuple[pd.DataFrame, List[RawSpectrum]]:
    """Read every catalogued spectrum. Rows whose wavelengths cannot be matched are dropped."""
    lib_dir = find_library_dir(root, library)
    resolver = WavelengthResolver(lib_dir)

    def one(row) -> Optional[RawSpectrum]:
        try:
            v = read_values(row.path)
        except Exception:
            return None
        w = resolver.resolve(row.family, len(v))
        if w is None:
            return None
        order = np.argsort(w)
        return RawSpectrum(w[order], v[order])

    rows = list(catalog.itertuples(index=False))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(one, rows))
    keep = [i for i, r in enumerate(results) if r is not None]
    cat = catalog.iloc[keep].reset_index(drop=True)
    return cat, [results[i] for i in keep]
