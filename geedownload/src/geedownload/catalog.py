"""Registry of satellite / geospatial datasets available in Google Earth Engine.

Any other Earth Engine asset id can be used directly too (see `get_dataset`).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from .errors import GeeDownloadError


@dataclass(frozen=True)
class Dataset:
    key: str
    collection_id: str
    title: str = ""
    scale: Optional[float] = None            # native resolution in metres (None = detect from data)
    cloud_property: Optional[str] = None     # image property holding cloud % (None = no cloud filter)
    default_bands: Optional[Tuple[str, ...]] = None   # None = all bands
    band_groups: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    filters: Tuple[Tuple[str, object], ...] = ()      # equality filters on image properties
    reducer: str = "median"                  # default temporal reducer
    scale_factors: Tuple[dict, ...] = ()     # [{"pattern": regex, "mult": x, "add": y}]
    cloud_mask: Optional[str] = None         # "s2_scl" | "landsat_qa" | None
    kind: Optional[str] = None               # "collection" | "image" | None (auto-detect)

    def group_of(self, band: str) -> str:
        for group, bands in self.band_groups.items():
            if band in bands:
                return group
        return "other"

    def expand_bands(self, requested):
        """Expand group names (e.g. '10m_bands') inside a band list."""
        out: List[str] = []
        for b in requested:
            if b in self.band_groups:
                out.extend(self.band_groups[b])
            else:
                out.append(b)
        return list(dict.fromkeys(out))


_LANDSAT_SR = (
    {"pattern": "SR_B.", "mult": 0.0000275, "add": -0.2},
    {"pattern": "ST_B10", "mult": 0.00341802, "add": 149.0},
)


def _landsat(key, cid, title, sr_bands, extra_groups=None):
    groups = {"surface_reflectance": tuple(sr_bands)}
    groups.update(extra_groups or {})
    return Dataset(key, cid, title, scale=30, cloud_property="CLOUD_COVER", band_groups=groups,
                   scale_factors=_LANDSAT_SR, cloud_mask="landsat_qa")


_S2_GROUPS = {
    "10m_bands": ("B2", "B3", "B4", "B8"),
    "20m_bands": ("B5", "B6", "B7", "B8A", "B11", "B12"),
    "60m_bands": ("B1", "B9", "B10"),
    "atmospheric_bands": ("AOT", "WVP", "SCL", "TCI_R", "TCI_G", "TCI_B"),
    "quality_bands": ("MSK_CLDPRB", "MSK_SNWPRB", "QA10", "QA20", "QA60"),
}

DATASETS: Dict[str, Dataset] = {}


def register_dataset(ds: Dataset, *aliases: str) -> Dataset:
    """Add (or replace) a dataset in the registry."""
    DATASETS[ds.key] = ds
    for a in aliases:
        DATASETS[a] = ds
    return ds


register_dataset(Dataset(
    "sentinel2", "COPERNICUS/S2_SR_HARMONIZED", "Sentinel-2 MSI surface reflectance (L2A)", scale=10,
    cloud_property="CLOUDY_PIXEL_PERCENTAGE", band_groups=_S2_GROUPS, cloud_mask="s2_scl",
    scale_factors=({"pattern": "B[0-9].*", "mult": 0.0001, "add": 0.0},),
), "s2", "sentinel-2")
register_dataset(Dataset(
    "sentinel2_toa", "COPERNICUS/S2_HARMONIZED", "Sentinel-2 MSI top-of-atmosphere (L1C)", scale=10,
    cloud_property="CLOUDY_PIXEL_PERCENTAGE",
    band_groups={k: v for k, v in _S2_GROUPS.items() if k in ("10m_bands", "20m_bands", "60m_bands")} | {"quality_bands": ("QA10", "QA20", "QA60")},
    scale_factors=({"pattern": "B[0-9].*", "mult": 0.0001, "add": 0.0},),
), "s2_toa")
register_dataset(Dataset(
    "sentinel1", "COPERNICUS/S1_GRD", "Sentinel-1 SAR GRD (IW)", scale=10,
    default_bands=("VV", "VH"), filters=(("instrumentMode", "IW"),),
    band_groups={"polarisation": ("VV", "VH", "HH", "HV"), "geometry": ("angle",)},
), "s1")
register_dataset(_landsat("landsat9", "LANDSAT/LC09/C02/T1_L2", "Landsat 9 OLI-2 surface reflectance (C2 L2)",
                          ("SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"),
                          {"thermal": ("ST_B10",), "quality_bands": ("QA_PIXEL", "QA_RADSAT", "SR_QA_AEROSOL")}), "l9")
register_dataset(_landsat("landsat8", "LANDSAT/LC08/C02/T1_L2", "Landsat 8 OLI surface reflectance (C2 L2)",
                          ("SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"),
                          {"thermal": ("ST_B10",), "quality_bands": ("QA_PIXEL", "QA_RADSAT", "SR_QA_AEROSOL")}), "l8")
register_dataset(_landsat("landsat7", "LANDSAT/LE07/C02/T1_L2", "Landsat 7 ETM+ surface reflectance (C2 L2)",
                          ("SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7"),
                          {"thermal": ("ST_B6",), "quality_bands": ("QA_PIXEL", "QA_RADSAT", "SR_ATMOS_OPACITY")}), "l7")
register_dataset(_landsat("landsat5", "LANDSAT/LT05/C02/T1_L2", "Landsat 5 TM surface reflectance (C2 L2)",
                          ("SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7"),
                          {"thermal": ("ST_B6",), "quality_bands": ("QA_PIXEL", "QA_RADSAT", "SR_ATMOS_OPACITY")}), "l5")
register_dataset(Dataset(
    "modis_sr", "MODIS/061/MOD09GA", "MODIS Terra daily surface reflectance (500 m)", scale=500,
    default_bands=tuple(f"sur_refl_b0{i}" for i in range(1, 8)),
    scale_factors=({"pattern": "sur_refl_b.*", "mult": 0.0001, "add": 0.0},),
), "modis")
register_dataset(Dataset(
    "modis_ndvi", "MODIS/061/MOD13Q1", "MODIS Terra 16-day NDVI/EVI (250 m)", scale=250,
    default_bands=("NDVI", "EVI"), scale_factors=({"pattern": "NDVI|EVI", "mult": 0.0001, "add": 0.0},),
), "ndvi")
register_dataset(Dataset(
    "modis_lst", "MODIS/061/MOD11A1", "MODIS Terra daily land surface temperature (1 km)", scale=1000,
    default_bands=("LST_Day_1km", "LST_Night_1km"), scale_factors=({"pattern": "LST_.*", "mult": 0.02, "add": 0.0},),
), "lst")
register_dataset(Dataset(
    "srtm", "USGS/SRTMGL1_003", "SRTM 30 m digital elevation model", scale=30,
    default_bands=("elevation",), kind="image",
), "dem")
register_dataset(Dataset(
    "copernicus_dem", "COPERNICUS/DEM/GLO30", "Copernicus GLO-30 DEM", scale=30,
    default_bands=("DEM",), reducer="mosaic",
))
register_dataset(Dataset(
    "worldcover", "ESA/WorldCover/v200", "ESA WorldCover 10 m land cover (2021)", scale=10,
    default_bands=("Map",), reducer="mosaic",
))
register_dataset(Dataset(
    "dynamic_world", "GOOGLE/DYNAMICWORLD/V1", "Dynamic World near-real-time land cover", scale=10,
    cloud_property=None, default_bands=("label",), reducer="mode",
), "dw")
register_dataset(Dataset(
    "chirps", "UCSB-CHG/CHIRPS/DAILY", "CHIRPS daily precipitation", scale=5566,
    default_bands=("precipitation",), reducer="sum",
))
register_dataset(Dataset(
    "era5_land", "ECMWF/ERA5_LAND/DAILY_AGGR", "ERA5-Land daily aggregates", scale=11132,
    default_bands=("temperature_2m", "total_precipitation_sum"), reducer="mean",
), "era5")
register_dataset(Dataset(
    "viirs_nightlights", "NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG", "VIIRS monthly night-time lights", scale=463.83,
    default_bands=("avg_rad",), reducer="mean",
), "nightlights")
register_dataset(Dataset(
    "sentinel5p_no2", "COPERNICUS/S5P/OFFL/L3_NO2", "Sentinel-5P tropospheric NO2", scale=1113.2,
    default_bands=("tropospheric_NO2_column_number_density",), reducer="mean",
), "no2")


def list_datasets() -> List[Dataset]:
    """Unique registered datasets (aliases removed)."""
    seen, out = set(), []
    for ds in DATASETS.values():
        if ds.key not in seen:
            seen.add(ds.key)
            out.append(ds)
    return out


def get_dataset(name) -> Dataset:
    """Resolve a registry key / alias, a Dataset, or any raw Earth Engine asset id ('ORG/PATH/ID')."""
    if isinstance(name, Dataset):
        return name
    key = str(name).strip()
    if key.lower() in DATASETS:
        return DATASETS[key.lower()]
    for ds in DATASETS.values():
        if ds.collection_id == key:
            return ds
    if "/" in key:  # generic: any EE collection or image, properties detected at run time
        return Dataset(key=key.replace("/", "_"), collection_id=key, title=key)
    raise GeeDownloadError(
        f"Unknown dataset '{name}'. Use one of {sorted(d.key for d in list_datasets())} or an Earth Engine asset id."
    )


def with_overrides(ds: Dataset, **kw) -> Dataset:
    return replace(ds, **{k: v for k, v in kw.items() if v is not None})
