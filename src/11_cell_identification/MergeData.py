#!/usr/bin/env python3

import argparse
# import os
from pathlib import Path
# import pyarrow
# import openpyxl
# import pandas as pd
import polars as pl
import warnings
import csv

# input_folder = '/mnt/check_jon/cell_identification_flow_cytometry/Data/XenMIL2/output_feature_extraction'
# output_csv = '/mnt/check_jon/cell_identification_flow_cytometry/Data/XenMIL2/output_cell_identification/df_data_merged.parquet'

def sniff_separator(fp: Path) -> str:
    with open(fp, "r", newline="") as f:
        sample = f.read(4096)

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        return dialect.delimiter
    except csv.Error:
        # Default used by the original feature-extraction outputs
        return ";"

def sniff_decimal_separator(fp: Path, sep: str) -> str:
    with open(fp, "r", newline="") as f:
        lines = f.readlines()[1:25]  # skip header

    comma_decimal = 0
    dot_decimal = 0

    for line in lines:
        for x in line.rstrip("\n").split(sep):
            x = x.strip().strip('"').strip("'")

            if "," in x and x.replace(",", "", 1).replace("-", "", 1).isdigit():
                comma_decimal += 1

            if "." in x and x.replace(".", "", 1).replace("-", "", 1).isdigit():
                dot_decimal += 1

    if comma_decimal > dot_decimal:
        return ","

    return "."

def merge_data(input_folder: str, output_csv: str) -> None:
    print(f"### input csv folder: {input_folder} ###")
    print(f"### output csv: {output_csv} ###")

    out_dir = Path(output_csv).parent
    if not out_dir.exists():
        print(f"### creating folder: {out_dir} ###")
        out_dir.mkdir(parents=True, exist_ok=True)

    # Load csv files
    print("Loading csv files")
    input_path = Path(input_folder)
    if not input_path.exists() or not input_path.is_dir():
        raise ValueError(f"input_folder does not exist or is not a directory: {input_folder}")

    # List all files. Can also be restricted to a specific format (.csv, for example). 
    files = sorted([p for p in input_path.iterdir() if p.is_file()])

    df_list = []
    for fp in files:
        sep = sniff_separator(fp)
        dec = sniff_decimal_separator(fp, sep)
        # tmp = pd.read_csv(fp, sep=";", decimal=',')  # start as str to avoid type surprises
        # tmp = pd.read_csv(fp, sep=None, engine="python")
        tmp = pl.read_csv(fp, separator=sep, decimal_comma=(dec == ","), infer_schema_length=10000, ignore_errors=False)
        df_list.append(tmp)

    if len(df_list) == 0:
        raise ValueError(f"No files found in input folder: {input_folder}")

    # df_data = pd.concat(df_list, ignore_index=True)
    df_data = pl.concat(df_list, how="vertical")
    
    # QC complete data
    null_counts = df_data.null_count()
    n_cells_with_na = int(null_counts.select(pl.sum_horizontal(pl.all())).item())

    if n_cells_with_na > 0:
        n_rows_before = df_data.height
        df_data = df_data.drop_nulls()
        n_rows_after = df_data.height
        n_rows_with_na = n_rows_before - n_rows_after
    
        warnings.warn(
            f"NA/null values detected before completeness check: "
            f"{n_rows_with_na} rows affected, "
            f"{n_cells_with_na} total NA/null cells. "
            f"Rows will be removed.",
            RuntimeWarning,
        )

    print("QC complete data")
    print(f"{len(files)} scenes (csv generated from feature extraction)")

    has_slide_scene = {"slide_id", "scene_id"}.issubset(df_data.columns)
    
    if has_slide_scene:
        df_data = df_data.with_columns(
            (
                pl.col("slide_id").cast(pl.Utf8).str.strip_chars()
                + "_"
                + pl.col("scene_id").cast(pl.Utf8).str.strip_chars()
            ).alias("sample_id")
        )
    elif "sample_id" not in df_data.columns:
        raise ValueError(
            "Missing sample identifier. Expected either both 'slide_id' and 'scene_id', "
            "or an existing 'sample_id' column."
        )
    else:
        df_data = df_data.with_columns(
            pl.col("sample_id").cast(pl.Utf8).str.strip_chars().alias("sample_id")
        )
    
    n_bad_sample_ids = df_data.select(
        (
            pl.col("sample_id").is_null()
            | (pl.col("sample_id").cast(pl.Utf8).str.strip_chars() == "")
        )
        .sum()
        .alias("n_bad_sample_ids")
    ).item()
    
    if n_bad_sample_ids > 0:
        raise ValueError("sample_id contains missing or empty values.")
    
    n_complete_samples = df_data.select(pl.col("sample_id").n_unique()).item()
    print(f"{n_complete_samples} samples with complete data")

    # Write Data
    print("Writing data")

    must_show_cols = ['sample_id', 'OID']
    missing_id = [c for c in must_show_cols if c not in df_data.columns]
    if missing_id:
        raise ValueError(f"Missing expected ID columns for reshape: {missing_id}")
    
    id_cols = ["sample_id", "slide_id", "scene_id", "scan_region", "OID", "X", "Y", "s.area"]
    id_cols = [c for c in id_cols if c in df_data.columns]

    marker_cols = [c for c in df_data.columns if c not in id_cols]

    numeric_marker_cols = [
        c for c in marker_cols
        if df_data.schema[c].is_numeric()
    ]
    
    non_numeric_marker_cols = [
        c for c in marker_cols
        if not df_data.schema[c].is_numeric()
    ]
    
    if len(numeric_marker_cols) == 0:
        raise ValueError("No numeric marker columns found. Cannot check all-zero marker expression.")
    
    if non_numeric_marker_cols:
        warnings.warn(
            "Non-numeric columns found outside ID columns and will not be used for all-zero filtering: "
            + ", ".join(non_numeric_marker_cols),
            RuntimeWarning,
        )
    
    print("Filtering cells with zero expression across all numeric markers")
    
    n_rows_before_zero_filter = df_data.height
    
    zero_marker_expr = (
        pl.sum_horizontal([
            pl.col(c).cast(pl.Float64, strict=False).abs()
            for c in numeric_marker_cols
        ]) == 0
    )
    
    n_zero_marker_rows = df_data.select(
        zero_marker_expr.sum().alias("n_zero_marker_rows")
    ).item()
    
    if n_zero_marker_rows > 0:
        warnings.warn(
            f"{n_zero_marker_rows} cells have zero expression across all numeric markers. "
            "Rows will be removed.",
            RuntimeWarning,
        )
    
        df_data = df_data.filter(~zero_marker_expr)
    
    print(
        f"Rows after all-zero marker filtering: "
        f"{df_data.height} / {n_rows_before_zero_filter}"
    )
    
    # Keep IDs first, then numeric markers, then any remaining non-numeric columns.
    df_data = df_data.select(id_cols + numeric_marker_cols + non_numeric_marker_cols)
    df_data.write_parquet(output_csv)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Merge csv files into a single file.")
    p.add_argument("--path.input.folder", required=True,
                   help="Path to input folder with csv files (directory).")
    p.add_argument("--path.output.csv", required=True,
                   help="Path to output csv file where the merged data will be stored (csv).")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    merge_data(
        input_folder=getattr(args, "path.input.folder"),
        output_csv=getattr(args, "path.output.csv"),
    )


if __name__ == "__main__":
    main()
