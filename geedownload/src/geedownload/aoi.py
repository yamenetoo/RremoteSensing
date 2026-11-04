"""Area of interest: from a place name, a shapefile/GeoJSON, a bounding box or a shapely geometry."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .errors import GeeDownloadError
from .geocode import Place, search_area
from .utils import logger

VECTOR_EXT = (".shp", ".geojson", ".json", ".gpkg", ".kml")


@dataclass
class AOI:
    name: str
    geometry: BaseGeometry            # EPSG:4326 (lon/lat)
    display_name: str = ""
    source: str = ""                  # "search" | "file" | "bbox" | "geometry"
    osm_id: int = 0

    @property
    def bbox(self) -> tuple:
        return tuple(self.geometry.bounds)   # (west, south, east, north)

    @property
    def centroid(self) -> tuple:
        c = self.geometry.centroid
        return c.x, c.y


def aoi_from_place(place: Place) -> AOI:
    if not place.has_polygon:
        logger.warning("'%s' has no polygon in OpenStreetMap; its bounding box is used.", place.name)
    return AOI(place.name, place.polygon, place.display_name, "search", place.osm_id)


def aoi_from_file(path) -> AOI:
    import geopandas as gpd

    gdf = gpd.read_file(path)
    if gdf.empty:
        raise GeeDownloadError(f"No features in {path}")
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    return AOI(Path(path).stem, unary_union(list(gdf.geometry)), str(path), "file")


def _parse_bbox(text: str):
    try:
        vals = [float(v) for v in text.replace(";", ",").split(",")]
    except ValueError:
        return None
    return tuple(vals) if len(vals) == 4 else None


def resolve_aoi(area, pick: int = 0, name: Optional[str] = None, **search_kwargs) -> AOI:
    """Turn almost anything into an AOI.

    `area` can be an AOI, a Place, a place name ("Masyaf, Syria"), a path to a
    shapefile/GeoJSON/GPKG, a (west, south, east, north) tuple/list or "w,s,e,n" text,
    or a shapely geometry in lon/lat. `pick` selects which search candidate to use.
    """
    if isinstance(area, AOI):
        aoi = area
    elif isinstance(area, Place):
        aoi = aoi_from_place(area)
    elif isinstance(area, BaseGeometry):
        aoi = AOI(name or "area", area, source="geometry")
    elif isinstance(area, (list, tuple)) and len(area) == 4:
        w, s, e, n = (float(v) for v in area)
        aoi = AOI(name or "bbox_area", box(w, s, e, n), source="bbox")
    elif isinstance(area, (str, Path)):
        text = str(area)
        if Path(text).suffix.lower() in VECTOR_EXT and Path(text).exists():
            aoi = aoi_from_file(text)
        elif _parse_bbox(text):
            aoi = AOI(name or "bbox_area", box(*_parse_bbox(text)), source="bbox")
        else:
            places = search_area(text, **search_kwargs)
            if pick >= len(places):
                raise GeeDownloadError(f"pick={pick} but only {len(places)} result(s) found for '{text}'")
            aoi = aoi_from_place(places[pick])
            logger.info("Using: %s", places[pick])
    else:
        raise GeeDownloadError(f"Cannot interpret area of type {type(area).__name__}")
    if name:
        aoi.name = name
    w, s, e, n = aoi.bbox
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise GeeDownloadError(f"Invalid lon/lat bounds {aoi.bbox}")
    return aoi


def buffer_aoi(aoi: AOI, metres: float) -> AOI:
    """Return a copy of the AOI buffered by `metres` (computed in local UTM)."""
    if not metres:
        return aoi
    import geopandas as gpd

    from .grid import utm_crs_for

    lon, lat = aoi.centroid
    utm = utm_crs_for(lon, lat)
    g = gpd.GeoSeries([aoi.geometry], crs=4326).to_crs(utm).buffer(metres).to_crs(4326).iloc[0]
    return AOI(aoi.name, g, aoi.display_name, aoi.source, aoi.osm_id)
