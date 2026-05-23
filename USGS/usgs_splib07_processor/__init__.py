"""USGS Spectral Library v7.0 Processor Package."""
from .core import process_spectrum, create_material_interp_function
from .builder import build_material_library, load_material_library

__version__ = "1.0.0"
__all__ = [
    "process_spectrum",
    "create_material_interp_function",
    "build_material_library",
    "load_material_library"
]
