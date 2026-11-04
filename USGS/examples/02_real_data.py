"""Real data: download the USGS library once, build it once, then use it.

Run from the USGS folder:
    pip install -e .
    python examples/02_real_data.py

The first call downloads the oversampled ASCII archive from USGS ScienceBase (needs internet)
into ~/.usgs_splib07 (or $USGS_SPLIB07_HOME) and builds a 5 nm VNIR-SWIR library of minerals
and soils. Later runs load the cached ``.npz`` in about a second.
"""
import usgs_splib07 as splib

lib = splib.get_library(chapters="MS")          # M = minerals, S = soils and mixtures
print(lib)
print(lib.materials().head(10).to_string(index=False))

# Find a material and look at one spectrum
hits = lib.search("kaolinite")
print(hits[["name", "material", "chapter_name"]].head())
y = lib.spectrum(hits.index[0])                 # 1-D reflectance on lib.wavelengths

# What would Sentinel-2 record? (13 bands, normalised so only the shape is left)
s2 = lib.to_sensor("sentinel2a").normalized("l2")
s2.to_csv("splib07_sentinel2_features.csv")
print(s2.to_frame().iloc[:3, :8])
