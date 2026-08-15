"""
Basic unit tests for the parts of lulc_toolkit that don't require live
Earth Engine credentials or Colab (statistics parsing/pivoting helpers).

Run with: pytest
"""

import pandas as pd

from lulc_toolkit.statistics import parse_tif_filename, build_pivot_table


def test_parse_tif_filename_matches_pattern():
    district, year = parse_tif_filename("DW_Baqubah_2019.tif", prefix="DW_")
    assert district == "Baqubah"
    assert year == 2019


def test_parse_tif_filename_no_match_returns_none_year():
    district, year = parse_tif_filename("some_other_file.tif", prefix="DW_")
    assert year is None


def test_parse_tif_filename_custom_prefix():
    district, year = parse_tif_filename("LULC_Al_Muqdadiya_2024.tif", prefix="LULC_")
    assert district == "Al_Muqdadiya"
    assert year == 2024


def test_build_pivot_table_shape(tmp_path):
    df = pd.DataFrame(
        [
            {"district": "A", "year": 2019, "class_name": "water", "area_km2": 1.0},
            {"district": "A", "year": 2019, "class_name": "trees", "area_km2": 2.0},
            {"district": "A", "year": 2024, "class_name": "water", "area_km2": 1.5},
            {"district": "B", "year": 2019, "class_name": "water", "area_km2": 0.5},
        ]
    )
    out_csv = tmp_path / "pivot.csv"
    pivot = build_pivot_table(df, out_csv_path=str(out_csv), value_col="area_km2")

    assert out_csv.exists()
    assert "water" in pivot.columns
    assert "trees" in pivot.columns
    # A/2019 row should have water=1.0, trees=2.0
    row = pivot[(pivot["district"] == "A") & (pivot["year"] == 2019)].iloc[0]
    assert row["water"] == 1.0
    assert row["trees"] == 2.0
