#!/usr/bin/env python3

import argparse
import csv
from pathlib import Path

import polars as pl


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
    out_dir = Path(path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    path_l = path.lower()

    if path_l.endswith(".parquet"):
        df.write_parquet(path)
    elif path_l.endswith(".csv"):
        df.write_csv(path)
    else:
        raise ValueError("Output must end with .csv or .parquet")


# input_csv = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/df_data_norm.parquet'
# output_csv = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/df_data_sampled.parquet'
# sampling_yes_no = 1
# n_cells = 25000
# selected_seed = 1234

def data_sampling(
    input_csv: str,
    output_csv: str,
    sampling_yes_no: int = 1,
    n_cells: int = 25000,
    selected_seed: int = 1234,
) -> None:
    print(f"### input normalized data: {input_csv} ###")
    print(f"### output sampled data: {output_csv} ###")
    print(f"### sampling.yes.no: {sampling_yes_no} ###")
    print(f"### number of sampled cells: {n_cells} ###")
    print(f"### selected seed: {selected_seed} ###")

    print("Loading normalized data")
    df_data = read_table(input_csv)

    # Basic checks
    missing_group_cols = [c for c in GROUP_COLS if c not in df_data.columns]
    
    if missing_group_cols:
        raise ValueError(
            "Missing required grouping columns: " + ", ".join(missing_group_cols)
        )

    df_data = df_data.with_columns([pl.col(c).cast(pl.Utf8).str.strip_chars().alias(c) for c in GROUP_COLS])
    
    bad_group_expr = pl.any_horizontal([pl.col(c).is_null() | (pl.col(c).cast(pl.Utf8).str.strip_chars() == "") for c in GROUP_COLS])
    n_bad_group_ids = df_data.select(bad_group_expr.sum().alias("n_bad_group_ids")).item()

    if n_bad_group_ids > 0:
        raise ValueError(
            "Grouping columns contain missing or empty values: " + ", ".join(GROUP_COLS)
        )

    total_rows = df_data.height

    if total_rows == 0:
        raise ValueError("No rows available; cannot sample.")

    if int(sampling_yes_no) == 1:
        print(f"Sampling cells proportionally by: {', '.join(GROUP_COLS)}")

        if n_cells <= 0:
            raise ValueError("number.of.cells must be > 0 when sampling is enabled.")

        if n_cells >= total_rows:
            print(
                f"Requested {n_cells} cells, but input only has {total_rows}. "
                "Returning all cells."
            )
            df_sampled = df_data
        
        else:
            counts = (df_data
                .group_by(GROUP_COLS)
                .len()
                .rename({"len": "N"})
                .with_columns(
                    ((pl.col("N") / total_rows) * n_cells)
                    .round()
                    .cast(pl.Int64)
                    .alias("k")
                )
                .with_columns(
                    pl.min_horizontal("k", "N").alias("k")
                )
            )

            print(
                f"{counts.height} groups detected; "
                f"{counts.select(pl.col('k').sum()).item()} cells will be sampled"
            )
            
            df_with_k = df_data.join(
                counts.select(GROUP_COLS + ["k"]),
                on=GROUP_COLS,
                how="left",
            )
            
            # Randomize rows, assign row number within each group, keep first k.
            df_sampled = (
                df_with_k
                .with_columns(
                    pl.int_range(0, pl.len())
                    .shuffle(seed=int(selected_seed))
                    .alias("_random_order")
                )
                .sort(GROUP_COLS + ["_random_order"])
                .with_columns(
                    pl.arange(0, pl.len())
                    .over(GROUP_COLS)
                    .alias("_rank_in_group")
                )
                .filter(pl.col("_rank_in_group") < pl.col("k"))
                .drop(["k", "_random_order", "_rank_in_group"])
            )
    else:
        print("Sampling skipped")
        df_sampled = df_data
    
    print(f"Output rows: {df_sampled.height}")
    print("Writing sampled data")
    write_table(df_sampled, output_csv)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sample data prior to clustering and dimensionality reduction.")
    parser.add_argument("--path.input.csv", required=True, help="Path to input csv/parquet file with normalized data.")
    parser.add_argument("--path.output.csv", required=True, help="Path to output csv/parquet where sampled data will be stored.")
    parser.add_argument("--sampling.yes.no", type=int, default=1, choices=[0, 1], help="Binary specifying whether sampling is performed: 1 yes, 0 no. Default: 1.")
    parser.add_argument("--number.of.cells", type=int, default=25000, help="Number of cells to sample. Default: 25000.")
    parser.add_argument("--selected.seed", type=int, default=1234, help="Selected seed for random sampling. Default: 1234.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    data_sampling(
        input_csv=getattr(args, "path.input.csv"),
        output_csv=getattr(args, "path.output.csv"),
        sampling_yes_no=getattr(args, "sampling.yes.no"),
        n_cells=getattr(args, "number.of.cells"),
        selected_seed=getattr(args, "selected.seed"),
    )


if __name__ == "__main__":
    main()
