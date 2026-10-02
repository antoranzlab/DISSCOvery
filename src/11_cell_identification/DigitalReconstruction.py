#!/usr/bin/env python3

import argparse
import csv
from pathlib import Path

import numpy as np
import polars as pl
import tifffile
from scipy import ndimage
from skimage.segmentation import find_boundaries

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

def digital_reconstruction(input_csv_colors: str, input_segmented_dapi: str, input_csv: str,
                            output_folder: str) -> None:
    print(f"### input csv colors: {input_csv_colors} ###")
    print(f"### input csv data: {input_csv} ###")
    print(f"### input segmented object: {input_segmented_dapi} ###")
    print(f"### output folder: {output_folder} ###")

    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    print("Loading colors")
    df_dictionary = read_table(input_csv_colors).with_columns(
        pl.col("CellType").cast(pl.Utf8),
        pl.col("R").cast(pl.Float64), pl.col("G").cast(pl.Float64), pl.col("B").cast(pl.Float64),
    )
    print(df_dictionary)

    print("Loading data")
    df_data = read_table(input_csv).with_columns(
        pl.col("CellType").cast(pl.Utf8),
        (pl.col("slide_id") + "_" + pl.col("scene_id")).alias("tissue_id"),
    ).join(df_dictionary, on="CellType", how="left")

    print("Loading segmentation matrix")
    segmentation_matrix = np.load(input_segmented_dapi)

    print("Generating digital tissue")
    h, w = segmentation_matrix.shape
    tmp_red = np.zeros((h, w), dtype=np.float64)
    tmp_green = np.zeros((h, w), dtype=np.float64)
    tmp_blue = np.zeros((h, w), dtype=np.float64)

    # Dilated once, reused per CellType below -- segmentation_matrix doesn't change inside
    # the loop, so this is the same result the R source recomputed on every iteration.
    dilated = ndimage.grey_dilation(segmentation_matrix, size=(3, 3))

    for celltype in sorted(df_dictionary.select("CellType").unique().to_series().to_list()):
        tmp_data = df_data.filter(pl.col("CellType") == celltype)
        tmp_colors = df_dictionary.filter(pl.col("CellType") == celltype).unique(["R", "G", "B"]).row(0, named=True)
        r, g, b = tmp_colors["R"], tmp_colors["G"], tmp_colors["B"]

        # Exclude OID2 == 0 (a cell whose coordinates didn't land inside any segmented
        # object -- background/failed lookup): the R source didn't special-case this,
        # so a single such cell would match every background pixel (also labeled 0)
        # and paint the entire image in that cell's CellType color. Confirmed by
        # direct reproduction, not guessed -- fixed rather than ported literally.
        oid2s = [x for x in tmp_data.select("OID2").to_series().to_list() if x != 0]
        tmp_image = np.where(np.isin(dilated, oid2s), 1.0, 0.0) if oid2s else np.zeros_like(dilated, dtype=np.float64)

        tmp_red += r * tmp_image
        tmp_green += g * tmp_image
        tmp_blue += b * tmp_image

    tmp_plot = np.clip(np.stack([tmp_red, tmp_green, tmp_blue], axis=-1), 0, 1)

    # Outline each object's boundary in black, matching EBImage::paintObjects.
    boundaries = find_boundaries(segmentation_matrix, mode="outer")
    tmp_plot[boundaries] = 0

    print("Saving results")
    tissue_id = df_data.select("tissue_id").unique().to_series().to_list()[0]
    tifffile.imwrite(
        output_folder / f"{tissue_id}.tiff",
        (tmp_plot * 255).astype(np.uint8),
        compression="lzw",
    )

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Digital Reconstruction.")
    p.add_argument("--path.input.csv.colors", required=True,
                   help="Path to input csv where the selected colors are stored (csv).")
    p.add_argument("--path.input.csv", required=True,
                   help="Path to input csv where the data is stored (csv).")
    p.add_argument("--path.input.segmented.dapi", required=True,
                   help="Path to input npy where the segmented DAPI object is stored (npy).")
    p.add_argument("--path.output.folder", required=True,
                   help="Path to output directory where the digital tissue reconstruction will be saved (directory).")
    return p

def main() -> None:
    args = build_parser().parse_args()

    digital_reconstruction(
        input_csv_colors=getattr(args, "path.input.csv.colors"),
        input_segmented_dapi=getattr(args, "path.input.segmented.dapi"),
        input_csv=getattr(args, "path.input.csv"),
        output_folder=getattr(args, "path.output.folder"),
    )

if __name__ == "__main__":
    main()
