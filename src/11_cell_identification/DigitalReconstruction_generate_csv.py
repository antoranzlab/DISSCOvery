#!/usr/bin/env python3

import argparse
import os
from pathlib import Path

import polars as pl

def digital_reconstruction_generate_csv(input_annotation_log_folder: str, input_segmented_dapi_folder: str,
                                         input_overlapping_mask_folder: str, output_csv: str,
                                         ref_round: str = "R01") -> None:
    print(f"### annotation log: {input_annotation_log_folder} ###")
    print(f"### input segmented object folder: {input_segmented_dapi_folder} ###")
    print(f"### input overlapping mask folder: {input_overlapping_mask_folder} ###")
    print(f"### output csv: {output_csv} ###")
    print(f"### reference round: {ref_round} ###")

    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)

    print("Listing annotated cells")
    annotated_rows = []
    for f in sorted(os.listdir(input_annotation_log_folder)):
        if not f.endswith(".csv"):
            continue
        slide_id, scene_id = Path(f).stem.split("_", 1)
        annotated_rows.append({"tissue_id": f"{slide_id}_{scene_id}", "annotated_cells": f})
    tmp_annotated_cells = pl.DataFrame(annotated_rows)

    print("Listing segmented objects")
    # Segmentation only ever runs on the reference round (see FeatureExtraction.py's own
    # ref_round-only matrix selection) -- filenames follow the disscovery convention
    # <slide>_<round>_<version>_<project>_<user>_<scan_region>_<channel>.npy.
    segmented_rows = []
    segmentation_root = Path(input_segmented_dapi_folder)
    for path in sorted(segmentation_root.rglob("*.npy")):
        parts = path.stem.split("_")
        if len(parts) != 7:
            continue
        slide_id, round_number, _version, _project, _user, scan_region, _channel = parts
        if round_number != ref_round or _channel != "DAPI":
            continue
        scene_id = "scene" + str(int(scan_region.replace("S", "")) + 1).zfill(2)
        segmented_rows.append({"tissue_id": f"{slide_id}_{scene_id}",
                               "segmented_objects": str(path.relative_to(segmentation_root))})
    tmp_segmented_objects = pl.DataFrame(segmented_rows)

    print("Listing overlapping masks")
    ovl_rows = []
    for f in sorted(os.listdir(input_overlapping_mask_folder)):
        if not f.endswith(".tiff"):
            continue
        ovl_rows.append({"tissue_id": Path(f).stem, "ovl_mask": f})
    tmp_ovl_masks = pl.DataFrame(ovl_rows)

    print("Merging lists")
    for label, rows in [("annotated cells", annotated_rows),
                        ("segmented objects", segmented_rows), ("overlapping masks", ovl_rows)]:
        ids = [row["tissue_id"] for row in rows]
        if not ids:
            raise ValueError(f"No {label} found")
        if len(ids) != len(set(ids)):
            raise ValueError(f"Multiple {label} files for the same tissue; select one reference version")
    annotated_ids = {row["tissue_id"] for row in annotated_rows}
    for label, rows in [("segmented objects", segmented_rows), ("overlapping masks", ovl_rows)]:
        missing = annotated_ids - {row["tissue_id"] for row in rows}
        if missing:
            raise ValueError(f"Missing {label} for annotated tissues: {sorted(missing)}")
    tmp_csv = (
        tmp_annotated_cells
        .join(tmp_segmented_objects, on="tissue_id", how="inner")
        .join(tmp_ovl_masks, on="tissue_id", how="inner")
    )
    tmp_csv = tmp_csv.drop_nulls()

    print("Saving csv")
    tmp_csv.write_csv(output_csv)

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Digital Reconstruction generate csv.")
    p.add_argument("--path.input.annotation.log.folder", required=True,
                   help="Path to input folder where the per-scene annotation logs are stored (directory).")
    p.add_argument("--path.input.segmented.dapi.folder", required=True,
                   help="Path to input folder where the segmented DAPI object is stored (directory).")
    p.add_argument("--path.input.overlapping.mask.folder", required=True,
                   help="Path to input folder where the overlapping mask is stored (directory).")
    p.add_argument("--path.output.csv", required=True,
                   help="Path to output csv where the results will be stored (csv).")
    p.add_argument("--ref_round", default="R01",
                   help="Reference round whose segmentation matrices to use (default: R01).")
    return p

def main() -> None:
    args = build_parser().parse_args()

    digital_reconstruction_generate_csv(
        input_annotation_log_folder=getattr(args, "path.input.annotation.log.folder"),
        input_segmented_dapi_folder=getattr(args, "path.input.segmented.dapi.folder"),
        input_overlapping_mask_folder=getattr(args, "path.input.overlapping.mask.folder"),
        output_csv=getattr(args, "path.output.csv"),
        ref_round=args.ref_round,
    )

if __name__ == "__main__":
    main()
