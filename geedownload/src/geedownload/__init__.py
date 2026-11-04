"""geedownload: search any area by name, save its boundary as a shapefile, download satellite data
(Sentinel, Landsat, MODIS, DEM, ...) from Google Earth Engine, draw cartopy maps, and serve it all as a REST API."""

__version__ = "0.2.0"
__author__ = "M. Yamen AL-Mohamad"
__email__ = "yamenmohamad@tabrizu.ac.ir"

AUTHOR = {
    "name": "M. Yamen AL-Mohamad",
    "full_name": "Mohamad Yamen Al-Mohamad",
    "arabic_name": "محمد يامن المحمد",
    "affiliation": "Department of Statistics, University of Tabriz, Tabriz, Iran",
    "email": "yamenmohamad@tabrizu.ac.ir",
    "github": "https://github.com/yamenetoo",
    "website": "https://yamenetoo.github.io",
    "scholar": "https://scholar.google.com/citations?user=un_6SQwAAAAJ",
    "orcid": "https://orcid.org/0009-0009-1665-7203",
}


def about() -> str:
    """Return (and print) the package description with the author's contact details."""
    text = (f"geedownload {__version__}\n"
            f"Author : {AUTHOR['name']} ({AUTHOR['arabic_name']})\n"
            f"Affil. : {AUTHOR['affiliation']}\n"
            f"Email  : {AUTHOR['email']}\n"
            f"GitHub : {AUTHOR['github']}\n"
            f"Web    : {AUTHOR['website']}\n"
            f"Scholar: {AUTHOR['scholar']}\n"
            f"ORCID  : {AUTHOR['orcid']}")
    print(text)
    return text


from .aoi import AOI, resolve_aoi  # noqa: E402
from .auth import init_ee  # noqa: E402
from .boundary import read_boundary, save_boundary  # noqa: E402
from .catalog import Dataset, get_dataset, list_datasets, register_dataset  # noqa: E402
from .errors import AreaNotFound, DownloadError, GeeDownloadError, NoImagesError  # noqa: E402
from .geocode import Place, search_area  # noqa: E402
from .maps import country_aoi, plot_area, plot_map  # noqa: E402
from .pipeline import DownloadResult, download_area, search_and_save  # noqa: E402
from .reference import function_catalogue  # noqa: E402
from .utils import set_verbose  # noqa: E402

__all__ = [
    "AOI", "resolve_aoi", "init_ee", "read_boundary", "save_boundary", "Dataset", "get_dataset",
    "list_datasets", "register_dataset", "AreaNotFound", "DownloadError", "GeeDownloadError", "NoImagesError",
    "Place", "search_area", "country_aoi", "plot_area", "plot_map", "DownloadResult", "download_area",
    "search_and_save", "function_catalogue", "set_verbose", "about", "AUTHOR",
]
