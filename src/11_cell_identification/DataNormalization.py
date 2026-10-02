#!/usr/bin/env python3

import argparse
from pathlib import Path
import warnings
import csv

import polars as pl
# import numpy as np
# import pandas as pd

PREFERRED_ID_COLS = ["sample_id", "slide_id", "scene_id", "scan_region", "OID", "X", "Y", "s.area"]
GROUP_COLS = ["sample_id"]

def sniff_separator(fp: Path) -> str:
    with open(fp, "r", newline="") as f:
        sample = f.read(4096)

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        return dialect.delimiter
    except csv.Error:
        return ";"

def read_table(path: str) -> pl.DataFrame:
    path_obj = Path(path)
    path_l = path.lower()

    if not path_obj.exists():
        raise ValueError(f"Input file does not exist: {path}")

    if path_l.endswith(".parquet"):
        return pl.read_parquet(path)

    if path_l.endswith((".csv", ".txt", ".tsv")):
        sep = sniff_separator(path_obj)
        return pl.read_csv(
            path,
            separator=sep,
            infer_schema_length=10000,
            ignore_errors=False,
        )

    raise ValueError("Input must end with .csv, .txt, .tsv, or .parquet")

def write_table(df: pl.DataFrame, path: str) -> None:
    path_l = path.lower()
    out_dir = Path(path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    if path_l.endswith(".parquet"):
        df.write_parquet(path)
    elif path_l.endswith(".csv"):
        df.write_csv(path)
    else:
        raise ValueError("Output must end with .csv or .parquet")

# input_csv = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/df_data_merged.parquet'
# normalization_yes_no = 1
# output_csv = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/df_data_norm.parquet'

def data_normalization(input_csv: str, normalization_yes_no: int, output_csv: str, normalization_scope: str = "sample") -> None:
    print(f"### input csv: {input_csv} ###")
    print(f"### normalization.yes.no: {normalization_yes_no} ###")
    print(f"### normalization.scope: {normalization_scope} ###")
    print(f"### output csv: {output_csv} ###")

    group_cols = GROUP_COLS if normalization_scope == "sample" else []

    # Load table
    print("Loading input data")
    df_data = read_table(input_csv)

    if group_cols:
        missing_group_cols = [c for c in group_cols if c not in df_data.columns]

        if missing_group_cols:
            raise ValueError(
                "Missing required grouping columns: " + ", ".join(missing_group_cols)
            )

        df_data = df_data.with_columns([pl.col(c).cast(pl.Utf8).str.strip_chars().alias(c) for c in group_cols])

        # Validate group columns after cleaning
        bad_group_expr = pl.any_horizontal([pl.col(c).is_null() | (pl.col(c).cast(pl.Utf8).str.strip_chars() == "") for c in group_cols])
        n_bad_group_ids = df_data.select(bad_group_expr.sum().alias("n_bad_group_ids")).item()

        if n_bad_group_ids > 0:
            raise ValueError(
                "Grouping columns contain missing or empty values: " + ", ".join(group_cols)
            )

    id_cols = [c for c in PREFERRED_ID_COLS if c in df_data.columns]
    candidate_marker_cols = [c for c in df_data.columns if c not in id_cols]

    numeric_marker_cols = [
        c
        for c in candidate_marker_cols
        if df_data.schema[c].is_numeric()
    ]
    
    non_numeric_marker_cols = [
        c
        for c in candidate_marker_cols
        if not df_data.schema[c].is_numeric()
    ]

    if non_numeric_marker_cols:
        warnings.warn(
            "Non-numeric columns were found outside the ID columns and will not be normalized: "
            + ", ".join(non_numeric_marker_cols),
            RuntimeWarning,
        )

    if int(normalization_yes_no) == 1:
        if group_cols:
            print(f"Normalizing marker intensity values per: {', '.join(group_cols)}")
        else:
            print("Normalizing marker intensity values globally, per marker only (no sample grouping)")

        if len(numeric_marker_cols) == 0:
            warnings.warn("No numeric marker columns found to normalize.", RuntimeWarning)
            write_table(df_data, output_csv)
            return

        if group_cols:
            n_groups = df_data.select(pl.struct(group_cols).n_unique()).item()
            print(f"{n_groups} groups detected using: {', '.join(group_cols)}")
        print(f"{len(numeric_marker_cols)} numeric marker columns will be normalized")

        normalized_exprs = []

        for col in numeric_marker_cols:
            if group_cols:
                mean_expr = pl.col(col).mean().over(group_cols)
                sd_expr = pl.col(col).std(ddof=1).over(group_cols)
            else:
                mean_expr = pl.col(col).mean()
                sd_expr = pl.col(col).std(ddof=1)

            z_expr = (
                pl.when(sd_expr.is_null() | (sd_expr == 0))
                .then(0.0)
                .otherwise((pl.col(col) - mean_expr) / sd_expr)
                .clip(-5, 5)
                .alias(col)
            )

            normalized_exprs.append(z_expr)

        df_data = df_data.with_columns(normalized_exprs)
        
    else:
        print('Normalization skipped')

    # Keep IDs first, then numeric markers, then any remaining non-numeric columns.
    output_cols = id_cols + numeric_marker_cols + non_numeric_marker_cols
    df_data = df_data.select(output_cols)

    print("Writing output")
    write_table(df_data, output_csv)

    print("Done")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize cell-level marker data.")
    parser.add_argument("--path.input.csv", required=True, help="Path to input csv/parquet with merged data.")
    parser.add_argument("--normalization.yes.no", required=True, type=int, choices=[0, 1], help="Binary specifying whether normalization is performed: 1 yes, 0 no.")
    parser.add_argument("--normalization.scope", default="sample", choices=["sample", "global"],
                        help="'sample' (default): z-score each marker per sample_id (slide+scene), the original behavior. "
                             "'global': z-score each marker across the whole dataset, with no sample grouping.")
    parser.add_argument("--path.output.csv", required=True, help="Path to output csv/parquet file where normalized data will be stored.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    data_normalization(
        input_csv=getattr(args, "path.input.csv"),
        normalization_yes_no=getattr(args, "normalization.yes.no"),
        output_csv=getattr(args, "path.output.csv"),
        normalization_scope=getattr(args, "normalization.scope"),
    )


if __name__ == "__main__":
    main()
