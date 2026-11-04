"""Search an area by name (OpenStreetMap Nominatim) and get its boundary polygon."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

import requests
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry

from .errors import AreaNotFound, GeeDownloadError
from .utils import logger

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "geedownload/0.1 (python package; area search)"
_last_call = 0.0


@dataclass
class Place:
    name: str
    display_name: str
    bbox: tuple                     # (west, south, east, north)
    geometry: BaseGeometry          # boundary (Polygon/MultiPolygon when available, else Point)
    osm_type: str = ""
    osm_id: int = 0
    category: str = ""
    kind: str = ""
    importance: float = 0.0

    @property
    def has_polygon(self) -> bool:
        return self.geometry.geom_type in ("Polygon", "MultiPolygon")

    @property
    def polygon(self) -> BaseGeometry:
        """Boundary polygon; falls back to the bounding box when OSM only has a point."""
        return self.geometry if self.has_polygon else box(*self.bbox)

    def __str__(self) -> str:
        shape_txt = "polygon" if self.has_polygon else "bbox only"
        return f"{self.display_name} [{self.category}/{self.kind}, {shape_txt}]"


def _parse(item: dict) -> Place:
    s, n, w, e = (float(x) for x in item["boundingbox"])
    geom = shape(item["geojson"]) if item.get("geojson") else box(w, s, e, n)
    name = item.get("name") or item.get("display_name", "").split(",")[0]
    return Place(
        name=name, display_name=item.get("display_name", name), bbox=(w, s, e, n), geometry=geom,
        osm_type=item.get("osm_type", ""), osm_id=int(item.get("osm_id", 0) or 0),
        category=item.get("category", item.get("class", "")), kind=item.get("type", ""),
        importance=float(item.get("importance", 0) or 0),
    )


def search_area(query: str, limit: int = 5, country_codes: Optional[str] = None, lang: str = "en",
                polygons_first: bool = True, base_url: str = NOMINATIM_URL, timeout: int = 60,
                feature_type: Optional[str] = None) -> List[Place]:
    """Search a place name and return candidate areas with their boundary geometry.

    Example: ``search_area("Masyaf, Syria")``. `country_codes` is e.g. ``"sy,iq"``.
    `feature_type` restricts results to ``"country"``, ``"state"``, ``"city"`` or ``"settlement"``.
    Respects the Nominatim usage policy (max one request per second).
    """
    global _last_call
    wait = 1.0 - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    params = {"q": query, "format": "jsonv2", "polygon_geojson": 1, "limit": limit,
              "addressdetails": 0, "accept-language": lang}
    if country_codes:
        params["countrycodes"] = country_codes
    if feature_type:
        params["featureType"] = feature_type
    try:
        resp = requests.get(base_url, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise GeeDownloadError(f"Geocoding request failed: {exc}") from exc
    finally:
        _last_call = time.time()
    places = [_parse(i) for i in resp.json() if i.get("boundingbox")]
    if not places:
        raise AreaNotFound(f"No area found for '{query}'. Try a more specific name (e.g. add the country).")
    if polygons_first:
        places.sort(key=lambda p: (not p.has_polygon, -p.importance))
    logger.info("Found %d candidate(s) for '%s'", len(places), query)
    return places
