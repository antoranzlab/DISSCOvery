#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import json
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

def reverse_transformation_job_list(
    input_path_tm: str | Path,
    input_path_masks: str | Path,
    input_path_bb: str | Path,
    input_path_hard_stitching: str | Path,
    output_path_masks: str | Path,
    output_path_bb: str | Path,
    reference_map: Dict[str, Dict[str, str]],
    output_path_csv: str | Path,
) -> None:

    input_path_tm = Path(input_path_tm)
    input_path_masks = Path(input_path_masks)
    input_path_bb = Path(input_path_bb)
    input_path_hard_stitching = Path(input_path_hard_stitching)
    output_path_masks = Path(output_path_masks)
    output_path_bb = Path(output_path_bb)
    output_path_csv = Path(output_path_csv)

    print(f"### input path transformation matrices: {input_path_tm} ###")
    print(f"### input path foreground masks: {input_path_masks} ###")
    print(f"### input path bounding boxes: {input_path_bb} ###")
    print(f"### input path hard stitching (native shape reference): {input_path_hard_stitching} ###")
    print(f"### output path foreground masks: {output_path_masks} ###")
    print(f"### output path bounding boxes: {output_path_bb} ###")
    print(f"### output path csv job list: {output_path_csv} ###")

    output_path_masks.mkdir(parents=True, exist_ok=True)
    output_path_bb.mkdir(parents=True, exist_ok=True)
    output_path_csv.parent.mkdir(parents=True, exist_ok=True)

    # First-level folders only
    tmp_folders = [p for p in input_path_tm.iterdir() if p.is_dir()]

    file_records: List[Dict[str, str]] = []

    for folder in tmp_folders:
        for npy_file in folder.iterdir():
            if not npy_file.is_file():
                continue
            if npy_file.suffix.lower() != ".npy":
                continue

            stem = npy_file.stem
            stem = stem.replace("AF_FITC", "AFFITC")

            stem_parts = stem.split("_")

            if len(stem_parts) != 6:
                print(f"Skipping malformed filename: {npy_file.name}")
                continue

            slide_id, round_id, version_id, project_id, user_id, channel_id = stem_parts

            if slide_id not in reference_map:
                # Skip slides not present in reference map
                print(f"Skipping {npy_file.name}: slide_id '{slide_id}' not in reference_map")
                continue

            ref_info = reference_map[slide_id]
            ref_round = ref_info.get("reference_round")
            ref_version = ref_info.get("reference_version")

            file_records.append(
                {
                    "folder": folder.name,
                    "ofile": npy_file.name,
                    "slide_id": slide_id,
                    "round_number": round_id,
                    "version_id": version_id,
                    "project_id": project_id,
                    "user_id": user_id,
                    "channel_id": channel_id,
                    "reference_round": ref_round,
                    "reference_version": ref_version,
                    "input_path_tm": str(input_path_tm / slide_id / npy_file.name),
                    "query_native_shape_path": str(input_path_hard_stitching / slide_id / f"{npy_file.stem}.tiff"),
                    "output_path_masks": str(output_path_masks / slide_id / f"{npy_file.stem}.tiff"),
                    "output_path_bb": str(output_path_bb / slide_id / f"{npy_file.stem}.csv"),
                }
            )

    df_files = pd.DataFrame(file_records)

    if df_files.empty:
        raise ValueError(f"No .npy files found under {input_path_tm}")

    ref_files = (
        df_files.loc[
            (df_files["round_number"] == df_files["reference_round"])
            & (df_files["version_id"] == df_files["reference_version"]),
            ["slide_id", "ofile"],
        ]
        .copy()
    )

    ref_files["input_path_masks"] = ref_files.apply(lambda row: str(input_path_masks / row["slide_id"] / re.sub(r"\.npy$", ".tiff", row["ofile"])), axis=1)
    ref_files["input_path_bb"] = ref_files.apply(lambda row: str(input_path_bb / row["slide_id"] / re.sub(r"\.npy$", ".csv", row["ofile"])), axis=1)
    ref_files = ref_files[["slide_id", "input_path_masks", "input_path_bb"]]

    job_list = (
        df_files[["slide_id", "input_path_tm", "query_native_shape_path", "output_path_masks", "output_path_bb"]]
        .merge(ref_files, how="left", on="slide_id")
        .drop(columns=["slide_id"])
    )

    job_list.to_csv(output_path_csv, index=False)

def main() -> None:
    parser = argparse.ArgumentParser(description="STS - reverse transformation - list jobs.")

    parser.add_argument("--input_path_tm", required=True, help="Path to input transformation matrices (path).")
    parser.add_argument("--input_path_masks", required=True, help="Path to input masks (path).")
    parser.add_argument("--input_path_bb", required=True, help="Path to input bounding boxes (path).")
    parser.add_argument("--input_path_hard_stitching", required=True, help="Path to per-round hard-stitched images, used only for their native shape (path).")
    parser.add_argument("--output_path_masks", required=True, help="Path to output masks (path).")
    parser.add_argument( "--output_path_bb", required=True, help="Path to output bounding boxes (path).")
    parser.add_argument("--reference_map_json", required=True,
        help=(
            "Path to a JSON file containing the reference mapping per slide. "
            "Example: "
            '{"SLIDE001": {"reference_round": "R01", "reference_version": "V01"}}'
        ))
    parser.add_argument("--output_path_csv", required=True, help="Path to output csv where the job list will be saved (.csv).")

    args = parser.parse_args()

    with open(args.reference_map_json, "r", encoding="utf-8") as f:
        reference_map = json.load(f)

    reverse_transformation_job_list(
        input_path_tm=args.input_path_tm,
        input_path_masks=args.input_path_masks,
        input_path_bb=args.input_path_bb,
        input_path_hard_stitching=args.input_path_hard_stitching,
        output_path_masks=args.output_path_masks,
        output_path_bb=args.output_path_bb,
        reference_map=reference_map,
        output_path_csv=args.output_path_csv,
    )

if __name__ == "__main__":
    main()
