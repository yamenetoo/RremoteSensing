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
```
```markdown
## 📥 Data Setup: Downloading & Configuring USGS Splib07

### 1️⃣ Download the USGS Spectral Library v7.0

The full USGS Spectral Library Version 7 dataset (`usgs_splib07.zip`, ~5.1 GB) is publicly available from the U.S. Geological Survey.

| Source | Link |
|--------|------|
| **DOI (Recommended)** | [https://dx.doi.org/10.5066/F7RR1WDJ](https://dx.doi.org/10.5066/F7RR1WDJ) |
| **ScienceBase Catalog** | [https://www.sciencebase.gov/catalog/item/5807a2a2e4b0841e59e3a18d](https://www.sciencebase.gov/catalog/item/5807a2a2e4b0841e59e3a18d) |
| **USGS Spectral Lab** | [https://speclab.cr.usgs.gov/spectral-lib.html](https://speclab.cr.usgs.gov/spectral-lib.html) |

**Steps:**
1. Visit one of the links above.
2. Download the file: **`usgs_splib07.zip`** (~5.1 GB).
3. Extract the archive to your preferred location. Example:
   ```
   D:\usgs_splib07\
   ├── extracted_tables/
   ├── splib07a/
   ├── splib07b/
   └── ...
   ```

> 💡 **Tip**: The package expects the extracted data to be organized with CSV index files (e.g., `Chapter_1.csv`, `Chapter_2.csv`, etc.) in a folder like `extracted_tables/`. If your download doesn't include these, you may need to generate them or adjust the `csv_dir` path accordingly.

---

### 2️⃣ Configure Paths in `Chapter_*.csv` Files

The CSV index files reference spectral data using absolute paths. By default, this package assumes the library is installed at:

```
D:\usgs_splib07\
```

If you extracted the data to a **different location**, you have two options:

#### ✅ Option A: Use the `base_path` Parameter (Recommended)

When calling `build_material_library()`, simply specify your actual installation path:

```python
build_material_library(
    csv_dir=r"C:\my_data\usgs_splib07\extracted_tables",
    output_path=r"C:\my_data\material_functions.pkl",
    base_path=r"C:\my_data\usgs_splib07",  # ← Override default D:\ path
    plot=False,
    column_indices=[0, 2, 4]
)
```

This avoids modifying the original CSV files.

#### ✏️ Option B: Edit the CSV Files Directly

If you prefer to update the CSVs permanently:

1. Open each `Chapter_*.csv` file in a text editor or spreadsheet program.
2. Locate the columns containing file paths (typically columns 2 and 4: reflectance and wavelength paths).
3. Replace the hardcoded prefix `D:\` with your actual base path.

**Example using Python (bulk replace):**
```python
import pandas as pd
from pathlib import Path

csv_dir = Path(r"C:\my_data\usgs_splib07\extracted_tables")
new_base = r"C:\my_data\usgs_splib07"

for csv_file in csv_dir.glob("Chapter_*.csv"):
    df = pd.read_csv(csv_file)
    # Update path columns (adjust indices if your CSV structure differs)
    for col in [2, 4]:
        if col < len(df.columns):
            df.iloc[:, col] = df.iloc[:, col].str.replace(r"D:\\", f"{new_base}\\", regex=False)
    df.to_csv(csv_file, index=False)
    print(f"✓ Updated {csv_file.name}")
```

> ⚠️ **Warning**: Always back up your CSV files before performing bulk edits.

---

### 🔍 Verify Your Setup

After downloading and configuring paths, run a quick test:

```python
from usgs_splib07_processor import process_spectrum
import pandas as pd

# Load a sample CSV
df = pd.read_csv(r"C:\my_data\usgs_splib07\extracted_tables\Chapter_1.csv")
df = df.iloc[:, [0, 2, 4]]  # [name, reflectance_path, wavelength_path]

# Process the first row
name, spectrum = process_spectrum(
    df.iloc[0], 
    plot=True, 
    base_path=r"C:\my_data\usgs_splib07"
)

print(f"✓ Successfully loaded: {name}")
print(f"  Spectrum shape: {spectrum.shape}")
```

If a plot appears and no errors are raised, your data is correctly configured! 🎉

---

> 📌 **Note**: The USGS Splib07 library is organized into 7 chapters:
> - `Chapter_1.csv` → Minerals (M)
> - `Chapter_2.csv` → Soils & Mixtures (S)
> - `Chapter_3.csv` → Coatings (C)
> - `Chapter_4.csv` → Liquids (L)
> - `Chapter_5.csv` → Organics (O)
> - `Chapter_6.csv` → Artificial Materials (A)
> - `Chapter_7.csv` → Vegetation (V)
>
> Ensure all relevant `Chapter_*.csv` files are present in your `csv_dir` for complete library processing.

---

*Data citation*:  
Kokaly, R.F., Clark, R.N., Swayze, G.A., et al. (2017). *USGS Spectral Library Version 7*. U.S. Geological Survey Data Series 1035. https://doi.org/10.3133/ds1035
```
## Quick Start
###  Build the Material Library
```
from usgs_splib07_processor import build_material_library

build_material_library(
    csv_dir=r"D:\usgs_splib07\extracted_tables",
    output_path=r"D:\usgs_splib07\material_functions.pkl",
    base_path=r"D:\usgs_splib07",  # Optional: overrides hardcoded D:\ paths
    plot=False,
    column_indices=[0, 2, 4]       # [name, reflectance_path, wavelength_path]
)
```

### Load & Query a Spectrum
```
from usgs_splib07_processor import load_material_library

# Load the pre-processed library
lib = load_material_library("material_functions.pkl")

# Find a material by name (exact match)
material_name = "Calcite_HS188.3B"
if material_name in lib["name"]:
    idx = lib["name"].index(material_name)
    P_m = lib["fn"][idx]  # Callable interpolation function
    
    # Query reflectance at specific wavelengths (in nm by default)
    print(f"Reflectance at 500 nm: {P_m(500.0):.4f}")
    print(f"Reflectance at [450, 550, 650] nm: {P_m([450, 550, 650])}")
else:
    print(f"Material '{material_name}' not found in library.")
```
 
 
