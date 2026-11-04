import numpy as np
import pytest


def _write(path, values, title="title"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(title + "\n")
        for v in values:
            fh.write(f"{v:.8e}\n")


@pytest.fixture()
def fake_root(tmp_path):
    """A tiny tree shaped like the real ASCIIdata_splib07b layout."""
    lib = tmp_path / "ASCIIdata" / "ASCIIdata_splib07b"
    asd_wl = np.linspace(0.35, 2.5, 2151)  # micrometres
    beck_wl = np.linspace(0.2, 3.0, 1401)
    nic_wl = np.linspace(1.5, 20.0, 800)
    _write(lib / "splib07b_Wavelengths_ASD_0.35-2.5_microns_2151_ch.txt", asd_wl)
    _write(lib / "splib07b_Wavelengths_BECK_Beckman_0.2-3.0_microns.txt", beck_wl)
    _write(lib / "splib07b_Wavelengths_NIC4_Nicolet_1.5-20_microns.txt", nic_wl)

    # Calcite-like: dip near 2.34 um (ASD). Deleted channels in the 1.40 um region.
    y = 0.8 - 0.3 * np.exp(-0.5 * ((asd_wl - 2.34) / 0.02) ** 2)
    y_del = y.copy()
    y_del[(asd_wl > 1.40) & (asd_wl < 1.42)] = -1.23e34
    _write(lib / "ChapterM_Minerals" / "splib07b_Calcite_HS48.3B_ASDFRb_AREF.txt", y_del)
    _write(lib / "ChapterM_Minerals" / "splib07b_Calcite_HS48.3B_ASDFRb_RREF.txt", y)  # other kind
    # Flat spectrum, Beckman
    _write(lib / "ChapterM_Minerals" / "splib07b_Flat_Mineral_X1_BECKb_AREF.txt", np.full(len(beck_wl), 0.5))
    # Vegetation, ASD, red edge
    veg = 0.05 + 0.45 / (1 + np.exp(-(asd_wl - 0.71) / 0.02))
    _write(lib / "ChapterV_Vegetation" / "splib07b_Grass_Dry_GR1_ASDFRa_AREF.txt", veg)
    # FTIR (should be dropped by a VNIR-SWIR grid)
    _write(lib / "ChapterM_Minerals" / "splib07b_Quartz_QZ1_NIC4bb_AREF.txt", np.full(len(nic_wl), 0.3))
    # error bars dir must be ignored
    _write(lib / "errorbars" / "errorbars_for_splib07b_Calcite_HS48.3B_ASDFRb_AREF.txt", np.zeros(2151))
    return tmp_path
