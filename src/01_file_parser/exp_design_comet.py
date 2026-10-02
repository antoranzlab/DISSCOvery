#!/usr/bin/env python
"""Generate the experimental design for COMET (Lunaphore). Flattens each slide's .xml jobfile CycleModels/ChannelMeta nodes into one row per (folder, cycle, channel), then infers each real-marker round's nearest AF-reference round on the same channel -- see `_infer_af_reference`."""
import argparse
import os
import sys
import xml.etree.ElementTree as ET

import pandas as pd

def _extract_cycle_rows(cycle_node, cycle_number):
    rows = []
    for channel_meta in cycle_node.findall(".//ChannelMeta"):
        channel = channel_meta.find(".//Channel")
        plane = channel_meta.find(".//Plane")
        channel_priv = channel_meta.find(".//ChannelPriv")
        rows.append({
            "cycle_number": cycle_number,
            "channel_name": channel.get("Name") if channel is not None else None,
            "samples_per_pixel": channel.get("SamplesPerPixel") if channel is not None else None,
            "color": channel.get("Color") if channel is not None else None,
            "exposure_time": plane.get("ExposureTime") if plane is not None else None,
            "exposure_time_unit": plane.get("ExposureTimeUnit") if plane is not None else None,
            "TheC": plane.get("TheC") if plane is not None else None,
            "TheT": plane.get("TheT") if plane is not None else None,
            "TheZ": plane.get("TheZ") if plane is not None else None,
            "FluorescenceChannel": channel_priv.get("FluorescenceChannel") if channel_priv is not None else None,
            "LedCurrentUnit": channel_priv.get("LedCurrentUnit") if channel_priv is not None else None,
        })
    return rows

def _cycle_number_from_path(tile_folder_path):
    # ".../Cycle_003/" or "...\Cycle_003\" -> 3 (R: strip trailing backslash, then
    # strip everything up to and including the last "Cycle_").
    cleaned = tile_folder_path.rstrip("\\").rstrip("/")
    cycle_str = cleaned.rsplit("Cycle_", 1)[-1]
    return int(cycle_str)

def _infer_af_reference(df):
    """Nearest AF-only round per (folder, round_number), ties broken toward the larger round_number."""
    af_rounds = df[(df["channel_id"] != "DAPI") & (df["marker_name"] == df["channel_id"])][
        ["folder", "round_number"]
    ].drop_duplicates()
    marker_rounds = df[df["marker_name"] != df["channel_id"]][["folder", "round_number"]].drop_duplicates()

    ref_map = {}
    for _, row in marker_rounds.iterrows():
        candidates = af_rounds[af_rounds["folder"] == row["folder"]].copy()
        if candidates.empty:
            continue
        candidates["delta"] = (candidates["round_number"] - row["round_number"]).abs()
        min_delta = candidates["delta"].min()
        candidates = candidates[candidates["delta"] == min_delta]
        ref_map[(row["folder"], row["round_number"])] = int(candidates["round_number"].max())
    return ref_map

def exp_design_comet(input_path, exp_design_rounds, exp_design_slides):
    print(f"### input path raw data: {input_path} ###")
    print(f"### output path experimental design rounds (csv): {exp_design_rounds} ###")
    print(f"### output path experimental design slides (csv): {exp_design_slides} ###")

    os.makedirs(os.path.dirname(exp_design_rounds), exist_ok=True)
    os.makedirs(os.path.dirname(exp_design_slides), exist_ok=True)

    folders = sorted(f.name for f in os.scandir(input_path) if f.is_dir())

    all_rows = []
    for folder in folders:
        xml_files = [f for f in os.listdir(os.path.join(input_path, folder)) if f.endswith(".xml")]
        if len(xml_files) != 1:
            raise ValueError(f"expected exactly 1 .xml jobfile in {folder}, found {len(xml_files)}")

        root = ET.parse(os.path.join(input_path, folder, xml_files[0])).getroot()
        for cycle_node in root.findall(".//CycleModels"):
            cycle_number = _cycle_number_from_path(cycle_node.get("TileFolderPath"))
            for row in _extract_cycle_rows(cycle_node, cycle_number):
                row["folder"] = folder
                all_rows.append(row)

    df_metadata = pd.DataFrame(all_rows)

    df = (
        df_metadata[["folder", "cycle_number", "FluorescenceChannel", "channel_name"]]
        .drop_duplicates()
        .rename(columns={"cycle_number": "round_number", "FluorescenceChannel": "channel_id", "channel_name": "marker_name"})
    )

    ref_map = _infer_af_reference(df)
    df["ref_round_af"] = df.apply(
        lambda r: ref_map.get((r["folder"], r["round_number"]), r["round_number"]), axis=1
    )

    df["round_number"] = "R" + df["round_number"].astype(int).astype(str).str.zfill(2)
    df["ref_round_af"] = "R" + df["ref_round_af"].astype(int).astype(str).str.zfill(2)
    df["QC_include"] = 1
    # AF-sentinel encoding, added here (not a literal R port): the R script leaves marker_id
    # as the raw channel name for AF-only rounds, but AFS_list_jobs.py/FeatureExtraction.py key
    # off marker_id=="AF" -- matches exp_design_akoya.py's equivalent handling and the real
    # COMET reference file's own convention.
    is_af_round = (df["channel_id"] != "DAPI") & (df["marker_name"] == df["channel_id"])
    df["marker_id"] = df["marker_name"].where(~is_af_round, "AF")

    df.to_csv(exp_design_rounds, index=False)

    df_slides = df[["folder"]].drop_duplicates()
    df_slides.to_csv(exp_design_slides, index=False)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate the experimental design for COMET.")
    parser.add_argument("--input_path", type=str, help="Path to input directory with the raw data (path).")
    parser.add_argument("--exp_design_rounds", type=str, help="Path to output file for the rounds experimental design (csv).")
    parser.add_argument("--exp_design_slides", type=str, help="Path to output file for the slides experimental design (csv).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    exp_design_comet(
        input_path=args.input_path,
        exp_design_rounds=args.exp_design_rounds,
        exp_design_slides=args.exp_design_slides,
    )
