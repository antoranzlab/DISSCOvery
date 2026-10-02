#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Any, List
import pandas as pd

def generate_scenes_csv(
    input_path_bb: str | Path,
    reference_map: Dict[str, Dict[str, str]],
    output_path_csv: str | Path,
) -> None:
    """
    Generate the scenes CSV from bounding-box CSV files.

    Parameters
    ----------
    input_path_bb : str or Path
        Path to the folder containing subfolders with bounding box CSVs.
    reference_map : dict
        Dictionary keyed by slide_id. Each value must be a dictionary with:
            - reference_round
            - reference_version
    output_path_csv : str or Path
        Output CSV path.
    """
    input_path_bb = Path(input_path_bb)
    output_path_csv = Path(output_path_csv)

    print(f"### input path bounding boxes: {input_path_bb} ###")
    print(f"### output path csv job list: {output_path_csv} ###")

    if not output_path_csv.parent.exists():
        print(f"### creating folder: {output_path_csv.parent} ###")
        output_path_csv.parent.mkdir(parents=True, exist_ok=True)

    # List first-level folders only
    tmp_folders = [p for p in input_path_bb.iterdir() if p.is_dir()]

    file_records: List[Dict[str, Any]] = []

    for folder in tmp_folders:
        for csv_file in folder.glob("*.csv"):
            stem_parts = csv_file.stem.split("_")

            if len(stem_parts) != 6:
                # Skip malformed filenames
                print(f"Skipping malformed filename: {csv_file.name}")
                continue

            slide_id, round_id, version_id, project_id, user_id, channel_id = stem_parts

            if slide_id not in reference_map:
                # Skip slides not present in reference map
                print(f"Skipping {csv_file.name}: slide_id '{slide_id}' not in reference_map")
                continue

            ref_info = reference_map[slide_id]
            ref_round = ref_info.get("reference_round")
            ref_version = ref_info.get("reference_version")

            if round_id == ref_round and version_id == ref_version:
                file_records.append(
                    {
                        "folder": folder.name,
                        "ofile": csv_file.name,
                        "slide_id": slide_id,
                        "round_id": round_id,
                        "version_id": version_id,
                        "project_id": project_id,
                        "user_id": user_id,
                        "channel_id": channel_id,
                    }
                )

    if not file_records:
        print("No matching files found.")
        pd.DataFrame().to_csv(output_path_csv, index=False)
        return

    df_files = pd.DataFrame(file_records)

    csv_dfs = []

    for _, tmp_file in df_files.iterrows():
        csv_path = input_path_bb / tmp_file["folder"] / tmp_file["ofile"]
        tmp_csv = pd.read_csv(csv_path)

        # Equivalent to mutate(meanr = (minr+maxr)/2, meanc = (minc+maxc)/2)
        tmp_csv["meanr"] = (tmp_csv["minr"] + tmp_csv["maxr"]) / 2
        tmp_csv["meanc"] = (tmp_csv["minc"] + tmp_csv["maxc"]) / 2

        # Recover metadata from filename
        stem_parts = Path(tmp_file["ofile"]).stem.split("_")
        slide_id, round_id, version_id, project_id, user_id, channel_id = stem_parts

        tmp_csv["slide_id"] = slide_id
        tmp_csv["round_id"] = round_id
        tmp_csv["version_id"] = version_id
        tmp_csv["project_id"] = project_id
        tmp_csv["user_id"] = user_id
        tmp_csv["channel_id"] = channel_id

        # Equivalent to scene_number = as.numeric(sub('S', '', scan_region))+1
        tmp_csv["scene_number"] = (
            tmp_csv["scan_region"]
            .astype(str)
            .str.replace("S", "", regex=False)
            .astype(int)
            + 1
        )

        # Equivalent renaming
        tmp_csv = tmp_csv.rename(
            columns={
                "project_id": "project_name",
                "slide_id": "slide_name",
                "user_id": "project_leader",
            }
        )
        tmp_csv["project_operator"] = tmp_csv["project_leader"]

        # Equivalent to mutate(slide_number_scenes = n_distinct(scene_number))
        tmp_csv["slide_number_scenes"] = tmp_csv["scene_number"].nunique()

        # Equivalent to mutate(QC_include = 1)
        tmp_csv["QC_include"] = 1

        csv_dfs.append(tmp_csv)

    df_csv = pd.concat(csv_dfs, ignore_index=True)
    df_csv.to_csv(output_path_csv, index=False)
    
def main() -> None:
    parser = argparse.ArgumentParser(description="STS - generate scenes csv.")

    parser.add_argument(
        "--input_path_bb",
        required=True,
        help="Path to input bounding boxes (directory).",
    )
    parser.add_argument(
        "--reference_map_json",
        required=True,
        help=(
            "Path to a JSON file containing the reference mapping per slide. "
            "Example: "
            '{"SLIDE001": {"reference_round": "R01", "reference_version": "V01"}}'
        ),
    )
    parser.add_argument(
        "--output_path_csv",
        required=True,
        help="Path to output CSV where the scene CSV will be saved.",
    )

    args = parser.parse_args()

    with open(args.reference_map_json, "r", encoding="utf-8") as f:
        reference_map = json.load(f)

    generate_scenes_csv(
        input_path_bb=args.input_path_bb,
        reference_map=reference_map,
        output_path_csv=args.output_path_csv,
    )


if __name__ == "__main__":
    main()
