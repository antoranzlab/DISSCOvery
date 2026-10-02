import argparse
import os
import sys

import pandas as pd

def mask_generation_job_list(input_path_images, output_path_images, path_model, output_path_csv, ref_channel):
    """List registered images for the reference channel and build the mask-generation joblist."""
    print(f"### input path images: {input_path_images} ###")
    print(f"### output path images: {output_path_images} ###")
    print(f"### input path model: {path_model} ###")
    print(f"### output path csv job list: {output_path_csv} ###")
    print(f"### reference channel: {ref_channel} ###")

    os.makedirs(output_path_images, exist_ok=True)
    os.makedirs(os.path.dirname(output_path_csv), exist_ok=True)

    folders = sorted(f.name for f in os.scandir(input_path_images) if f.is_dir())

    job_list = []
    for folder in folders:
        for ofile in os.listdir(os.path.join(input_path_images, folder)):
            if ".tif" not in ofile:
                continue
            channel_id = ofile.replace(".tiff", "").split("_")[-1]
            if channel_id != ref_channel:
                continue
            job_list.append(
                {
                    "input_image": os.path.join(input_path_images, folder, ofile),
                    "output_image": os.path.join(output_path_images, folder, ofile),
                    "model": path_model,
                }
            )

    pd.DataFrame(job_list).to_csv(output_path_csv, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coarse registration from hard stitched images - list jobs.")
    parser.add_argument("--input_path_images", type=str, help="Path to input images (path).")
    parser.add_argument("--output_path_images", type=str, help="Path to output path to save the masks (path).")
    parser.add_argument("--path_model", type=str, help="Path to input path with the model (.h5).")
    parser.add_argument("--output_path_csv", type=str, help="Path to output csv where the job list will be saved (.csv).")
    parser.add_argument("--ref_channel", type=str, help="Reference channel where to perform the STS (string).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    mask_generation_job_list(
        input_path_images=args.input_path_images,
        output_path_images=args.output_path_images,
        path_model=args.path_model,
        output_path_csv=args.output_path_csv,
        ref_channel=args.ref_channel,
    )
