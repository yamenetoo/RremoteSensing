"""usgs_splib07 - get the USGS Spectral Library Version 7 and preprocess its spectra.

    import usgs_splib07 as splib
    lib = splib.get_library()                       # downloads once, then loads from cache
    s2 = lib.to_sensor("sentinel2a").normalized()   # spectra as a sensor would see them

Author: Mohamad Yamen Al-Mohamad <yamenmohamad@tabrizu.ac.ir>

Data: Kokaly, R.F., et al., 2017, USGS Spectral Library Version 7,
U.S. Geological Survey Data Series 1035, https://doi.org/10.3133/ds1035
This package is an independent tool and is not affiliated with or endorsed by the USGS.
"""
from . import preprocess
from .api import default_home, get_library
from .catalog import build_catalog, read_values
from .demo import demo_library
from .download import download_splib07, list_remote_files
from .functions import catalogue_markdown, list_functions
from .library import SpectralLibrary, build_library
from .sensors import SENSORS, Band, Sensor, get_sensor, register_sensor, sensor_from_wavelengths, subset_sensor

__version__ = "3.0.0"
__author__ = "Mohamad Yamen Al-Mohamad"
__email__ = "yamenmohamad@tabrizu.ac.ir"
__all__ = [
    "get_library", "default_home", "download_splib07", "list_remote_files", "build_library", "build_catalog", "read_values",
    "SpectralLibrary", "preprocess", "SENSORS", "Sensor", "Band", "get_sensor", "register_sensor",
    "sensor_from_wavelengths", "subset_sensor", "demo_library", "list_functions", "catalogue_markdown",
]
