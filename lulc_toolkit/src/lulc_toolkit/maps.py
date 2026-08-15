"""Render classified GeoTIFFs as styled PNG maps."""

import glob
import os

import numpy as np
import rasterio
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.ticker import FuncFormatter
from matplotlib_scalebar.scalebar import ScaleBar


def make_lulc_png_map(
    tif_path: str,
    out_png_path: str,
    class_dict: dict,
    source_label: str = "GOOGLE/DYNAMICWORLD/V1",
) -> bool:
    """
    Render a single LULC GeoTIFF as a professional PNG map with: boundary
    outline, lon/lat graticule, legend, north arrow, scale bar, and a title.

    Parameters
    ----------
    tif_path : str
        Path to the input GeoTIFF (single-band classified raster).
    out_png_path : str
        Path to save the output PNG.
    class_dict : dict
        Mapping of ``{pixel_value: (class_name, hex_color)}`` — e.g.
        :data:`lulc_toolkit.dynamic_world.DW_CLASSES`.
    source_label : str
        Text shown in the map's data-source credit line.

    Returns
    -------
    bool
        ``True`` if a map was generated, ``False`` if the file had no
        recognizable class values (e.g. fully masked).
    """
    base = os.path.splitext(os.path.basename(tif_path))[0]
    display_name = base.replace("DW_", "").replace("LULC_", "").replace("_", " ")

    with rasterio.open(tif_path) as src:
        data = src.read(1)
        nodata = src.nodata
        bounds = src.bounds  # left, bottom, right, top (in lon/lat)

    if nodata is not None:
        data = np.ma.masked_equal(data, nodata)
    else:
        data = np.ma.masked_invalid(data)

    present_values = sorted(
        [int(v) for v in np.unique(data.compressed()) if int(v) in class_dict]
    )
    if not present_values:
        print(f"  ⚠ Skipping {display_name} - no recognized class values in the image")
        return False

    fig, ax = plt.subplots(figsize=(10, 10), dpi=200)

    colors = [class_dict[v][1] for v in present_values]
    cmap = ListedColormap(colors)
    cmap.set_bad(color="white", alpha=0)  # masked/nodata pixels render transparent
    bounds_norm = present_values + [present_values[-1] + 1]
    norm = BoundaryNorm(bounds_norm, cmap.N)

    extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
    ax.imshow(data, cmap=cmap, norm=norm, extent=extent, interpolation="nearest")

    # Boundary (the raster extent itself, after clipping to the district)
    ax.add_patch(
        mpatches.Rectangle(
            (bounds.left, bounds.bottom),
            bounds.right - bounds.left,
            bounds.top - bounds.bottom,
            fill=False,
            edgecolor="black",
            linewidth=1.5,
        )
    )

    # Lon/Lat graticule
    ax.set_xlabel("Longitude (°E)", fontsize=10)
    ax.set_ylabel("Latitude (°N)", fontsize=10)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:.3f}°"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.3f}°"))
    ax.grid(True, linestyle="--", linewidth=0.5, color="gray", alpha=0.6)
    ax.tick_params(axis="both", labelsize=8)

    # Title
    ax.set_title(
        f"Land Use / Land Cover Map\n{display_name}", fontsize=13, fontweight="bold", pad=12
    )

    # Legend
    legend_patches = [
        mpatches.Patch(facecolor=class_dict[v][1], edgecolor="black", label=class_dict[v][0])
        for v in present_values
    ]
    ax.legend(
        handles=legend_patches,
        loc="upper left",
        bbox_to_anchor=(1.02, 1),
        fontsize=9,
        title="Legend",
        title_fontsize=10,
        frameon=True,
    )

    # North arrow
    ax.annotate(
        "N",
        xy=(0.96, 0.90),
        xytext=(0.96, 0.80),
        arrowprops=dict(facecolor="black", width=4, headwidth=12),
        ha="center",
        va="center",
        fontsize=13,
        fontweight="bold",
        xycoords="axes fraction",
    )

    # Scale bar (approx: 1 degree of longitude at this latitude -> meters)
    try:
        mean_lat = (bounds.top + bounds.bottom) / 2
        meters_per_degree = 111320 * np.cos(np.radians(mean_lat))
        scalebar = ScaleBar(
            meters_per_degree,
            units="m",
            dimension="si-length",
            location="lower left",
            length_fraction=0.25,
            box_alpha=0.7,
            font_properties={"size": 8},
        )
        ax.add_artist(scalebar)
    except Exception:
        pass  # if this fails, just skip the scale bar rather than the whole map

    # Source credit
    ax.text(
        0.01,
        -0.08,
        f"Source: {source_label} | CRS: EPSG:4326",
        transform=ax.transAxes,
        fontsize=7,
        color="gray",
    )

    plt.tight_layout()
    plt.savefig(out_png_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def generate_all_maps(
    in_dir: str,
    out_dir: str,
    class_dict: dict,
    source_label: str = "GOOGLE/DYNAMICWORLD/V1",
):
    """
    Convert every ``.tif`` file in ``in_dir`` into a PNG map (via
    :func:`make_lulc_png_map`) and save the results in ``out_dir``.

    Parameters
    ----------
    in_dir : str
        Folder containing input GeoTIFF files.
    out_dir : str
        Folder to write output PNG maps into (created if missing).
    class_dict : dict
        ``{pixel_value: (class_name, hex_color)}`` mapping, e.g.
        :data:`lulc_toolkit.dynamic_world.DW_CLASSES`.
    source_label : str
        Text shown in each map's data-source credit line.

    Returns
    -------
    list of str
        Paths of the PNG files that were successfully generated.
    """
    os.makedirs(out_dir, exist_ok=True)
    tif_files = sorted(glob.glob(os.path.join(in_dir, "*.tif")))

    if not tif_files:
        raise FileNotFoundError(f"No .tif files found in {in_dir}")

    print(f"Found {len(tif_files)} TIFF files")

    generated = []
    for i, tif_path in enumerate(tif_files, 1):
        base_name = os.path.splitext(os.path.basename(tif_path))[0]
        out_png_path = os.path.join(out_dir, f"{base_name}.png")
        print(f"\n[{i}/{len(tif_files)}] Processing: {base_name} ...")
        try:
            ok = make_lulc_png_map(tif_path, out_png_path, class_dict, source_label)
            if ok:
                print(f"  ✓ Created: {out_png_path}")
                generated.append(out_png_path)
        except Exception as e:
            print(f"  ✗ Error processing {base_name}: {e}")

    print(f"\n✓ Done. Generated {len(generated)} of {len(tif_files)} PNG maps")
    return generated
