#!/usr/bin/env python3

import argparse
import csv
from pathlib import Path

import numpy as np
import polars as pl
import tifffile
from scipy import ndimage

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

def digital_reconstruction_aux(input_csv_scene: str, input_segmented_dapi: str, input_overlapping_mask: str,
                                output_folder: str, min_object_fraction: float = 0.01) -> None:
    print(f"### input csv scene: {input_csv_scene} ###")
    print(f"### input segmented object: {input_segmented_dapi} ###")
    print(f"### input overlapping mask: {input_overlapping_mask} ###")
    print(f"### output folder: {output_folder} ###")

    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    print("Loading data file")
    df_data = read_table(input_csv_scene)
    df_data = df_data.with_columns(
        (pl.col("slide_id") + "_" + pl.col("scene_id")).alias("tissue_id")
    )
    tissue_id = df_data.select("tissue_id").unique().to_series().to_list()[0]

    print("Loading segmented object")
    # No transpose here (unlike the R source's `%>% t()`): that transpose was purely to
    # reconcile numpy's row-major layout with R's column-major convention when the array
    # crossed the reticulate boundary. Plain numpy already indexes as [row, col] = [Y, X],
    # which is what the per-cell OID2 lookup below expects.
    segmentation_matrix = np.load(input_segmented_dapi)

    print("Loading overlapping mask")
    tmp_mask = tifffile.imread(input_overlapping_mask)
    if tmp_mask.shape != segmentation_matrix.shape:
        raise ValueError(f"Mask and segmentation shapes differ: {tmp_mask.shape} vs {segmentation_matrix.shape}")

    print("Applying QC filters")
    # Label connected components of the mask and keep only ones that are a meaningful
    # fraction of the total foreground area (drops tiny stray/noise blobs), then crop both
    # mask and segmentation matrix to one overall bounding box spanning every surviving
    # component. Ported from a genuinely ambiguous piece of the R source (`tmp_df_objects$value`
    # ends up as a vector used in a scalar-shaped `!=` comparison due to a missing group_by
    # before `summarise`, which in R silently recycles rather than erroring) -- implemented
    # here as the behavior the surrounding crop/mask code clearly intends: filter out small
    # components, keep one bounding box over the rest. Not yet validated against real
    # overlapping-mask data; verify before trusting in production.
    tmp_objects, _n_labels = ndimage.label(tmp_mask)
    labels, counts = np.unique(tmp_objects[tmp_objects != 0], return_counts=True)
    total_foreground = counts.sum()
    keep_labels = labels[counts / total_foreground > min_object_fraction] if total_foreground > 0 else np.array([])

    keep_mask = np.isin(tmp_objects, keep_labels)
    rows, cols = np.nonzero(keep_mask)
    if rows.size == 0:
        raise ValueError(f"No objects in overlapping mask survive the {min_object_fraction:.0%} size filter: {input_overlapping_mask}")
    r1, r2, c1, c2 = rows.min(), rows.max(), cols.min(), cols.max()

    tmp_mask = np.where(keep_mask, tmp_mask, 0)
    tmp_mask = ndimage.binary_dilation(tmp_mask > 0)
    tmp_mask = tmp_mask[r1:r2 + 1, c1:c2 + 1]
    tmp_mask = ndimage.binary_dilation(tmp_mask)

    segmentation_matrix = segmentation_matrix[r1:r2 + 1, c1:c2 + 1]
    segmentation_matrix = segmentation_matrix * tmp_mask

    print("Identifying objects in space")
    obj_labels, obj_sizes = np.unique(segmentation_matrix[segmentation_matrix != 0], return_counts=True)
    segmentation_matrix = np.where(np.isin(segmentation_matrix, obj_labels), segmentation_matrix, 0)

    # FeatureExtraction stores coordinates in the original scene frame. Subtract
    # the crop origin for lookup; cells outside retained coverage map to background.
    # Preserve X/Y in the annotation table so they remain comparable to features.
    x = df_data["X"].to_numpy()
    y = df_data["Y"].to_numpy()
    finite = np.isfinite(x) & np.isfinite(y)
    col = np.where(finite, x, 0).astype(np.int64) - c1
    row = np.where(finite, y, 0).astype(np.int64) - r1
    valid = finite & (row >= 0) & (col >= 0)
    valid &= (row < segmentation_matrix.shape[0]) & (col < segmentation_matrix.shape[1])
    oid2 = np.zeros(len(df_data), dtype=np.int64)
    oid2[valid] = segmentation_matrix[row[valid], col[valid]]
    df_data = df_data.with_columns(pl.Series("OID2", oid2))

    print("Saving results")
    write_table(df_data, str(output_folder / f"{tissue_id}.csv"))

    keep_oid2 = set(df_data.select("OID2").to_series().to_list())
    segmentation_matrix = np.where(np.isin(segmentation_matrix, list(keep_oid2)), segmentation_matrix, 0)
    np.save(output_folder / f"{tissue_id}.npy", segmentation_matrix)

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Digital Reconstruction auxiliary preprocessing.")
    p.add_argument("--path.input.csv.scene", required=True,
                   help="Path to input csv where the annotated data for the scene is stored (csv).")
    p.add_argument("--path.input.segmented.dapi", required=True,
                   help="Path to input npy where the segmented DAPI object is stored (npy).")
    p.add_argument("--path.input.overlapping.mask", required=True,
                   help="Path to input tiff where the overlapping mask is stored (tiff).")
    p.add_argument("--path.output.folder", required=True,
                   help="Path to output directory (directory).")
    return p

def main() -> None:
    args = build_parser().parse_args()

    digital_reconstruction_aux(
        input_csv_scene=getattr(args, "path.input.csv.scene"),
        input_segmented_dapi=getattr(args, "path.input.segmented.dapi"),
        input_overlapping_mask=getattr(args, "path.input.overlapping.mask"),
        output_folder=getattr(args, "path.output.folder"),
    )

if __name__ == "__main__":
    main()
