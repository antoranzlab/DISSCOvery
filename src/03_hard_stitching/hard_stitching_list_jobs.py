import argparse
import os
import sys

import pandas as pd

def hard_stitching_job_list(
    input_path_tiles,
    input_path_meta,
    output_folder,
    output_path_csv,
    output_pixel_size,
    only_dapi,
    skip_existing,
):
    """List tile folders and build the coarse-stitching joblist, one row per folder."""
    print(f"### input path tiles: {input_path_tiles} ###")
    print(f"### input path metadata: {input_path_meta} ###")
    print(f"### output directory: {output_folder} ###")
    print(f"### output path csv job list: {output_path_csv} ###")
    print(f"### output pixel size: {output_pixel_size} ###")
    print(f"### only dapi: {only_dapi} ###")

    output_pixel_size = float(output_pixel_size)

    os.makedirs(output_folder, exist_ok=True)

    folders = sorted(f.name for f in os.scandir(input_path_tiles) if f.is_dir())

    job_list = []
    for folder in folders:
        print(folder)
        slide_id = folder.split("_")[0]

        os.makedirs(os.path.join(output_folder, slide_id), exist_ok=True)

        meta_files = [f for f in os.listdir(os.path.join(input_path_meta, folder)) if f.endswith(".csv")]
        if len(meta_files) != 1:
            raise RuntimeError("error fetching the metadata")
        meta_file = meta_files[0]

        # pixel size is constant across all tiles in a folder, so one row is enough
        meta = pd.read_csv(os.path.join(input_path_meta, folder, meta_file), nrows=1)
        px_size_x = float(meta["ImagePixelSize"].iloc[0].split(",")[0]) / 10
        conversion_factor = output_pixel_size / px_size_x

        job_list.append(
            {
                "input_path_tiles": os.path.join(input_path_tiles, folder),
                "input_path_meta": os.path.join(input_path_meta, folder, meta_file),
                "output_folder": os.path.join(output_folder, slide_id),
                "conversion_factor": conversion_factor,
                "only_dapi": only_dapi,
                "skip_existing": skip_existing,
            }
        )

    pd.DataFrame(job_list).to_csv(output_path_csv, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coarse stitching from individual tiles - list jobs.")
    parser.add_argument("--input_path_tiles", type=str, help="Path to input tiles (path).")
    parser.add_argument("--input_path_meta", type=str, help="Path to input metadata files (path).")
    parser.add_argument("--output_folder", type=str, help="Path to output path to save images (path).")
    parser.add_argument("--output_path_csv", type=str, help="Path to output csv where the job list will be saved (.csv).")
    parser.add_argument("--output_pixel_size", type=str, help="Pixel size for output images.")
    parser.add_argument("--only_dapi", type=str, help="Boolean indicating if to do HS only on DAPI.")
    parser.add_argument("--skip_existing", type=str, help="Boolean to skip already existing results (boolean).")

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
        only_dapi=args.only_dapi,
        skip_existing=args.skip_existing,
    )
