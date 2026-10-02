#!/usr/bin/env python3

import argparse
import csv
from pathlib import Path

import polars as pl

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
        return pl.read_csv(path, separator=sep, infer_schema_length=10000, ignore_errors=False)

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

def preprocessing_for_digital_reconstruction(input_csv: str, output_folder: str) -> None:
    print(f"### input csv: {input_csv} ###")
    print(f"### output folder: {output_folder} ###")

    output_folder = Path(output_folder)
    cell_annotations_folder = output_folder / "cell_annotations"
    cell_annotations_folder.mkdir(parents=True, exist_ok=True)

    print("Loading instruction csv")
    df_csv = read_table(input_csv)

    required = {"path_log_file", "include", "CellType"}
    missing = required - set(df_csv.columns)
    if missing:
        raise ValueError(f"Instruction csv missing required columns: {sorted(missing)}")

    print("Loading annotations")
    annotation_frames = []
    for path_log_file in df_csv.select("path_log_file").unique().to_series().to_list():
        tmp_csv = df_csv.filter(
            (pl.col("path_log_file") == path_log_file) & (pl.col("include") == 1)
        )
        celltypes = tmp_csv.select(pl.col("CellType").cast(pl.String)).unique().to_series().to_list()
        log_folder = Path(path_log_file)
        log_path = log_folder / "annotation_log.parquet"
        if not log_path.exists():
            log_path = log_folder / "annotation_log.csv"
        tmp_annotations = read_table(str(log_path)).with_columns(pl.col("CellType").cast(pl.String))
        tmp_annotations = tmp_annotations.filter(pl.col("CellType").is_in(celltypes))
        annotation_frames.append(tmp_annotations)

    df_annotations = pl.concat(annotation_frames, how="vertical")

    print("Evaluating conflicts")
    # A conflict is a cell (slide_id, scene_id, OID) annotated with more than one
    # CellType across the included annotation logs -- e.g. it fell inside two
    # different manually-drawn regions with different labels.
    conflict_id = (
        df_annotations.group_by(["slide_id", "scene_id", "OID"], maintain_order=True)
        .agg(pl.col("CellType").sort().str.join("___").alias("conflict_id"), pl.len().alias("N"))
    )
    df_annotations = df_annotations.join(conflict_id, on=["slide_id", "scene_id", "OID"], how="left")

    df_conflicts = df_annotations.filter(pl.col("N") > 1).sort(["slide_id", "scene_id", "OID"])

    if df_conflicts.height > 0:
        print("Solving conflicts")
        # Global per-CellType cell counts across all annotations, used to break
        # conflicts in favor of the rarer (more specific) label among the
        # conflicting set -- a common class is less likely to be starved of
        # examples by losing a contested cell than a rare one is.
        tmp_cytometry = df_annotations.group_by("CellType").agg(pl.len().alias("N"))

        resolved_parts = [df_annotations.filter(pl.col("N") <= 1)]
        for tmp_c in df_conflicts.select("conflict_id").unique().to_series().to_list():
            tmp_ct = tmp_c.split("___")
            counts = tmp_cytometry.filter(pl.col("CellType").is_in(tmp_ct))
            min_n = counts.select(pl.col("N").min()).item()
            keep_celltypes = counts.filter(pl.col("N") == min_n).select("CellType").to_series().to_list()
            solved = df_annotations.filter(
                (pl.col("conflict_id") == tmp_c) & (pl.col("CellType").is_in(keep_celltypes))
            )
            resolved_parts.append(solved)
        df_annotations = pl.concat(resolved_parts, how="vertical")

    print("Writing data")
    df_annotations = df_annotations.drop("conflict_id", "N").with_columns(
        (pl.col("slide_id") + "_" + pl.col("scene_id")).alias("tissue_id")
    )

    for tissue_id in df_annotations.select("tissue_id").unique().to_series().to_list():
        tmp_annotations = df_annotations.filter(pl.col("tissue_id") == tissue_id).drop("tissue_id")
        write_table(tmp_annotations, str(cell_annotations_folder / f"{tissue_id}.csv"))

    write_table(df_conflicts, str(output_folder / "conflicting_cells.csv"))

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Bridge the gap between cell identification and digital reconstruction.")
    p.add_argument("--path.input.csv", required=True,
                   help="Path to input csv listing the annotation logs/CellTypes to include (csv).")
    p.add_argument("--path.output.folder", required=True,
                   help="Path to output directory where the per-scene annotation csvs will be stored (directory).")
    return p

def main() -> None:
    args = build_parser().parse_args()

    preprocessing_for_digital_reconstruction(
        input_csv=getattr(args, "path.input.csv"),
        output_folder=getattr(args, "path.output.folder"),
    )

if __name__ == "__main__":
    main()
