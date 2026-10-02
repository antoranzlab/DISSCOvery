#!/usr/bin/env python
"""Generate the experimental design for AKOYA - PhenoCycler. Reads each slide's .xpd JSON acquisition metadata into one row per (well, marker); well order of first appearance becomes round_number."""
import argparse
import json
import os
import sys

import pandas as pd

CHANNEL_NUMBER_MAP = {"DAPI": 0, "ATTO550": 1, "AF750": 2, "CY5": 3}

def exp_design_akoya(input_path, exp_design_rounds, exp_design_slides):
    print(f"### input path raw data: {input_path} ###")
    print(f"### output path experimental design rounds (csv): {exp_design_rounds} ###")
    print(f"### output path experimental design slides (csv): {exp_design_slides} ###")

    os.makedirs(os.path.dirname(exp_design_rounds), exist_ok=True)
    os.makedirs(os.path.dirname(exp_design_slides), exist_ok=True)

    folders = sorted(f.name for f in os.scandir(input_path) if f.is_dir())

    all_rows = []
    for folder in folders:
        xpd_files = [f for f in os.listdir(os.path.join(input_path, folder)) if f.endswith(".xpd")]
        if len(xpd_files) != 1:
            raise ValueError(f"metadata file not found (expected exactly 1 .xpd in {folder}, found {len(xpd_files)})")

        with open(os.path.join(input_path, folder, xpd_files[0])) as f:
            data = json.load(f)
        resolution = data["resolution"]

        well_order = []
        for well in data["wells"]:
            well_name = well["wellName"]
            if well_name not in well_order:
                well_order.append(well_name)
            for k, item in enumerate(well["items"]):
                all_rows.append({
                    "well_name": well_name,
                    "marker_name": item["markerName"],
                    "marker_id": item["markerName"],  # duplication to make AFS work, per original comment
                    "channel_id": item["channel"],
                    "channel_number": k,
                    "folder": folder,
                    "pixel_size": resolution,
                    "_well_order_idx": well_order.index(well_name),
                })

    df = pd.DataFrame(all_rows)
    # round_number: well's first-appearance order WITHIN its own slide folder, 1-based
    df["round_number"] = "R" + (df["_well_order_idx"] + 1).astype(str).str.zfill(2)
    df = df.drop(columns=["_well_order_idx"])
    df["marker_name"] = df["marker_name"].replace("--", "AF")
    df["QC_include"] = 1

    # channel names outside CHANNEL_NUMBER_MAP keep their original positional index rather than raising
    mapped = df["channel_id"].map(CHANNEL_NUMBER_MAP)
    df["channel_number"] = mapped.where(mapped.notna(), df["channel_number"]).astype(int)

    df.to_csv(exp_design_rounds, index=False)

    df_slides = df[["folder"]].drop_duplicates()
    df_slides.to_csv(exp_design_slides, index=False)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate the experimental design for AKOYA - PhenoCycler.")
    parser.add_argument("--input_path", type=str, help="Path to input directory with the raw data (path).")
    parser.add_argument("--exp_design_rounds", type=str, help="Path to output file for the rounds experimental design (csv).")
    parser.add_argument("--exp_design_slides", type=str, help="Path to output file for the slides experimental design (csv).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    exp_design_akoya(
        input_path=args.input_path,
        exp_design_rounds=args.exp_design_rounds,
        exp_design_slides=args.exp_design_slides,
    )
