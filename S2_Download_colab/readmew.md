# Sentinel‑2 Batch Download from Google Earth Engine

This module provides a set of functions to automatically download all Sentinel‑2 spectral bands (10 m, 20 m, 60 m, atmospheric, and quality bands) for a given area of interest, using Google Earth Engine and Google Colab. The data is saved as organised GeoTIFF files, together with metadata and an optional zip archive.

### Main Function: `main()`
The entry point of the script. It:
1. Initialises Earth Engine (authenticates if needed).
2. Defines the study area from a bounding box.
3. Retrieves a median composite of Sentinel‑2 images within the specified date range and cloud cover threshold.
4. Creates a folder structure.
5. Downloads every available band into its respective subfolder.
6. Generates a metadata file.
7. Optionally creates an RGB composite and a zip archive.
8. Prints a summary and download instructions.

**Usage** (in a Colab cell):
```python
from your_script_name import main
main()
```
Or simply run the script directly.

---

### Initialisation
```python
init_ee(project_id='ee-almohamadmohamad678')
```
- **Purpose**: Authenticates and initialises the Earth Engine API. If no valid authentication exists, it triggers an interactive login.
- **Parameters**:
  - `project_id` (str): Your Earth Engine project ID. Default is the one used in the example.

---

### Folder & Metadata Utilities
```python
create_output_structure()
```
- **Returns**: `dict` with paths to `base`, `spectral_10m`, `spectral_20m`, `spectral_60m`, `atmospheric`, `quality`, `metadata`, and `zipped` folders.
- **Creates** a timestamped folder tree and prints confirmation.

```python
create_metadata_file(folders, bands_info)
```
- **Parameters**:
  - `folders` (dict): Output from `create_output_structure()`.
  - `bands_info` (dict): Dictionary of band groups with their names (e.g., `{'10m_bands': ['B2','B3',...]}`).
- **Returns**: Path to the saved `metadata.txt` file.

```python
create_zip_archive(folders)
```
- **Parameters**: `folders` dictionary.
- **Returns**: Path to the created `.zip` archive.

---

### Study Area & Image Collection
```python
create_study_area(bbox)
```
- **Parameters**:
  - `bbox` (list of 4 floats): `[minLon, minLat, maxLon, maxLat]`.
- **Returns**: `ee.Geometry.Rectangle` object.
- **Prints** area size and approximate pixel count.

```python
get_sentinel2_image(study_area)
```
- **Parameters**:
  - `study_area` (ee.Geometry): Rectangle from `create_study_area()`.
- **Returns**: Tuple `(sentinel_median, bands_by_type)` where:
  - `sentinel_median` : `ee.Image` – median composite clipped to the area.
  - `bands_by_type` : `dict` – classification of bands (e.g., `'10m_bands'`, `'20m_bands'`, ...).
- **Raises**: `ValueError` if no images match the criteria.

---

### Download Functions
```python
download_band_with_organization(image, study_area, band, folders)
```
- **Downloads a single band** as GeoTIFF and places it into the correct subfolder (based on the band group).
- **Returns**: `(filepath, size_mb, success)`.

```python
download_bands_organized(image, study_area, bands_by_type, folders)
```
- **Downloads all bands** in bulk by iterating over `bands_by_type`.
- **Returns**: `(list_of_downloaded_files, total_size_mb)`.

```python
download_composite_image(image, study_area, bands, folders, suffix="")
```
- **Downloads a multi‑band composite** (e.g., RGB) into the base folder.
- **Returns**: `(filepath, size_mb)` or `(None, 0)` on failure.

---

### Global Configuration (edit before running)
The script uses a global dictionary `CONFIG` that you can modify:
```python
CONFIG = {
    'location_name': 'Baghdadi_Haditha',   # used in file names
    'country': 'Iraq',
    'bbox': [42.35, 33.84, 42.55, 33.96],  # [west, south, east, north]
    'start_date': '2023-06-01',
    'end_date': '2023-09-30',
    'cloud_threshold': 10,                 # max cloud percentage
    'output_resolution': 10,               # metres
    'crs': 'EPSG:32637',                   # UTM zone
    'max_pixels': 1e9,
    'create_zip_archive': True
}
```

### Band Groups (predefined)
`SENTINEL2_BANDS` dictionary organises Sentinel‑2 bands into logical groups:
- `10m_bands`: B2, B3, B4, B8
- `20m_bands`: B5, B6, B7, B8A, B11, B12
- `60m_bands`: B1, B9, B10
- `atmospheric_bands`: AOT, WVP, SCL, TCI_R, TCI_G, TCI_B
- `quality_bands`: MSK_CLDPRB, MSK_SNWPRB, QA10, QA20, QA60

---

### Example Workflow in Google Colab
```python
# 1. Install Earth Engine API (run once)
!pip install earthengine-api -q

# 2. Copy the whole script into a cell and run it
# The script will execute main() automatically when run as a script.

# 3. Alternatively, call the functions manually:
from sentinel2_download import init_ee, create_study_area, get_sentinel2_image
init_ee()
area = create_study_area([42.35, 33.84, 42.55, 33.96])
img, bands = get_sentinel2_image(area)
# ... then create folders and download
```

### Notes
- The script is designed for **Google Colab** but can be adapted to any Python environment with Earth Engine authentication.
- Large areas or long time ranges may exceed the Earth Engine download limit (max 32 MB per request). The script handles this by downloading bands individually.
- If you encounter `EEException: Image.clip()`, the area may be too large – reduce `bbox` or increase `max_pixels`.

--- 
