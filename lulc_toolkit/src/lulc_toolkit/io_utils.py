"""Local-storage packaging and download helpers (Colab-oriented)."""

import os
import zipfile


def zip_and_download(file_list, zip_path: str) -> str:
    """
    Zip a list of local files and, if running in Colab, trigger a browser
    download of the archive. Outside Colab, the zip is simply created and
    its path returned.

    Parameters
    ----------
    file_list : list of str
        Paths of files to include in the zip.
    zip_path : str
        Output path for the zip archive.

    Returns
    -------
    str
        The path to the created zip archive.
    """
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in file_list:
            zf.write(f, os.path.basename(f))
    print(f"✓ Zipped {len(file_list)} files into: {zip_path}")

    try:
        from google.colab import files  # noqa: import deferred - Colab only

        files.download(zip_path)
    except ImportError:
        print("  (not running in Colab - skipping browser download)")

    return zip_path
