"""Comparison charts built from a statistics DataFrame."""

import os

import pandas as pd
import matplotlib.pyplot as plt

#: Official Dynamic World palette, keyed by lowercase class_name — used to
#: keep chart colors consistent with :data:`lulc_toolkit.dynamic_world.DW_CLASSES`.
DW_COLORS = {
    "water": "#419bdf",
    "trees": "#397d49",
    "grass": "#88b053",
    "flooded_vegetation": "#7a87c6",
    "crops": "#e49635",
    "shrub_and_scrub": "#dfc35a",
    "built": "#c4281b",
    "bare": "#a59b8f",
    "snow_and_ice": "#b39fe1",
}


def plot_trend_per_district(df: pd.DataFrame, out_dir: str, color_map: dict = DW_COLORS):
    """
    For each district, plot class area (km²) over the years as a line chart.

    Parameters
    ----------
    df : pandas.DataFrame
        Statistics table (see :func:`lulc_toolkit.statistics.build_statistics_table`).
    out_dir : str
        Folder to save PNG charts into (created if missing).
    color_map : dict
        ``{class_name: hex_color}`` mapping for consistent chart colors.

    Returns
    -------
    list of str
        Paths of the generated PNG files.
    """
    os.makedirs(out_dir, exist_ok=True)
    generated = []

    for district in sorted(df["district"].unique()):
        sub = df[df["district"] == district]
        pivot = sub.pivot_table(
            index="year", columns="class_name", values="area_km2", aggfunc="sum", fill_value=0
        )
        if pivot.empty:
            continue

        fig, ax = plt.subplots(figsize=(9, 6), dpi=150)
        for cls in pivot.columns:
            ax.plot(
                pivot.index, pivot[cls], marker="o", label=cls, color=color_map.get(cls), linewidth=2
            )

        ax.set_title(f"Class Area Trend Over Years - {district}", fontsize=13, fontweight="bold")
        ax.set_xlabel("Year")
        ax.set_ylabel("Area (km²)")
        ax.set_xticks(pivot.index)
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8, title="Class")
        plt.tight_layout()

        out_path = os.path.join(out_dir, f"trend_{district}.png")
        plt.savefig(out_path, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        generated.append(out_path)
        print(f"  ✓ {out_path}")

    return generated


def plot_stacked_bar_per_year(df: pd.DataFrame, out_dir: str, color_map: dict = DW_COLORS):
    """
    For each year, plot a stacked bar chart of class area (km²) per district.

    Parameters
    ----------
    df : pandas.DataFrame
        Statistics table.
    out_dir : str
        Folder to save PNG charts into (created if missing).
    color_map : dict
        ``{class_name: hex_color}`` mapping for consistent chart colors.

    Returns
    -------
    list of str
        Paths of the generated PNG files.
    """
    os.makedirs(out_dir, exist_ok=True)
    generated = []

    for year in sorted(df["year"].dropna().unique()):
        sub = df[df["year"] == year]
        pivot = sub.pivot_table(
            index="district", columns="class_name", values="area_km2", aggfunc="sum", fill_value=0
        )
        if pivot.empty:
            continue

        fig, ax = plt.subplots(figsize=(12, 7), dpi=150)
        bottom = None
        for cls in pivot.columns:
            vals = pivot[cls]
            color = color_map.get(cls)
            if bottom is None:
                ax.bar(pivot.index, vals, label=cls, color=color)
                bottom = vals.copy()
            else:
                ax.bar(pivot.index, vals, bottom=bottom, label=cls, color=color)
                bottom += vals

        ax.set_title(
            f"Land Cover Distribution by District - Year {int(year)}", fontsize=13, fontweight="bold"
        )
        ax.set_xlabel("District")
        ax.set_ylabel("Area (km²)")
        ax.tick_params(axis="x", rotation=75)
        ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8, title="Class")
        ax.grid(True, axis="y", linestyle="--", alpha=0.5)
        plt.tight_layout()

        out_path = os.path.join(out_dir, f"stacked_bar_{int(year)}.png")
        plt.savefig(out_path, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        generated.append(out_path)
        print(f"  ✓ {out_path}")

    return generated


def plot_province_total_trend(df: pd.DataFrame, out_dir: str, color_map: dict = DW_COLORS) -> str:
    """
    Plot total class area (km²) across all districts combined, over the years.

    Parameters
    ----------
    df : pandas.DataFrame
        Statistics table.
    out_dir : str
        Folder to save the PNG chart into (created if missing).
    color_map : dict
        ``{class_name: hex_color}`` mapping for consistent chart colors.

    Returns
    -------
    str
        Path of the generated PNG file.
    """
    os.makedirs(out_dir, exist_ok=True)
    total_pivot = df.pivot_table(
        index="year", columns="class_name", values="area_km2", aggfunc="sum", fill_value=0
    )

    fig, ax = plt.subplots(figsize=(9, 6), dpi=150)
    for cls in total_pivot.columns:
        ax.plot(
            total_pivot.index,
            total_pivot[cls],
            marker="o",
            label=cls,
            color=color_map.get(cls),
            linewidth=2.5,
        )

    ax.set_title("Total Class Area at Province Level Over the Years", fontsize=13, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("Area (km²)")
    ax.set_xticks(total_pivot.index)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=9, title="Class")
    plt.tight_layout()

    out_path = os.path.join(out_dir, "total_province_trend.png")
    plt.savefig(out_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  ✓ {out_path}")
    return out_path


def plot_percent_change(df: pd.DataFrame, out_dir: str):
    """
    Plot the percent change in total class area between the first and last
    available year (province-level).

    Parameters
    ----------
    df : pandas.DataFrame
        Statistics table.
    out_dir : str
        Folder to save the PNG chart into (created if missing).

    Returns
    -------
    str or None
        Path of the generated PNG file, or ``None`` if fewer than 2 years
        of data exist.
    """
    os.makedirs(out_dir, exist_ok=True)
    total_pivot = df.pivot_table(
        index="year", columns="class_name", values="area_km2", aggfunc="sum", fill_value=0
    )
    years_sorted = sorted(total_pivot.index)

    if len(years_sorted) < 2:
        print("  ⚠ Need at least 2 years of data to compute percent change - skipping")
        return None

    first_year, last_year = years_sorted[0], years_sorted[-1]
    change = (
        (total_pivot.loc[last_year] - total_pivot.loc[first_year])
        / total_pivot.loc[first_year].replace(0, pd.NA)
        * 100
    ).fillna(0)

    fig, ax = plt.subplots(figsize=(9, 6), dpi=150)
    bar_colors = ["green" if v >= 0 else "red" for v in change.values]
    ax.barh(change.index, change.values, color=bar_colors)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_title(
        f"Percent Change in Area per Class ({int(first_year)} → {int(last_year)})",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_xlabel("Percent Change (%)")
    ax.grid(True, axis="x", linestyle="--", alpha=0.5)
    plt.tight_layout()

    out_path = os.path.join(out_dir, f"change_percent_{int(first_year)}_to_{int(last_year)}.png")
    plt.savefig(out_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  ✓ {out_path}")
    return out_path


def generate_all_charts(df: pd.DataFrame, out_dir: str):
    """
    Run all four chart functions (trend per district, stacked bar per
    year, province total trend, percent change) and return every
    generated file.

    Parameters
    ----------
    df : pandas.DataFrame
        Statistics table.
    out_dir : str
        Folder to save all PNG charts into.

    Returns
    -------
    list of str
        Paths of all generated PNG chart files.
    """
    generated = []
    generated += plot_trend_per_district(df, out_dir)
    generated += plot_stacked_bar_per_year(df, out_dir)
    generated.append(plot_province_total_trend(df, out_dir))
    change_path = plot_percent_change(df, out_dir)
    if change_path:
        generated.append(change_path)

    print(f"\n✓ Generated {len(generated)} charts in total")
    return generated
