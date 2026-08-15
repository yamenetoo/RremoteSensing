"""
Google Drive access (read-only) and shapefile loading utilities.

These helpers are written for the Google Colab environment. Importing
``google.colab`` outside Colab will raise ``ImportError`` — the import is
deferred into each function so the rest of the package stays importable
in non-Colab environments (e.g. for unit tests).
"""

import os
import subprocess
import zipfile

import geopandas as gpd


def mount_drive_readonly(mountpoint: str = "/content/drive") -> None:
    """
    Mount Google Drive in a Colab runtime.

    Drive is only ever used in this toolkit as a *read* source (e.g. to
    locate a shapefile archive) — nothing in this package writes back to
    Drive. All pipeline outputs are written to local Colab storage.

    Parameters
    ----------
    mountpoint : str
        Local path to mount Drive at (default: ``/content/drive``).
    """
    from google.colab import drive  # noqa: import deferred - Colab only

    drive.mount(mountpoint)
    print("✓ Google Drive mounted (read-only use)")


def find_archive_in_drive(
    keyword: str,
    extensions=(".rar", ".zip"),
    search_root: str = "/content/drive/MyDrive",
    max_depth: int = 5,
):
    """
    Search Google Drive (read-only) for an archive whose filename contains
    ``keyword`` and ends with one of ``extensions``.

    Parameters
    ----------
    keyword : str
        Case-insensitive substring to look for in the filename.
    extensions : tuple of str
        Allowed file extensions.
    search_root : str
        Root folder to search under (default: My Drive root).
    max_depth : int
        Maximum folder depth to recurse into below ``search_root``.

    Returns
    -------
    str or None
        Full path to the first matching file, or ``None`` if not found.
    """
    for root, _dirs, fnames in os.walk(search_root):
        if root.replace(search_root, "").count(os.sep) > max_depth:
            continue
        for f in fnames:
            fl = f.lower()
            if keyword.lower() in fl and fl.endswith(extensions):
                return os.path.join(root, f)
    return None


def extract_shapefile_archive(archive_path: str, extract_dir: str) -> str:
    """
    Extract a ``.zip`` or ``.rar`` archive (containing a shapefile) into a
    local directory, then locate the ``.shp`` file inside it.

    Extracting ``.rar`` archives requires the ``unrar`` command-line tool
    to be installed (``apt-get install unrar`` on Debian/Ubuntu, including
    Colab runtimes).

    Parameters
    ----------
    archive_path : str
        Path to the ``.zip`` or ``.rar`` archive.
    extract_dir : str
        Local folder to extract into (created if missing).

    Returns
    -------
    str
        Path to the extracted ``.shp`` file.

    Raises
    ------
    ValueError
        If the archive extension is not ``.zip`` or ``.rar``.
    FileNotFoundError
        If no ``.shp`` file is found after extraction.
    """
    os.makedirs(extract_dir, exist_ok=True)

    if archive_path.endswith(".rar"):
        subprocess.run(
            ["unrar", "x", "-y", archive_path, extract_dir],
            check=True,
            capture_output=True,
            text=True,
        )
    elif archive_path.endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as z:
            z.extractall(extract_dir)
    else:
        raise ValueError(f"Unsupported archive type: {archive_path}")

    shp_path = None
    for root, _dirs, fnames in os.walk(extract_dir):
        for f in fnames:
            if f.endswith(".shp"):
                shp_path = os.path.join(root, f)
                break

    if shp_path is None:
        raise FileNotFoundError(f"No .shp file found inside {archive_path}")

    print(f"✓ Shapefile extracted to local storage: {shp_path}")
    return shp_path


def load_shapefile(shp_path: str, target_crs: str = "EPSG:4326"):
    """
    Read a shapefile with GeoPandas and reproject it to ``target_crs`` if needed.

    Parameters
    ----------
    shp_path : str
        Path to the ``.shp`` file.
    target_crs : str
        Target coordinate reference system (default: WGS84 lon/lat).

    Returns
    -------
    geopandas.GeoDataFrame
    """
    gdf = gpd.read_file(shp_path)

    if gdf.crs is None:
        gdf = gdf.set_crs(target_crs)
    elif gdf.crs.to_epsg() != int(target_crs.split(":")[1]):
        gdf = gdf.to_crs(target_crs)

    print(f"✓ Shapefile loaded: {len(gdf)} features")
    print("  Columns:", list(gdf.columns))
    return gdf
