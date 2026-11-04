"""Download the USGS Spectral Library Version 7 from USGS ScienceBase.

The remote file list is read from the ScienceBase JSON API at run time, so no
download URL is hard coded. Downloads are resumable, verified by size (and by
checksum when ScienceBase provides one), and extraction is protected against
path traversal ("zip slip").

DOI: https://doi.org/10.5066/F7RR1WDJ
"""
from __future__ import annotations

import hashlib
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Union

import requests

SCIENCEBASE_URL = "https://www.sciencebase.gov"
ITEM_ID = "5807a2a2e4b0841e59e3a18d"  # USGS Spectral Library Version 7 Data
USER_AGENT = "usgs-splib07-python-client"
CHUNK = 1024 * 1024

PathLike = Union[str, Path]


@dataclass
class RemoteFile:
    name: str
    size: Optional[int]
    url: str
    item_title: str = ""
    checksum: Optional[str] = None
    checksum_type: Optional[str] = None

    def __str__(self) -> str:
        mb = f"{self.size / 1e6:,.1f} MB" if self.size else "size unknown"
        return f"{self.name}  ({mb})  [{self.item_title}]"


def _file_entries(item: dict) -> List[RemoteFile]:
    out = []
    for f in item.get("files", []) or []:
        url = f.get("downloadUri") or f.get("url")
        if not url:
            continue
        cs = f.get("checksum") or {}
        out.append(
            RemoteFile(
                name=f.get("name", ""),
                size=f.get("size"),
                url=url,
                item_title=item.get("title", ""),
                checksum=cs.get("value"),
                checksum_type=(cs.get("type") or "").lower() or None,
            )
        )
    return out


def list_remote_files(
    item_id: str = ITEM_ID,
    include_children: bool = True,
    base_url: str = SCIENCEBASE_URL,
    session: Optional[requests.Session] = None,
    timeout: float = 60,
) -> List[RemoteFile]:
    """List downloadable files attached to the data release (and its child items)."""
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", USER_AGENT)
    files: List[RemoteFile] = []

    r = s.get(f"{base_url}/catalog/item/{item_id}", params={"format": "json", "fields": "title,files"}, timeout=timeout)
    r.raise_for_status()
    files += _file_entries(r.json())

    if include_children:
        r = s.get(
            f"{base_url}/catalog/items",
            params={"parentId": item_id, "format": "json", "fields": "title,files", "max": 100},
            timeout=timeout,
        )
        r.raise_for_status()
        for item in r.json().get("items", []):
            files += _file_entries(item)
    return files


def choose_file(files: Sequence[RemoteFile], pattern: str) -> RemoteFile:
    """Pick the zip file whose name matches ``pattern`` (case-insensitive regex search)."""
    rx = re.compile(pattern, re.I)
    hits = [f for f in files if rx.search(f.name) and f.name.lower().endswith(".zip")]
    if not hits:
        names = "\n  ".join(str(f) for f in files)
        raise LookupError(f"No zip file matches {pattern!r}. Available:\n  {names}")
    return hits[0]


def _hash_file(path: Path, kind: str) -> str:
    h = hashlib.new(kind)
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def download_file(
    remote: Union[RemoteFile, str],
    dest_dir: PathLike,
    filename: Optional[str] = None,
    retries: int = 5,
    timeout: float = 60,
    progress: Optional[Callable[[int, Optional[int]], None]] = None,
    session: Optional[requests.Session] = None,
) -> Path:
    """Download one file with resume support. Returns the final path."""
    url = remote.url if isinstance(remote, RemoteFile) else remote
    name = filename or (remote.name if isinstance(remote, RemoteFile) else url.rsplit("/", 1)[-1])
    expected = remote.size if isinstance(remote, RemoteFile) else None
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / name
    part = dest_dir / (name + ".part")

    if final.exists() and (expected is None or final.stat().st_size == expected):
        return final

    s = session or requests.Session()
    s.headers.setdefault("User-Agent", USER_AGENT)

    for attempt in range(1, retries + 1):
        have = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with s.get(url, headers=headers, stream=True, timeout=timeout, allow_redirects=True) as r:
                if r.status_code == 416:  # range not satisfiable: file already complete
                    break
                r.raise_for_status()
                if have and r.status_code != 206:  # server ignored Range -> restart
                    have = 0
                    part.unlink(missing_ok=True)
                total = None
                if "Content-Length" in r.headers:
                    total = int(r.headers["Content-Length"]) + have
                mode = "ab" if have else "wb"
                with open(part, mode) as fh:
                    done = have
                    for block in r.iter_content(CHUNK):
                        if block:
                            fh.write(block)
                            done += len(block)
                            if progress:
                                progress(done, total or expected)
            break
        except (requests.RequestException, OSError):
            if attempt == retries:
                raise
            time.sleep(min(2 ** attempt, 30))

    size = part.stat().st_size
    if expected and size != expected:
        raise IOError(f"Size mismatch for {name}: got {size}, expected {expected}. Re-run to resume.")
    if isinstance(remote, RemoteFile) and remote.checksum and remote.checksum_type in hashlib.algorithms_available:
        got = _hash_file(part, remote.checksum_type)
        if got.lower() != remote.checksum.lower():
            part.unlink(missing_ok=True)
            raise IOError(f"{remote.checksum_type} mismatch for {name}; partial file removed, re-run.")
    part.replace(final)
    return final


def extract_zip(zip_path: PathLike, dest_dir: PathLike, only: Optional[Sequence[str]] = None) -> Path:
    """Safely extract a zip archive.

    ``only`` keeps members whose path contains any of the given substrings
    (for example ``["ASCIIdata"]`` to skip photos and plots).
    """
    dest_dir = Path(dest_dir).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for m in zf.infolist():
            if only and not any(k in m.filename for k in only):
                continue
            target = (dest_dir / m.filename).resolve()
            if dest_dir != target and dest_dir not in target.parents:
                raise ValueError(f"Unsafe path in archive: {m.filename}")
            zf.extract(m, dest_dir)
    return dest_dir


def download_splib07(
    dest: PathLike,
    pattern: str = r"ASCIIdata_splib07b",
    fallback_pattern: str = r"usgs_splib07",
    extract: bool = True,
    only_ascii: bool = True,
    keep_zip: bool = True,
    item_id: str = ITEM_ID,
    base_url: str = SCIENCEBASE_URL,
    progress: Optional[Callable[[int, Optional[int]], None]] = None,
) -> Path:
    """Download (and extract) the library; returns the directory to pass to ``build_library``.

    By default the smaller oversampled ASCII archive (``ASCIIdata_splib07b``) is
    preferred. If it is not found on ScienceBase the full ``usgs_splib07.zip`` (~5 GB)
    is used instead.
    """
    dest = Path(dest)
    files = list_remote_files(item_id=item_id, base_url=base_url)
    try:
        chosen = choose_file(files, pattern)
    except LookupError:
        chosen = choose_file(files, fallback_pattern)
    print(f"Selected: {chosen}")
    zpath = download_file(chosen, dest / "downloads", progress=progress)
    if not extract:
        return zpath
    out = dest / "data"
    extract_zip(zpath, out, only=["ASCIIdata"] if only_ascii else None)
    if not keep_zip:
        zpath.unlink(missing_ok=True)
    return out
