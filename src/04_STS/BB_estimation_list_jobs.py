import argparse
import os
import sys

import pandas as pd

def bb_estimation_job_list(input_path_images, output_path_bbs, filter_small, output_path_csv):
    """List mask images and build the bounding-box estimation joblist."""
    print(f"### input path images: {input_path_images} ###")
    print(f"### output path bounding boxes: {output_path_bbs} ###")
    print(f"### filter small objects: {filter_small} ###")
    print(f"### output path csv job list: {output_path_csv} ###")

    os.makedirs(output_path_bbs, exist_ok=True)
    os.makedirs(os.path.dirname(output_path_csv), exist_ok=True)

    folders = sorted(f.name for f in os.scandir(input_path_images) if f.is_dir())

    job_list = []
    for folder in folders:
        for ofile in os.listdir(os.path.join(input_path_images, folder)):
            if ".tif" not in ofile:
                continue
            job_list.append(
                {
                    "input_image": os.path.join(input_path_images, folder, ofile),
                    "output_bb": os.path.join(output_path_bbs, folder, ofile.replace(".tiff", ".csv")),
                    "filter_small": filter_small,
                }
            )

    pd.DataFrame(job_list).to_csv(output_path_csv, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generation of bounding boxes - list jobs.")
    parser.add_argument("--input_path_images", type=str, help="Path to input images (path).")
    parser.add_argument("--output_path_bbs", type=str, help="Path to output path to save the csv (path).")
    parser.add_argument("--filter_small", type=str, help="Boolean to filter small objects or not (boolean).")
    parser.add_argument("--output_path_csv", type=str, help="Path to output csv where the job list will be saved (.csv).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    bb_estimation_job_list(
        input_path_images=args.input_path_images,
        output_path_bbs=args.output_path_bbs,
        filter_small=args.filter_small,
        output_path_csv=args.output_path_csv,
    )
