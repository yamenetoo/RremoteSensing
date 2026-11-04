"""Small helpers shared by the whole package."""
from __future__ import annotations

import logging
import re
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("geedownload")
logger.addHandler(logging.NullHandler())


def set_verbose(level: int = logging.INFO) -> None:
    """Print progress messages (call once in a notebook or script)."""
    if not any(type(h) is logging.StreamHandler for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


def slugify(text: str, default: str = "area", max_len: int = 60) -> str:
    """ASCII-safe file name from any text (Arabic/Persian names fall back to `default`)."""
    norm = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "_", norm).strip("_").lower()
    return slug[:max_len] or default


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def file_size_mb(path) -> float:
    return Path(path).stat().st_size / (1024 * 1024)


def zip_dir(folder, zip_path) -> Path:
    """Zip `folder` into `zip_path` (the archive itself is never included)."""
    folder, zip_path = Path(folder), Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(folder.rglob("*")):
            if p.is_file() and p.resolve() != zip_path.resolve():
                zf.write(p, p.relative_to(folder))
    return zip_path
