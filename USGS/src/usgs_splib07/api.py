"""One-call access: :func:`get_library` downloads (once), builds (once) and returns a ready library."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Sequence, Union

from .download import download_splib07
from .library import SpectralLibrary, build_library

PathLike = Union[str, Path]


def default_home() -> Path:
    """Folder where data and built libraries are cached: ``$USGS_SPLIB07_HOME`` or ``~/.usgs_splib07``."""
    return Path(os.environ.get("USGS_SPLIB07_HOME", "~/.usgs_splib07")).expanduser()


def get_library(
    home: Optional[PathLike] = None,
    chapters: Optional[Sequence[str]] = "MS",
    kinds: Optional[Sequence[str]] = ("AREF",),
    library: str = "splib07b",
    start: float = 350.0,
    stop: float = 2500.0,
    step: float = 5.0,
    refresh: bool = False,
    **download_kwargs,
) -> SpectralLibrary:
    """Return a :class:`SpectralLibrary`, downloading and building it only the first time.

    The raw data is stored in ``<home>/data`` and the built library in ``<home>/libraries/*.npz``;
    later calls with the same arguments just load the ``.npz``. ``chapters`` are letters from
    ``MSCLOAV`` (minerals, soils, coatings, liquids, organics, artificial, vegetation; None = all).
    Extra keyword arguments (``pattern``, ``base_url``, ...) go to :func:`download_splib07`.
    ``refresh=True`` rebuilds the library from the already downloaded data.
    """
    home = Path(home).expanduser() if home else default_home()
    ch = "".join(sorted(chapters)).upper() if chapters else "all"
    kd = "+".join(sorted(k.upper() for k in kinds)) if kinds else "all"
    cache = home / "libraries" / f"{library}_{ch}_{kd}_{start:g}-{stop:g}-{step:g}nm.npz"
    if cache.exists() and not refresh:
        return SpectralLibrary.load(cache)
    root = download_splib07(home / "data", **download_kwargs)
    lib = build_library(root, library, list(chapters) if chapters else None, kinds, start=start, stop=stop, step=step)
    lib.save(cache)
    return lib
