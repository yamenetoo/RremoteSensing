# USGS Splib07 Processor

A Python package to process **USGS Spectral Library v7.0** material data into callable interpolation functions $P_m(\lambda)$. Designed for remote sensing, spectroscopy, spectral unmixing, and radiative transfer modeling.

## ✨ Features
- 🔍 Automatic path resolution & CSV parsing for USGS Splib07 tables
- 🧹 Robust preprocessing: edge trimming, negative reflectance filtering, unit conversion (μm ↔ nm)
- 📈 Vectorized interpolation via `scipy.interpolate.interp1d`
- 📦 Batch processing with progress tracking & pickle serialization
- 🔌 Clean, typed API for easy integration into scientific pipelines

## 🛠 Installation
```bash
# Install in development mode
pip install -e .

# Or install dependencies manually
pip install -r requirements.txt


## Quick Start
###  Build the Material Library

from usgs_splib07_processor import build_material_library

build_material_library(
    csv_dir=r"D:\usgs_splib07\extracted_tables",
    output_path=r"D:\usgs_splib07\material_functions.pkl",
    base_path=r"D:\usgs_splib07",  # Optional: overrides hardcoded D:\ paths
    plot=False,
    column_indices=[0, 2, 4]       # [name, reflectance_path, wavelength_path]
)
