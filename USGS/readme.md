# USGS Splib07 Processor

A Python package that transforms the **USGS Spectral Library Version 7** dataset into callable interpolation functions \(P_m(\lambda)\). Purpose‑built for remote sensing, spectroscopy, spectral unmixing, and radiative‑transfer modelling.

## ✨ Features

- **Automatic ingestion** – locates and parses USGS Splib07 CSV index files.
- **Robust preprocessing** – edge trimming, negative reflectance filtering, unit conversion (μm ↔ nm).
- **Vectorized interpolation** – powered by `scipy.interpolate.interp1d`.
- **Batch processing** – progress tracking and pickle serialisation for fast reloading.
- **Clean, typed API** – designed for seamless integration into scientific workflows.

## 🛠 Installation

```bash
# Editable install (recommended during development)
pip install -e .

# Or install dependencies manually
pip install -r requirements.txt
```

## 📥 Data Setup

### 1. Download the USGS Spectral Library v7.0

The complete dataset (`usgs_splib07.zip`, ~5.1 GB) is publicly hosted by the U.S. Geological Survey.

| Source                     | Link                                                                                                                      |
|----------------------------|---------------------------------------------------------------------------------------------------------------------------|
| **DOI (recommended)**      | [https://dx.doi.org/10.5066/F7RR1WDJ](https://dx.doi.org/10.5066/F7RR1WDJ)                                               |
| **ScienceBase Catalog**    | [https://www.sciencebase.gov/catalog/item/5807a2a2e4b0841e59e3a18d](https://www.sciencebase.gov/catalog/item/5807a2a2e4b0841e59e3a18d) |
| **USGS Spectral Lab**      | [https://speclab.cr.usgs.gov/spectral-lib.html](https://speclab.cr.usgs.gov/spectral-lib.html)                             |

**Steps:**
1. Visit one of the links above and download `usgs_splib07.zip`.
2. Extract the archive to a location of your choice, e.g.:
   ```
   D:\usgs_splib07\
   ├── extracted_tables/
   ├── splib07a/
   ├── splib07b/
   └── ...
   ```

> 💡 **Tip**: The package expects CSV index files (`Chapter_1.csv` … `Chapter_7.csv`) inside a folder named `extracted_tables/`. If your download does not contain these CSVs, you will need to generate them or adjust the `csv_dir` parameter accordingly.

---

### 2. Configure Paths Inside the CSV Files

By default, the CSV index files reference spectral data using absolute paths that start with `D:\`. If your library is stored elsewhere, choose one of the following methods.

#### ✅ Option A: Use the `base_path` Argument (Recommended)

When calling `build_material_library()`, supply the actual installation root:

```python
build_material_library(
    csv_dir=r"C:\my_data\usgs_splib07\extracted_tables",
    output_path=r"C:\my_data\material_functions.pkl",
    base_path=r"C:\my_data\usgs_splib07",   # Overrides the default 'D:\' prefix
    plot=False,
    column_indices=[0, 2, 4]
)
```

This keeps the original CSV files untouched.

#### ✏️ Option B: Edit the CSV Files Directly

1. Open each `Chapter_*.csv` in a text editor or spreadsheet.
2. Locate the columns that contain file paths (typically columns 2 and 4 – reflectance and wavelength paths).
3. Replace the old prefix (e.g., `D:\`) with your actual base path.

A bulk‑update script is also provided:

```python
import pandas as pd
from pathlib import Path

csv_dir = Path(r"C:\my_data\usgs_splib07\extracted_tables")
new_base = r"C:\my_data\usgs_splib07"

for csv_file in csv_dir.glob("Chapter_*.csv"):
    df = pd.read_csv(csv_file)
    # Adjust column indices if your CSV layout differs
    for col in [2, 4]:
        if col < len(df.columns):
            df.iloc[:, col] = df.iloc[:, col].str.replace(
                r"D:\\", f"{new_base}\\", regex=False
            )
    df.to_csv(csv_file, index=False)
    print(f"✓ Updated {csv_file.name}")
```

> ⚠️ **Warning**: Back up your CSV files before performing any bulk edits.

---

### 3. Verify the Setup

Run a quick test to confirm everything is correctly configured:

```python
from usgs_splib07_processor import process_spectrum
import pandas as pd

df = pd.read_csv(r"C:\my_data\usgs_splib07\extracted_tables\Chapter_1.csv")
df = df.iloc[:, [0, 2, 4]]          # [name, reflectance_path, wavelength_path]

name, spectrum = process_spectrum(
    df.iloc[0],
    plot=True,
    base_path=r"C:\my_data\usgs_splib07"
)

print(f"✓ Successfully loaded: {name}")
print(f"  Spectrum shape: {spectrum.shape}")
```

If a plot appears and no exceptions are raised, your data is ready. 🎉

---

> 📌 **Library Structure**  
> USGS Splib07 is divided into 7 chapters:  
> `Chapter_1` – Minerals (M)  
> `Chapter_2` – Soils & Mixtures (S)  
> `Chapter_3` – Coatings (C)  
> `Chapter_4` – Liquids (L)  
> `Chapter_5` – Organics (O)  
> `Chapter_6` – Artificial Materials (A)  
> `Chapter_7` – Vegetation (V)  
> Make sure all relevant `Chapter_*.csv` files are present in your `csv_dir`.

**Data citation**  
Kokaly, R.F., Clark, R.N., Swayze, G.A., et al. (2017). *USGS Spectral Library Version 7*. U.S. Geological Survey Data Series 1035. [https://doi.org/10.3133/ds1035](https://doi.org/10.3133/ds1035)

---

## 🚀 Quick Start

### Build the Material Library

```python
from usgs_splib07_processor import build_material_library

build_material_library(
    csv_dir=r"D:\usgs_splib07\extracted_tables",
    output_path=r"D:\usgs_splib07\material_functions.pkl",
    base_path=r"D:\usgs_splib07",      # Optional: override if needed
    plot=False,
    column_indices=[0, 2, 4]           # [name, reflectance_path, wavelength_path]
)
```

### Load and Query a Spectrum

```python
from usgs_splib07_processor import load_material_library

lib = load_material_library("material_functions.pkl")

material_name = "Calcite_HS188.3B"
if material_name in lib["name"]:
    idx = lib["name"].index(material_name)
    P_m = lib["fn"][idx]               # Callable interpolation function

    # Query reflectance at a single wavelength (nm)
    print(f"Reflectance at 500 nm: {P_m(500.0):.4f}")

    # Or at multiple wavelengths
    wavelengths = [450, 550, 650]
    print(f"Reflectance at {wavelengths} nm: {P_m(wavelengths)}")
else:
    print(f"Material '{material_name}' not found in library.")
```
