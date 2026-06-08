# ------------------------------------------------------------------------------
# Install and import required packages (run in Colab cell)
# ------------------------------------------------------------------------------
# !pip install earthengine-api -q

import ee
import requests
import os
import zipfile
from datetime import datetime
from google.colab import files

# ------------------------------------------------------------------------------
# Configuration (global constants)
# ------------------------------------------------------------------------------
CONFIG = {
    'location_name': 'Baghdadi_Haditha',
    'country': 'Iraq',
    'bbox': [42.35, 33.84, 42.55, 33.96],
    'start_date': '2023-06-01',
    'end_date': '2023-09-30',
    'cloud_threshold': 10,
    'output_resolution': 10,
    'crs': 'EPSG:32637',
    'max_pixels': 1e9,
    'download_all_bands': True,
    'create_output_folder': True,
    'create_zip_archive': True
}

SENTINEL2_BANDS = {
    '10m_bands': ['B2', 'B3', 'B4', 'B8'],
    '20m_bands': ['B5', 'B6', 'B7', 'B8A', 'B11', 'B12'],
    '60m_bands': ['B1', 'B9', 'B10'],
    'atmospheric_bands': ['AOT', 'WVP', 'SCL', 'TCI_R', 'TCI_G', 'TCI_B'],
    'quality_bands': ['MSK_CLDPRB', 'MSK_SNWPRB', 'QA10', 'QA20', 'QA60']
}


# ------------------------------------------------------------------------------
# Earth Engine initialization
# ------------------------------------------------------------------------------
def init_ee(project_id='ee-almohamadmohamad678'):
    """Initialize Earth Engine, authenticate if needed."""
    try:
        ee.Initialize(project=project_id)
        print("✓ Earth Engine initialized successfully")
    except Exception:
        print("يجب المصادقة أولاً ...")
        ee.Authenticate()
        ee.Initialize(project=project_id)
        print("✓ Earth Engine initialized after authentication")


# ------------------------------------------------------------------------------
# Folder and metadata handling
# ------------------------------------------------------------------------------
def create_output_structure():
    """Create organised folder tree for outputs."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_folder = f"{CONFIG['location_name'].lower()}_sentinel_{timestamp}"

    folders = {
        'base': base_folder,
        'spectral_10m': os.path.join(base_folder, 'spectral_10m'),
        'spectral_20m': os.path.join(base_folder, 'spectral_20m'),
        'spectral_60m': os.path.join(base_folder, 'spectral_60m'),
        'atmospheric': os.path.join(base_folder, 'atmospheric'),
        'quality': os.path.join(base_folder, 'quality'),
        'metadata': os.path.join(base_folder, 'metadata'),
        'zipped': os.path.join(base_folder, 'zipped')
    }

    for folder_path in folders.values():
        os.makedirs(folder_path, exist_ok=True)

    print(f"✓ تم إنشاء مجلد الإخراج: {base_folder}")
    return folders


def create_metadata_file(folders, bands_info):
    """Save a metadata text file."""
    metadata_path = os.path.join(folders['metadata'], 'metadata.txt')
    with open(metadata_path, 'w') as f:
        f.write("=" * 60 + "\n")
        f.write(f"بيانات تحميل Sentinel-2\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"الموقع: {CONFIG['location_name']}, {CONFIG['country']}\n")
        f.write(f"نطاق الإحداثيات: {CONFIG['bbox']}\n")
        f.write(f"الفترة الزمنية: {CONFIG['start_date']} إلى {CONFIG['end_date']}\n")
        f.write(f"الحد الأقصى للغيوم: <{CONFIG['cloud_threshold']}%\n")
        f.write(f"الدقة: {CONFIG['output_resolution']} م\n")
        f.write(f"الإسقاط: {CONFIG['crs']}\n\n")
        f.write("النطاقات المحمَّلة:\n")
        f.write("-" * 40 + "\n")
        for band_group, bands in bands_info.items():
            if bands:
                f.write(f"\n{band_group}:\n")
                for band in bands:
                    f.write(f"  • {band}\n")
        f.write(f"\nوقت التحميل: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        total_files = sum(len(bands) for bands in bands_info.values())
        f.write(f"عدد الملفات الكلي: {total_files}\n")
    print(f"✓ ملف metadata محفوظ: {metadata_path}")
    return metadata_path


def create_zip_archive(folders):
    """Compress the entire output folder into a zip archive."""
    zip_filename = f"{folders['base']}.zip"
    zip_path = os.path.join(folders['zipped'], zip_filename)
    print(f"\nجاري إنشاء الأرشيف المضغوط ...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folders['base']):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, folders['base'])
                zipf.write(file_path, arcname)
    zip_size = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"✓ الأرشيف المضغوط: {zip_path}")
    print(f"  الحجم: {zip_size:.2f} MB")
    return zip_path


# ------------------------------------------------------------------------------
# Study area and Sentinel‑2 collection
# ------------------------------------------------------------------------------
def create_study_area(bbox):
    """Create an EE rectangle from bounding box and print area info."""
    study_area = ee.Geometry.Rectangle(bbox)
    area_sqkm = study_area.area().divide(1000000).getInfo()
    print(f"منطقة الدراسة: {CONFIG['location_name']}, {CONFIG['country']}")
    print(f"المستطيل: {bbox}")
    print(f"المساحة التقريبية: {area_sqkm:.2f} كم²")
    print(f"البكسلات التقريبية: {area_sqkm * 100:.0f} (بدقة {CONFIG['output_resolution']} م)")
    print("-" * 60)
    return study_area


def get_sentinel2_image(study_area):
    """Load median composite of Sentinel‑2 with all bands."""
    print("جاري تحميل صور Sentinel-2 مع جميع النطاقات...")
    sentinel_collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                           .filterBounds(study_area)
                           .filterDate(CONFIG['start_date'], CONFIG['end_date'])
                           .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', CONFIG['cloud_threshold'])))
    collection_size = sentinel_collection.size().getInfo()
    if collection_size == 0:
        raise ValueError("لا توجد صور Sentinel-2 تطابق المعايير المحددة")
    print(f"✓ تم العثور على {collection_size} صورة")
    sample_image = sentinel_collection.first()
    available_bands = sample_image.bandNames().getInfo()
    print(f"النطاقات المتوفرة في المجموعة: {len(available_bands)}")
    sentinel_median = sentinel_collection.median().clip(study_area)
    actual_bands = sentinel_median.bandNames().getInfo()

    # Classify bands by type
    bands_by_type = {k: [] for k in SENTINEL2_BANDS.keys()}
    bands_by_type['other_bands'] = []
    for band in actual_bands:
        found = False
        for group_name, group_bands in SENTINEL2_BANDS.items():
            if band in group_bands:
                bands_by_type[group_name].append(band)
                found = True
                break
        if not found:
            bands_by_type['other_bands'].append(band)

    total_bands = sum(len(bands) for bands in bands_by_type.values())
    print(f"\nسيتم تحميل {total_bands} نطاق:")
    for group_name, group_bands in bands_by_type.items():
        if group_bands:
            print(f"  • {group_name}: {len(group_bands)} نطاق")
    print(f"\n✓ تم الحصول على الصورة المركبة")
    print(f"  الدقة: {CONFIG['output_resolution']} م")
    print(f"  التاريخ: {CONFIG['start_date']} إلى {CONFIG['end_date']}")
    print(f"  الغطاء السحابي: <{CONFIG['cloud_threshold']}%")
    print("-" * 60)
    return sentinel_median, bands_by_type


# ------------------------------------------------------------------------------
# Download functions
# ------------------------------------------------------------------------------
def download_band_with_organization(image, study_area, band, folders):
    """Download a single band and place it into the correct subfolder."""
    folder_mapping = {
        '10m_bands': folders['spectral_10m'],
        '20m_bands': folders['spectral_20m'],
        '60m_bands': folders['spectral_60m'],
        'atmospheric_bands': folders['atmospheric'],
        'quality_bands': folders['quality']
    }
    target_folder = folders['spectral_10m']  # default
    for group, folder_path in folder_mapping.items():
        if band in SENTINEL2_BANDS.get(group, []):
            target_folder = folder_path
            break

    filename = f"{CONFIG['location_name'].lower()}_{band}.tif"
    filepath = os.path.join(target_folder, filename)

    try:
        download_url = image.select([band]).getDownloadURL({
            'scale': CONFIG['output_resolution'],
            'region': study_area,
            'format': 'GEO_TIFF',
            'crs': CONFIG['crs'],
            'maxPixels': CONFIG['max_pixels']
        })
        response = requests.get(download_url, stream=True)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        file_size = os.path.getsize(filepath) / (1024 * 1024)
        return filepath, file_size, True
    except Exception as e:
        print(f"    ✗ فشل تحميل {band}: {str(e)}")
        return None, 0, False


def download_bands_organized(image, study_area, bands_by_type, folders):
    """Download all bands and organise them in folders."""
    print("\n" + "="*60)
    print("تحميل النطاقات إلى مجلدات")
    print("="*60)
    downloaded_files = []
    total_size = 0
    successful = 0
    for group_name, bands in bands_by_type.items():
        if not bands:
            continue
        print(f"\nتحميل {group_name} ({len(bands)} نطاق)...")
        for band in bands:
            filepath, size, success = download_band_with_organization(image, study_area, band, folders)
            if success:
                downloaded_files.append(filepath)
                total_size += size
                successful += 1
                print(f"  ✓ {band}: {size:.1f} MB")
    print(f"\n✓ تم تحميل {successful} نطاق بنجاح")
    print(f"  الحجم الإجمالي: {total_size:.2f} MB")
    return downloaded_files, total_size


def download_composite_image(image, study_area, bands, folders, suffix=""):
    """Download a multi‑band composite GeoTIFF."""
    if not bands:
        return None, 0
    filename = f"{CONFIG['location_name'].lower()}_composite{suffix}.tif"
    filepath = os.path.join(folders['base'], filename)
    try:
        print(f"\nتحميل صورة مركبة ({len(bands)} نطاق)...")
        download_url = image.select(bands).getDownloadURL({
            'scale': CONFIG['output_resolution'],
            'region': study_area,
            'format': 'GEO_TIFF',
            'crs': CONFIG['crs'],
            'maxPixels': CONFIG['max_pixels']
        })
        response = requests.get(download_url, stream=True)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        file_size = os.path.getsize(filepath) / (1024 * 1024)
        print(f"✓ الصورة المركبة: {filename} ({file_size:.1f} MB)")
        return filepath, file_size
    except Exception as e:
        print(f"✗ فشل تحميل الصورة المركبة: {str(e)}")
        return None, 0


# ------------------------------------------------------------------------------
# Main pipeline
# ------------------------------------------------------------------------------
def main():
    print("="*60)
    print(f"تحميل صور Sentinel-2 لجميع النطاقات - منطقة {CONFIG['location_name']}")
    print("="*60)

    # Initialize Earth Engine
    init_ee()

    # Define study area
    study_area = create_study_area(CONFIG['bbox'])

    # Get Sentinel‑2 composite
    try:
        sentinel_image, bands_by_type = get_sentinel2_image(study_area)
    except ValueError as e:
        print(f"✗ خطأ: {str(e)}")
        print("\nجرِّب تعديل:")
        print("1. الفترة الزمنية")
        print("2. نسبة الغيوم المسموحة")
        print("3. إحداثيات المنطقة")
        return

    # Create output folders
    folders = create_output_structure()

    # Download individual bands
    downloaded_files, total_size = download_bands_organized(
        sentinel_image, study_area, bands_by_type, folders)

    # Create metadata file
    metadata_file = create_metadata_file(folders, bands_by_type)
    downloaded_files.append(metadata_file)

    # Optional RGB composite
    all_bands = sum(bands_by_type.values(), [])
    rgb_bands = [b for b in ['B4', 'B3', 'B2'] if b in all_bands]
    if rgb_bands:
        comp_path, comp_size = download_composite_image(sentinel_image, study_area, rgb_bands, folders, "_rgb")
        if comp_path:
            downloaded_files.append(comp_path)
            total_size += comp_size

    # Optional zip archive
    zip_file = None
    if CONFIG['create_zip_archive'] and downloaded_files:
        zip_file = create_zip_archive(folders)

    # Final summary
    print("\n" + "="*60)
    print("ملخص التحميل")
    print("="*60)
    print(f"\nالمجلد الأساسي: {folders['base']}")
    print(f"عدد الملفات: {len(downloaded_files)}")
    print(f"الحجم الإجمالي: {total_size:.2f} MB")
    print(f"\nمحتوى المجلدات:")
    for folder_name, folder_path in folders.items():
        if os.path.exists(folder_path):
            files_in = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
            if files_in:
                print(f"  • {folder_name}: {len(files_in)} ملفات")
    print("\n" + "="*60)
    print("للتحميل إلى جهاز الكمبيوتر:")
    print("="*60)
    if zip_file:
        print(f"files.download('{zip_file}')")
    else:
        print(f"!zip -r {folders['base']}.zip {folders['base']}/")
        print(f"files.download('{folders['base']}.zip')")
    print("\n" + "="*60)
    print("تم بنجاح!")
    print("="*60)


# ------------------------------------------------------------------------------
# Execute only if script is run directly
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    main()
