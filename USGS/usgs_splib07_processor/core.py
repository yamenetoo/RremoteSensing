import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.interpolate import interp1d
from typing import Callable, Union

def process_spectrum(
    row: Union[pd.Series, list, tuple],
    plot: bool = False,
    rng: int = 2,
    base_path: Union[str, Path, None] = None
) -> tuple:
    """
    Process a row containing material name, reflectance path, and wavelength path.
    
    Parameters
    ----------
    row : pd.Series or list/tuple
        Expected format: [name, reflectance_path, wavelength_path]
    plot : bool, default=False
        If True, displays the spectrum plot.
    rng : int, default=2
        Number of data points to trim from both ends of the spectrum.
    base_path : str or Path, optional
        Base directory to replace hardcoded drive paths. Defaults to 'D:\\usgs_splib07\\'
        
    Returns
    -------
    name : str
        Material name
    spectrum : np.ndarray
        Shape (N, 2) with wavelengths (col 0) and reflectance (col 1)
    """
    if hasattr(row, 'iloc'):
        name = row.iloc[0]
        t1 = row.iloc[1]
        t2 = row.iloc[2]
    else:
        name = row[0]
        t1 = row[1]
        t2 = row[2]

    # Resolve paths & apply base directory replacement
    default_base = r"D:\usgs_splib07"
    base = str(Path(base_path).resolve()) if base_path else default_base

    def fix_path(p: str) -> str:
        resolved = str(Path(p).resolve())
        return resolved.replace("D:\\", f"{base}\\")

    t1_fixed = fix_path(t1)
    t2_fixed = fix_path(t2)

    # Load data
    wavelengths = np.loadtxt(t2_fixed, skiprows=1)
    reflectance = np.loadtxt(t1_fixed, skiprows=1)

    # Trim edges
    if rng > 0:
        wavelengths = wavelengths[rng:-rng]
        reflectance = reflectance[rng:-rng]

    # Filter negative reflectance values
    valid_mask = reflectance >= 0.0
    wavelengths = wavelengths[valid_mask]
    reflectance = reflectance[valid_mask]

    if len(wavelengths) == 0:
        print(f"⚠️ Warning: All reflectance values were negative/invalid for '{name}'. Returning empty spectrum.")
        return name, np.empty((0, 2))

    spectrum = np.column_stack((wavelengths, reflectance))

    if plot:
        plt.figure(figsize=(6, 4))
        plt.plot(wavelengths, reflectance, linewidth=1.2)
        plt.title(name, fontsize=11)
        plt.xlabel('Wavelength (μm)', fontsize=10)
        plt.ylabel('Reflectance', fontsize=10)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()

    return name, spectrum


def create_material_interp_function(
    spectrum: np.ndarray,
    input_unit: str = 'um',
    output_unit: str = 'nm',
    kind: str = 'linear',
    fill_value: float = 0.0,
    normalize_reflectance: bool = True
) -> Callable[[Union[float, np.ndarray]], Union[float, np.ndarray]]:
    """
    Convert a spectrum array into a callable interpolation function P_m(λ).
    """
    wavelengths = spectrum[:, 0]
    reflectance = spectrum[:, 1]

    wl = np.asarray(wavelengths, dtype=np.float64)
    refl = np.asarray(reflectance, dtype=np.float64)

    if wl.shape != refl.shape:
        raise ValueError("Wavelengths and reflectance must have the same shape.")
    if len(wl) < 2:
        raise ValueError("At least two data points are required for interpolation.")

    # Normalize if values appear to be in percentage (0-100)
    if normalize_reflectance and np.max(refl) > 1.0:
        refl = refl / 100.0

    # Ensure strictly increasing wavelengths
    if not np.all(np.diff(wl) > 0):
        sort_idx = np.argsort(wl)
        wl = wl[sort_idx]
        refl = refl[sort_idx]

    # Unit conversion
    in_is_um = input_unit.lower() in ['um', 'micrometer', 'micrometers', 'μm']
    out_is_um = output_unit.lower() in ['um', 'micrometer', 'micrometers', 'μm']

    if in_is_um and not out_is_um:
        wl = wl * 1000.0  # μm → nm
    elif not in_is_um and out_is_um:
        wl = wl / 1000.0  # nm → μm

    return interp1d(
        wl, refl, kind=kind, fill_value=fill_value, bounds_error=False, assume_sorted=True
    )
