"""Save / load area boundaries as shapefiles and convert them for Earth Engine."""
from __future__ import annotations

from pathlib import Path

from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from .aoi import AOI, resolve_aoi
from .utils import logger, slugify


def save_boundary(area, out_dir=".", name: str | None = None, driver: str = "ESRI Shapefile", pick: int = 0) -> Path:
    """Write the boundary of `area` (name, Place, AOI, bbox ...) to a shapefile in EPSG:4326.

    Returns the path of the .shp file (sidecar .shx/.dbf/.prj/.cpg are written next to it).
    """
    import geopandas as gpd

    aoi = resolve_aoi(area, pick=pick, name=name)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = slugify(aoi.name)
    ext = ".shp" if driver == "ESRI Shapefile" else ".gpkg" if driver == "GPKG" else ".geojson"
    path = out_dir / f"{stem}{ext}"
    gdf = gpd.GeoDataFrame(
        {"name": [aoi.name], "display": [aoi.display_name[:250]], "source": [aoi.source], "osm_id": [aoi.osm_id]},
        geometry=[aoi.geometry], crs="EPSG:4326",
    )
    gdf.to_file(path, driver=driver, encoding="utf-8")
    logger.info("Boundary saved: %s", path)
    return path


def read_boundary(path) -> BaseGeometry:
    """Read a vector file and return the union of its geometries in lon/lat."""
    from .aoi import aoi_from_file

    return aoi_from_file(path).geometry


def to_ee_geometry(geometry: BaseGeometry, max_vertices: int = 3000):
    """shapely (lon/lat) -> ee.Geometry, simplifying very detailed boundaries."""
    import ee
    import shapely

    geom = geometry
    if shapely.get_num_coordinates(geom) > max_vertices:
        tol = 1e-5
        while shapely.get_num_coordinates(geom) > max_vertices and tol < 1:
            geom = geometry.simplify(tol, preserve_topology=True)
            tol *= 2
        logger.info("Boundary simplified to %d vertices for Earth Engine", shapely.get_num_coordinates(geom))
    return ee.Geometry(mapping(geom), proj="EPSG:4326", geodesic=False)
