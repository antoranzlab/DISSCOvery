#!/usr/bin/env python3

import argparse
import csv
from pathlib import Path

import polars as pl


REQUIRED_ID_COLS = ["sample_id", "OID"]


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
        raise ValueError(f"Input path does not exist: {path}")

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
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    path_l = path.lower()

    if path_l.endswith(".parquet"):
        df.write_parquet(path)
    elif path_l.endswith(".csv"):
        df.write_csv(path)
    else:
        raise ValueError("Output must end with .csv or .parquet")


def validate_required_ids(df: pl.DataFrame, label: str) -> None:
    missing = [c for c in REQUIRED_ID_COLS if c not in df.columns]

    if missing:
        raise ValueError(
            f"{label} is missing required ID columns: " + ", ".join(missing)
        )

    bad_id_expr = pl.any_horizontal([
        pl.col(c).is_null() | (pl.col(c).cast(pl.Utf8).str.strip_chars() == "")
        for c in REQUIRED_ID_COLS
    ])

    n_bad_ids = df.select(bad_id_expr.sum().alias("n_bad_ids")).item()

    if n_bad_ids > 0:
        raise ValueError(
            f"{label} contains missing or empty values in required ID columns: "
            + ", ".join(REQUIRED_ID_COLS)
        )


def clean_required_ids(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns([
        pl.col(c).cast(pl.Utf8).str.strip_chars().alias(c)
        for c in REQUIRED_ID_COLS
    ])


def load_selected_celltypes(path_split_celltypes: str) -> list[str]:
    df_celltypes = read_table(path_split_celltypes)

    required = {"CellType", "include"}
    missing = required - set(df_celltypes.columns)

    if missing:
        raise ValueError(
            "CellType selection file must contain columns: CellType, include. "
            f"Missing: {sorted(missing)}"
        )

    selected = (
        df_celltypes
        .with_columns([
            pl.col("CellType").cast(pl.Utf8).str.strip_chars().alias("CellType"),
            pl.col("include").cast(pl.Int64, strict=False).fill_null(0).alias("include"),
        ])
        .filter(pl.col("include") == 1)
        .filter(
            pl.col("CellType").is_not_null()
            & (pl.col("CellType").str.strip_chars() != "")
        )
        .select("CellType")
        .unique()
        .sort("CellType")
        .to_series()
        .to_list()
    )

    if len(selected) == 0:
        raise ValueError("No CellTypes selected. Expected include == 1 for at least one row.")

    return selected


# input_data = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/df_data_norm.parquet'
# input_annotations = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/fingerprint_mapping/fingerprint_predictions.parquet'
# split_celltypes = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/selected_celltypes_c01.csv'
# output_csv = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/c01/df_data_merged.parquet'

def data_filtering(
    input_data: str,
    input_annotations: str,
    split_celltypes: str,
    output_csv: str,
    keep_celltype_column: int = 0,
    min_prediction_confidence: float | None = None,
    allowed_prediction_status: str | None = None,
) -> None:
    print(f"### input data: {input_data} ###")
    print(f"### input annotations: {input_annotations} ###")
    print(f"### split celltypes: {split_celltypes} ###")
    print(f"### output data: {output_csv} ###")
    print(f"### keep CellType column: {keep_celltype_column} ###")
    print(f"### min prediction confidence: {min_prediction_confidence} ###")
    print(f"### allowed prediction status: {allowed_prediction_status} ###")

    print("Loading selected CellTypes")
    selected_celltypes = load_selected_celltypes(split_celltypes)
    print("Selected CellTypes:")
    print(selected_celltypes)

    print("Loading input data")
    df_data = read_table(input_data)
    validate_required_ids(df_data, "input data")
    df_data = clean_required_ids(df_data)

    print("Loading annotations")
    df_ann = read_table(input_annotations)
    validate_required_ids(df_ann, "input annotations")
    df_ann = clean_required_ids(df_ann)

    if "CellType" not in df_ann.columns:
        raise ValueError("Annotation file must contain a 'CellType' column.")

    df_ann = df_ann.with_columns(
        pl.col("CellType").cast(pl.Utf8).str.strip_chars().alias("CellType")
    )

    # Optional filtering by prediction confidence / status.
    if min_prediction_confidence is not None:
        if "prediction_confidence" not in df_ann.columns:
            raise ValueError(
                "--min.prediction.confidence was provided, but input annotations "
                "do not contain 'prediction_confidence'."
            )

        df_ann = df_ann.filter(
            pl.col("prediction_confidence").cast(pl.Float64, strict=False)
            >= float(min_prediction_confidence)
        )

    if allowed_prediction_status is not None:
        allowed_status = [
            x.strip()
            for x in str(allowed_prediction_status).split(",")
            if x.strip() != ""
        ]

        if "prediction_status" not in df_ann.columns:
            raise ValueError(
                "--allowed.prediction.status was provided, but input annotations "
                "do not contain 'prediction_status'."
            )

        df_ann = df_ann.filter(pl.col("prediction_status").is_in(allowed_status))

    # Keep only one annotation row per cell.
    annotation_cols = [
        c for c in [
            "CellType",
            "prediction_confidence",
            "prediction_margin",
            "prediction_status",
            "node_id",
            "version_id",
        ]
        if c in df_ann.columns
    ]

    df_ann = (
        df_ann
        .select(REQUIRED_ID_COLS + annotation_cols)
        .unique(subset=REQUIRED_ID_COLS, keep="first")
    )

    print("Filtering annotations to selected CellTypes")
    df_ann_selected = df_ann.filter(pl.col("CellType").is_in(selected_celltypes))

    print(f"Annotated cells before filtering: {df_ann.height}")
    print(f"Annotated cells after filtering:  {df_ann_selected.height}")

    if df_ann_selected.height == 0:
        raise ValueError("Filtering selected zero cells. Check selected CellTypes.")

    print("Joining selected annotations to input data")
    df_filtered = df_data.join(
        df_ann_selected.select(REQUIRED_ID_COLS + ["CellType"]),
        on=REQUIRED_ID_COLS,
        how="inner",
    )

    print(f"Input rows:    {df_data.height}")
    print(f"Filtered rows: {df_filtered.height}")

    if df_filtered.height == 0:
        raise ValueError("Join returned zero rows. Check sample_id/OID consistency.")

    if int(keep_celltype_column) == 0:
        df_filtered = df_filtered.drop("CellType")

    print("Writing filtered data")
    write_table(df_filtered, output_csv)

    print("Done")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Filter full normalized data to selected annotated CellTypes for downstream "
            "subpopulation re-analysis."
        )
    )

    parser.add_argument(
        "--path.input.data",
        required=True,
        help="Path to full normalized data csv/parquet.",
    )

    parser.add_argument(
        "--path.input.annotations",
        required=True,
        help=(
            "Path to annotation file csv/parquet. Usually "
            "fingerprint_mapping/fingerprint_predictions.parquet or annotation_log.csv."
        ),
    )

    parser.add_argument(
        "--path.split.celltypes",
        required=True,
        help="CSV/parquet with columns CellType and include.",
    )

    parser.add_argument(
        "--path.output.csv",
        required=True,
        help="Path to output filtered data csv/parquet.",
    )

    parser.add_argument(
        "--keep.celltype.column",
        type=int,
        default=0,
        choices=[0, 1],
        help="Keep CellType in the filtered output. Default: 0.",
    )

    parser.add_argument(
        "--min.prediction.confidence",
        type=float,
        default=None,
        help="Optional minimum prediction confidence.",
    )

    parser.add_argument(
        "--allowed.prediction.status",
        default=None,
        help=(
            "Optional comma-separated list of allowed prediction_status values, "
            "e.g. high_confidence,medium_confidence."
        ),
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    data_filtering(
        input_data=getattr(args, "path.input.data"),
        input_annotations=getattr(args, "path.input.annotations"),
        split_celltypes=getattr(args, "path.split.celltypes"),
        output_csv=getattr(args, "path.output.csv"),
        keep_celltype_column=getattr(args, "keep.celltype.column"),
        min_prediction_confidence=getattr(args, "min.prediction.confidence"),
        allowed_prediction_status=getattr(args, "allowed.prediction.status"),
    )


if __name__ == "__main__":
    main()
