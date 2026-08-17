"""
config.py
=========
Central configuration for the Jableh CA-Markov pipeline: class
definitions, file-path conventions, and the domain-informed seed
transition matrix shared across every IPF/RAS estimation call.
"""

from pathlib import Path
import numpy as np

# ----------------------------------------------------------------------
# Study period and LULC class scheme
# ----------------------------------------------------------------------
YEARS = list(range(2015, 2027))                 # 12 annual epochs
HINDCAST_CALIBRATION_YEARS = list(range(2015, 2023))   # 2015-2022
HINDCAST_VALIDATION_YEARS = list(range(2023, 2027))    # 2023-2026

# Dynamic World raw class codes actually present in Jableh
DW_RAW_CODES = {
    0: "water",
    1: "trees",
    2: "grass",
    3: "flooded_vegetation",
    4: "crops",
    5: "shrub_and_scrub",
    6: "built",
    7: "bare",
    8: "snow_and_ice",
}

# Six-class working scheme used throughout the analysis (water,
# flooded_vegetation, snow_and_ice are folded into `bare` -- see
# reclassify_to_six_class() in markov_ipf.py)
CLASS_INDICES = [1, 2, 4, 5, 6, 7]   # trees, grass, crops, shrub, built, bare
CLASS_NAMES = ["trees", "grass", "crops", "shrub", "built", "bare"]
N_CLASSES = len(CLASS_INDICES)

FOREST, GRASS, CROPS, SHRUB, BUILT, BARE = CLASS_INDICES

CLASS_COLOR = {
    "trees": "green",
    "grass": "lightgreen",
    "crops": "yellow",
    "shrub": "orange",
    "built": "red",
    "bare": "brown",
}

# ----------------------------------------------------------------------
# Default local paths (override via environment variables or the
# `paths=` argument accepted by every pipeline.run_* function)
# ----------------------------------------------------------------------
DEFAULT_PATHS = {
    "shapefile_archive": "Jableh_Extracted.rar",
    "dynamic_world_dir": "data/raw/DynamicWorld_Output",
    "maps_png_dir": "results/figures/DynamicWorld_Maps_PNG",
    "stats_dir": "data/processed",
    "ca_outputs_dir": "results/figures/CA_Markov_Outputs",
    "tables_dir": "results/tables",
    "dem_path": "data/raw/srtm_jableh.tif",
    "roads_path": "data/raw/osm_roads_jableh.gpkg",
}


def resolve_paths(base_dir: str, overrides: dict | None = None) -> dict:
    """Resolve every DEFAULT_PATHS entry relative to `base_dir`, applying
    any user-supplied overrides. Returns absolute Path objects."""
    overrides = overrides or {}
    resolved = {}
    for key, rel in DEFAULT_PATHS.items():
        value = overrides.get(key, rel)
        resolved[key] = Path(base_dir) / value
    return resolved


# ----------------------------------------------------------------------
# Domain-informed seed transition matrix (Section 2.4.1 of the article)
# ----------------------------------------------------------------------
def build_seed_matrix(
    persist: dict | None = None,
    off_pref: dict | None = None,
    min_reachability: float = 0.02,
) -> np.ndarray:
    """
    Construct the seed transition-probability matrix P^(0) encoding
    domain-informed persistence priors used to initialise every seeded
    IPF/RAS estimation (Eq. 1 of the article).

    Parameters
    ----------
    persist : dict, optional
        Row-wise diagonal (persistence) probability per class. Defaults
        to the values used throughout the article (built ~0.985 etc.).
    off_pref : dict, optional
        Relative off-diagonal preference weights per origin class.
    min_reachability : float, default 0.02
        Every class not explicitly listed in another class's `off_pref`
        entry is still assigned this small relative weight as a
        destination. This guarantees every column of the resulting
        seed matrix has at least one nonzero off-diagonal contributor,
        which is a NECESSARY condition for IPF/RAS to be able to match
        an arbitrary pair of observed marginals exactly (a "structural
        zero" column -- reachable from no other class -- makes exact
        marginal matching mathematically impossible for any pair of
        marginals in which that class's target differs from what its
        own diagonal persistence alone could supply; see
        tests/test_markov_ipf.py::test_seeded_ipf_matches_marginals).
        Set to 0.0 to recover the original (unguarded) behaviour.

    Returns
    -------
    np.ndarray, shape (N_CLASSES, N_CLASSES), row-stochastic.
    """
    if persist is None:
        persist = {
            "trees": 0.85, "grass": 0.5, "crops": 0.85,
            "shrub": 0.7, "built": 0.985, "bare": 0.4,
        }
    if off_pref is None:
        off_pref = {
            "trees": {"crops": 0.35, "shrub": 0.25, "built": 0.35, "bare": 0.05},
            "grass": {"crops": 0.4, "shrub": 0.3, "built": 0.2, "bare": 0.1},
            "crops": {"trees": 0.15, "shrub": 0.15, "built": 0.6, "bare": 0.1},
            "shrub": {"trees": 0.3, "crops": 0.3, "built": 0.3, "bare": 0.1},
            "built": {"trees": 0.3, "crops": 0.3, "shrub": 0.2, "bare": 0.2},
            "bare":  {"trees": 0.3, "crops": 0.3, "shrub": 0.2, "built": 0.2},
        }

    seed = np.zeros((N_CLASSES, N_CLASSES))
    for i, ci in enumerate(CLASS_NAMES):
        seed[i, i] = persist[ci]
        remain = 1.0 - persist[ci]
        for j, cj in enumerate(CLASS_NAMES):
            if i == j:
                continue
            weight = off_pref[ci].get(cj, 0.0)
            if weight == 0.0 and min_reachability > 0.0:
                weight = min_reachability  # guarantee reachability, see docstring
            seed[i, j] = remain * weight
        seed[i] /= seed[i].sum()
    return seed


# Convenience: the "original" seed used throughout the manuscript
SEED_MATRIX_ORIGINAL = build_seed_matrix()
