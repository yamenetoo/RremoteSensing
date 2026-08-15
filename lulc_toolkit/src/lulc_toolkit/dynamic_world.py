"""Download annual Google Dynamic World composites per district/year."""

import os

import ee
import geemap

#: Official Dynamic World class names & colors (9 classes: 0-8)
#: {pixel_value: (class_name, hex_color)}
DW_CLASSES = {
    0: ("Water", "#419bdf"),
    1: ("Trees", "#397d49"),
    2: ("Grass", "#88b053"),
    3: ("Flooded vegetation", "#7a87c6"),
    4: ("Crops", "#e49635"),
    5: ("Shrub and scrub", "#dfc35a"),
    6: ("Built", "#c4281b"),
    7: ("Bare", "#a59b8f"),
    8: ("Snow and ice", "#b39fe1"),
}

#: Same classes as ``DW_CLASSES`` but as {pixel_value: class_name} only,
#: convenient for statistics tables.
DW_CLASS_NAMES = {k: v[0].lower().replace(" ", "_") for k, v in DW_CLASSES.items()}


def download_dynamicworld_for_years(
    gdf,
    name_field: str,
    years,
    out_dir: str,
    scale: int = 10,
    crs: str = "EPSG:4326",
):
    """
    Download an annual Dynamic World mode-composite (the most frequent
    class per pixel over the year) for every feature (district) in
    ``gdf``, for every year in ``years``, clipped to that feature's
    geometry.

    Requires Earth Engine to already be initialized (see
    :func:`lulc_toolkit.auth.authenticate_ee`).

    Parameters
    ----------
    gdf : geopandas.GeoDataFrame
        Districts/features to process (e.g. from
        :func:`lulc_toolkit.shapefile_utils.load_shapefile`).
    name_field : str
        Column in ``gdf`` used to name each district in the output filenames.
    years : list of int
        Years to fetch, e.g. ``[2014, 2019, 2024]``. A year with no
        Dynamic World coverage (e.g. before mid-2015) is skipped
        automatically.
    out_dir : str
        Local folder to save GeoTIFFs into (created if missing).
    scale : int
        Output resolution in meters (Dynamic World native = 10m).
    crs : str
        Output coordinate reference system.

    Returns
    -------
    tuple(list of str, list of tuple)
        ``(downloaded_files, skipped)`` — paths of files written, and a
        list of ``(district_name, year)`` pairs that had no imagery
        available.
    """
    os.makedirs(out_dir, exist_ok=True)
    dw_collection_all = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")

    downloaded_files = []
    skipped = []
    total_iterations = len(gdf) * len(years)
    counter = 0

    for _idx, row in gdf.iterrows():
        district_name = str(row[name_field]).strip().replace(" ", "_").replace("/", "_")
        geom = row.geometry
        geojson = geom.__geo_interface__

        if geojson["type"] == "Polygon":
            district_aoi = ee.Geometry.Polygon(geojson["coordinates"])
        elif geojson["type"] == "MultiPolygon":
            district_aoi = ee.Geometry.MultiPolygon(geojson["coordinates"])
        else:
            print(f"⚠ Skipping {district_name} - unsupported geometry type: {geojson['type']}")
            continue

        for year in years:
            counter += 1
            start, end = f"{year}-01-01", f"{year}-12-31"

            dw_year_coll = (
                dw_collection_all.filterBounds(district_aoi)
                .filterDate(start, end)
                .select("label")
            )

            n_images = dw_year_coll.size().getInfo()
            if n_images == 0:
                print(
                    f"[{counter}/{total_iterations}] {district_name} - {year}: "
                    f"no imagery available, skipping"
                )
                skipped.append((district_name, year))
                continue

            dw_mode = dw_year_coll.mode().clip(district_aoi).rename("label")
            out_path = os.path.join(out_dir, f"DW_{district_name}_{year}.tif")

            print(
                f"[{counter}/{total_iterations}] Downloading: {district_name} - {year} "
                f"({n_images} source images) ..."
            )
            try:
                geemap.download_ee_image(
                    image=dw_mode,
                    filename=out_path,
                    region=district_aoi,
                    scale=scale,
                    crs=crs,
                )
                if os.path.exists(out_path):
                    size_mb = os.path.getsize(out_path) / (1024 * 1024)
                    print(f"  ✓ Saved: {out_path} ({size_mb:.2f} MB)")
                    downloaded_files.append(out_path)
                else:
                    print(f"  ✗ File was not created for {district_name} - {year}")
            except Exception as e:
                print(f"  ✗ Error downloading {district_name} - {year}: {e}")

    print(
        f"\n✓ Done. Downloaded {len(downloaded_files)} of {total_iterations} "
        f"(district x year) combinations"
    )
    if skipped:
        print(f"  Skipped {len(skipped)} combinations with no imagery:")
        for d, y in skipped:
            print(f"   - {d} ({y})")

    return downloaded_files, skipped
