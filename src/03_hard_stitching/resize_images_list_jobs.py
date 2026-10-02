#!/usr/bin/env python
"""Resize images (COMET/AKOYA) - list jobs. AKOYA runs this once (QUALIFAI); COMET runs it twice (STS and QUALIFAI, different pixel sizes)."""
import argparse
import os
import sys

import pandas as pd

def resize_images_job_list(input_path_images, output_folder, input_pixel_size, output_pixel_size, output_path_csv):
    print(f"### input path images: {input_path_images} ###")
    print(f"### output directory: {output_folder} ###")
    print(f"### input pixel size: {input_pixel_size} ###")
    print(f"### output pixel size: {output_pixel_size} ###")
    print(f"### output path csv job list: {output_path_csv} ###")

    input_pixel_size = float(input_pixel_size)
    output_pixel_size = float(output_pixel_size)
    conversion_factor = output_pixel_size / input_pixel_size

    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(os.path.dirname(output_path_csv), exist_ok=True)

    folders = sorted(f.name for f in os.scandir(input_path_images) if f.is_dir())
    rows = []
    for folder in folders:
        for ofile in sorted(os.listdir(os.path.join(input_path_images, folder))):
            if not (ofile.endswith(".tif") or ofile.endswith(".tiff")):
                continue
            rows.append({"ofile": ofile, "folder": folder})
    df_files = pd.DataFrame(rows)
    stem = df_files["ofile"].str.replace(r"\.tif+$", "", regex=True)
    stem = stem.str.replace("AF_FITC", "AFFITC", regex=False)
    fields = stem.str.split("_", expand=True)
    fields.columns = ["slide_id", "round_id", "version_id", "project_id", "user_id", "channel_id"]
    df_files = pd.concat([df_files, fields], axis=1)

    job_rows = []
    for _, row in df_files.iterrows():
        job_rows.append({
            "input_path_image": os.path.join(input_path_images, row["folder"], row["ofile"]),
            "output_path_image": os.path.join(output_folder, row["slide_id"], row["ofile"]),
            "conversion_factor": conversion_factor,
        })

    pd.DataFrame(job_rows).to_csv(output_path_csv, index=False)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resize images - list jobs.")
    parser.add_argument("--input_path_images", type=str, help="Path to input tiles (path).")
    parser.add_argument("--output_folder", type=str, help="Path to output path to save images (path).")
    parser.add_argument("--input_pixel_size", type=str, help="Pixel size of the input images (numeric).")
    parser.add_argument("--output_pixel_size", type=str, help="Desired pixel size for the output images (numeric).")
    parser.add_argument("--output_path_csv", type=str, help="Path to output csv where the job list will be saved (.csv).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    resize_images_job_list(
        input_path_images=args.input_path_images,
        output_folder=args.output_folder,
        input_pixel_size=args.input_pixel_size,
        output_pixel_size=args.output_pixel_size,
        output_path_csv=args.output_path_csv,
    )
