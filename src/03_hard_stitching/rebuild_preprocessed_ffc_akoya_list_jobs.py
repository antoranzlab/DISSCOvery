#!/usr/bin/env python
"""Coarse stitching from individual tiles (AKOYA) - list jobs. One job per input folder (round/version); computes conversion_factor from the folder's own metadata CSV."""
import argparse
import os
import sys

import pandas as pd

# input_path_meta must point at raw extraction output (output_tiles), not FFC output -- FFC folders don't carry their own metadata CSV
def hard_stitching_job_list(input_path_tiles, input_path_meta, output_folder, output_path_csv, output_pixel_size):
    print(f"### input path tiles: {input_path_tiles} ###")
    print(f"### input path metadata: {input_path_meta} ###")
    print(f"### output directory: {output_folder} ###")
    print(f"### output path csv job list: {output_path_csv} ###")
    print(f"### output pixel size: {output_pixel_size} ###")

    output_pixel_size = float(output_pixel_size)

    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(os.path.dirname(output_path_csv), exist_ok=True)

    folders = sorted(f.name for f in os.scandir(input_path_tiles) if f.is_dir())

    job_rows = []
    for folder in folders:
        print(folder)
        os.makedirs(os.path.join(output_folder, folder), exist_ok=True)

        meta_dir = os.path.join(input_path_meta, folder)
        csv_files = [f for f in os.listdir(meta_dir) if f.endswith(".csv")]
        if len(csv_files) != 1:
            raise ValueError(f"error fetching the metadata for {folder} (expected exactly 1 csv, found {len(csv_files)})")
        meta_path = os.path.join(meta_dir, csv_files[0])

        tmp_csv = pd.read_csv(meta_path)
        # first row per (S, M) group, not R's random sample_n(1) -- ImagePixelSize is constant within a group, so this is deterministic without changing the result
        tmp_csv = tmp_csv.groupby(["S", "M"], as_index=False).first()
        px_size = tmp_csv["ImagePixelSize"].iloc[0].split(",")
        px_size_x = float(px_size[0]) / 10

        conversion_factor = output_pixel_size / px_size_x

        job_rows.append({
            "input_path_tiles": os.path.join(input_path_tiles, folder),
            "input_path_meta": meta_path,
            "output_folder": os.path.join(output_folder, folder),
            "conversion_factor": conversion_factor,
        })

    pd.DataFrame(job_rows).to_csv(output_path_csv, index=False)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coarse stitching from individual tiles (AKOYA) - list jobs.")
    parser.add_argument("--input_path_tiles", type=str, help="Path to input tiles (path).")
    parser.add_argument("--input_path_meta", type=str, help="Path to input metadata files (path).")
    parser.add_argument("--output_folder", type=str, help="Path to output path to save images (path).")
    parser.add_argument("--output_path_csv", type=str, help="Path to output csv where the job list will be saved (.csv).")
    parser.add_argument("--output_pixel_size", type=str, help="Output pixel size (numeric).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    hard_stitching_job_list(
        input_path_tiles=args.input_path_tiles,
        input_path_meta=args.input_path_meta,
        output_folder=args.output_folder,
        output_path_csv=args.output_path_csv,
        output_pixel_size=args.output_pixel_size,
    )
