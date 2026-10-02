#!/usr/bin/env python
"""List split_scenes jobs: one row per (round/version folder, channel)."""
import argparse
import os
import sys

import pandas as pd

def split_scenes_job_list(input_path_tiles, input_path_meta, input_path_masks_foreground, input_path_bb,
                           input_path_masks_qc, output_path_error_log, px_size_sts, px_size_qc,
                           output_path_folder, output_path_csv, skip_existing):
    print(f"### input path tiles: {input_path_tiles} ###")
    print(f"### input path metadata: {input_path_meta} ###")
    print(f"### input path foreground masks: {input_path_masks_foreground} ###")
    print(f"### input path bounding boxes: {input_path_bb} ###")
    print(f"### input path QC masks: {input_path_masks_qc} ###")
    print(f"### output path error logs: {output_path_error_log} ###")
    print(f"### pixel size STS: {px_size_sts} ###")
    print(f"### pixel size QC: {px_size_qc} ###")
    print(f"### output path folder: {output_path_folder} ###")
    print(f"### output path csv job list: {output_path_csv} ###")
    print(f"### skip_existing: {skip_existing} ###")

    os.makedirs(output_path_folder, exist_ok=True)
    os.makedirs(os.path.dirname(output_path_csv), exist_ok=True)
    os.makedirs(os.path.dirname(output_path_error_log), exist_ok=True)

    px_size_sts = float(px_size_sts)
    px_size_qc = float(px_size_qc)

    folders = sorted(f.name for f in os.scandir(input_path_tiles) if f.is_dir())
    job_rows = []

    for folder in folders:
        meta_file = next(f for f in os.listdir(os.path.join(input_path_meta, folder)) if f.endswith(".csv"))
        meta = pd.read_csv(os.path.join(input_path_meta, folder, meta_file))

        px_size_x = float(meta["ImagePixelSize"].iloc[0].split(",")[0]) / 10
        conversion_factor_sts = px_size_sts / px_size_x
        conversion_factor_qc = px_size_qc / px_size_x

        slide_id, round_id, version_id = folder.split("_")[:3]

        bb_dir = os.path.join(input_path_bb, slide_id)
        bb_files = [f for f in os.listdir(bb_dir) if f.endswith(".csv") and f"_{round_id}_" in f and f"_{version_id}_" in f]
        if len(bb_files) != 1:
            raise ValueError(f"number of BB files identified different from 1 for {folder}: {bb_files}")

        fg_dir = os.path.join(input_path_masks_foreground, slide_id)
        fg_files = [f for f in os.listdir(fg_dir) if f.endswith((".tiff", ".tif")) and f"_{round_id}_" in f and f"_{version_id}_" in f]
        if len(fg_files) != 1:
            raise ValueError(f"number of foreground mask files identified different from 1 for {folder}: {fg_files}")

        prefix = folder  # slide_round_version_project_user, matches the folder name itself
        # channel names read directly off every tile_filename (deterministic), not R's fragile one-random-sample-per-(S,M) approach
        channels = sorted(meta["tile_filename"].str.replace(".tiff", "", regex=False).str.split("_").str[-1].unique())
        n_channels = meta["C"].nunique()
        if len(channels) != n_channels:
            raise ValueError(f"number of distinct channels ({len(channels)}) != number of channel indices "
                              f"in metadata ({n_channels}) for {folder}")

        for channel_id in channels:
            qc_file = f"{prefix}_{channel_id}.tiff"
            job_rows.append({
                "input_path_tiles": os.path.join(input_path_tiles, folder),
                "input_path_meta": os.path.join(input_path_meta, folder, meta_file),
                "input_path_masks_foreground": os.path.join(input_path_masks_foreground, slide_id, fg_files[0]),
                "input_path_bb": os.path.join(input_path_bb, slide_id, bb_files[0]),
                "input_path_masks_qc": os.path.join(input_path_masks_qc, slide_id, qc_file),
                "error_log_file": os.path.join(output_path_error_log, qc_file.replace(".tiff", ".txt")),
                "channel_id": channel_id,
                "conversion_factor_qc": conversion_factor_qc,
                "conversion_factor_sts": conversion_factor_sts,
                "output_path_folder": output_path_folder,
                "skip_existing": skip_existing,
            })

    pd.DataFrame(job_rows).to_csv(output_path_csv, index=False)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Split Scenes - list jobs.")
    parser.add_argument("--input_path_tiles", type=str, help="Path to input tiles (path).")
    parser.add_argument("--input_path_meta", type=str, help="Path to input metadata (path).")
    parser.add_argument("--input_path_masks_foreground", type=str, help="Path to input foreground masks (path).")
    parser.add_argument("--input_path_bb", type=str, help="Path to input bounding boxes (path).")
    parser.add_argument("--input_path_masks_qc", type=str, help="Path to input QC masks (path).")
    parser.add_argument("--output_path_error_log", type=str, help="Path to output error logs (path).")
    parser.add_argument("--px_size_sts", type=str, help="Pixel size used for STS (numeric).")
    parser.add_argument("--px_size_qc", type=str, help="Pixel size used for QC (numeric).")
    parser.add_argument("--output_path_folder", type=str, help="Path to output directory (path).")
    parser.add_argument("--output_path_csv", type=str, help="Path to output csv where the job list will be saved (.csv).")
    parser.add_argument("--skip_existing", type=str, help="Skip existing results (boolean).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    split_scenes_job_list(
        input_path_tiles=args.input_path_tiles,
        input_path_meta=args.input_path_meta,
        input_path_masks_foreground=args.input_path_masks_foreground,
        input_path_bb=args.input_path_bb,
        input_path_masks_qc=args.input_path_masks_qc,
        output_path_error_log=args.output_path_error_log,
        px_size_sts=args.px_size_sts,
        px_size_qc=args.px_size_qc,
        output_path_folder=args.output_path_folder,
        output_path_csv=args.output_path_csv,
        skip_existing=args.skip_existing,
    )
