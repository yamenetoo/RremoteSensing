from setuptools import setup, find_packages

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="jableh-ca-markov",
    version="1.0.0",
    description=(
        "Spatially explicit Markov-CA modelling of land use/land cover "
        "change and directional prediction for Jableh District, Syria, "
        "using Google Dynamic World time series (2015-2026)."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Mohamad Yamen Al-Mohamad",
    url="https://github.com/yamenetoo/Jableh_CA_Markov",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.10",
    install_requires=[
        "numpy>=1.24",
        "pandas>=2.0",
        "scipy>=1.10",
    ],
    extras_require={
        "raster": ["rasterio>=1.3", "geopandas>=0.14", "shapely>=2.0", "richdem>=0.3"],
        "gee": ["earthengine-api>=0.1.390"],
        "benchmark": ["scikit-learn>=1.3"],
        "mapping": ["matplotlib>=3.7", "cartopy>=0.22", "Pillow>=10.0"],
        "dev": ["pytest>=7.4"],
        "all": [
            "rasterio>=1.3", "geopandas>=0.14", "shapely>=2.0", "richdem>=0.3",
            "earthengine-api>=0.1.390", "scikit-learn>=1.3",
            "matplotlib>=3.7", "cartopy>=0.22", "Pillow>=10.0", "pytest>=7.4",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: GIS",
    ],
)
