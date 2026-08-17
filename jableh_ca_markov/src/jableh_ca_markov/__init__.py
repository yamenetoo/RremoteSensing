"""
jableh_ca_markov
=================
A reproducible Python package implementing the full Spatially Explicit
Markov-CA pipeline for Jableh District LULC change analysis and 2030
prediction (Dynamic World 2015-2026).

Modules
-------
config              : constants, class definitions, seed matrix
statistics          : annual class-area extraction / pivot tables
markov_ipf          : seeded IPF/RAS transition-matrix estimation,
                       pixel-level cross-tabulation, stationarity test
projection           : Markov forward projection, steady-state analysis
ca_allocation        : spatially explicit CA suitability + allocation
                       (distance, land-cover, density, slope, road)
spatial_analysis     : sector growth, centroid migration, SDE, KDE hotspots
uncertainty          : Monte Carlo bootstrap, classification-error
                       perturbation
validation           : retrospective hindcasting, OA / Kappa / FoM
sensitivity          : seed-matrix and CA-parameter sensitivity analyses
scenarios            : policy scenario simulation (green belt, forest
                       protection, combined)
benchmark            : logistic-regression CA benchmark model
mapping              : classified-raster PNG export, Sentinel-2
                       cartographic basemap, Syria locator map
pipeline             : end-to-end orchestration
"""

__version__ = "1.0.0"
