"""usgs_splib07 - download, catalog and preprocess the USGS Spectral Library Version 7.

Data: Kokaly, R.F., et al., 2017, USGS Spectral Library Version 7,
U.S. Geological Survey Data Series 1035, https://doi.org/10.3133/ds1035
"""
from . import preprocess
from .catalog import build_catalog
from .download import download_splib07, list_remote_files
from .imagery import Image, MatchResult, match_image
from .library import SpectralLibrary, build_library
from .sensors import SENSORS, Band, Sensor, get_sensor, register_sensor, sensor_from_wavelengths, subset_sensor

__version__ = "2.1.0"
__all__ = [
    "SpectralLibrary", "build_library", "build_catalog", "download_splib07", "list_remote_files",
    "preprocess", "SENSORS", "Sensor", "Band", "get_sensor", "register_sensor", "sensor_from_wavelengths",
    "subset_sensor", "Image", "MatchResult", "match_image",
]
