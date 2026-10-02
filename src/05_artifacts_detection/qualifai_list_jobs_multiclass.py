import argparse
import os
import sys

import pandas as pd

def qualifai_job_list(input_folder_path, output_folder_path, model_path, output_path_csv):
    """List hard-stitched full-resolution images and build the QUAL-IF-AI joblist."""
    print(f"### input path images: {input_folder_path} ###")
    print(f"### output path images: {output_folder_path} ###")
    print(f"### model path: {model_path} ###")
    print(f"### output path csv job list: {output_path_csv} ###")

    os.makedirs(output_folder_path, exist_ok=True)
    os.makedirs(os.path.dirname(output_path_csv), exist_ok=True)

    folders = sorted(f.name for f in os.scandir(input_folder_path) if f.is_dir())

    job_list = []
    for folder in folders:
        for ofile in os.listdir(os.path.join(input_folder_path, folder)):
            if ".tif" not in ofile:
                continue
            job_list.append(
                {
                    "input_image": os.path.join(input_folder_path, folder, ofile),
                    "output_image": os.path.join(output_folder_path, folder, ofile),
                    "model_path": model_path,
                }
            )

    pd.DataFrame(job_list).to_csv(output_path_csv, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coarse registration from hard stitched images - list jobs.")
    parser.add_argument("--input_folder_path", type=str, help="Path to input images (path).")
    parser.add_argument("--output_folder_path", type=str, help="Path to output path to save images (path).")
    parser.add_argument("--model_path", type=str, help="Path to input model (.h5).")
    parser.add_argument("--output_path_csv", type=str, help="Path to output csv where the job list will be saved (.csv).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    qualifai_job_list(
        input_folder_path=args.input_folder_path,
        output_folder_path=args.output_folder_path,
        model_path=args.model_path,
        output_path_csv=args.output_path_csv,
    )
