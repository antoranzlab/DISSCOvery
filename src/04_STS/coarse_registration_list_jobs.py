import argparse
import os
import sys

import pandas as pd

def coarse_registration_job_list(
    input_path_images,
    output_path_images,
    output_path_tm,
    ref_channel,
    ref_round,
    ref_version,
    output_path_csv,
):
    """List hard-stitched images per slide and pair each with its reference round/version."""
    print(f"### input path images: {input_path_images} ###")
    print(f"### output path images: {output_path_images} ###")
    print(f"### output path transformation matrices: {output_path_tm} ###")
    print(f"### reference channel: {ref_channel} ###")
    print(f"### reference round: {ref_round} ###")
    print(f"### reference version: {ref_version} ###")
    print(f"### output path csv job list: {output_path_csv} ###")

    os.makedirs(output_path_images, exist_ok=True)
    os.makedirs(output_path_tm, exist_ok=True)
    os.makedirs(os.path.dirname(output_path_csv), exist_ok=True)

    folders = sorted(f.name for f in os.scandir(input_path_images) if f.is_dir())

    rows = []
    for folder in folders:
        for ofile in os.listdir(os.path.join(input_path_images, folder)):
            if ".tif" not in ofile:
                continue
            slide_id, round_id, version_id, project_id, user_id, channel_id = (
                ofile.replace(".tiff", "").split("_")
            )
            if channel_id != ref_channel:
                continue
            rows.append(
                {"ofile": ofile, "folder": folder, "slide_id": slide_id, "round_id": round_id, "version_id": version_id}
            )
    df_files = pd.DataFrame(rows)

    ref_files = df_files[(df_files["round_id"] == ref_round) & (df_files["version_id"] == ref_version)]

    job_list = []
    for slide_id in ref_files["slide_id"].unique():
        tmp_ref_file = ref_files[ref_files["slide_id"] == slide_id]
        if len(tmp_ref_file) > 1:
            raise ValueError(f"unique reference not found for slide {slide_id}")
        ref_row = tmp_ref_file.iloc[0]
        fixed_image = os.path.join(input_path_images, ref_row["folder"], ref_row["ofile"])

        tmp_query_files = df_files[df_files["slide_id"] == slide_id]
        for _, query_row in tmp_query_files.iterrows():
            job_list.append(
                {
                    "fixed_image": fixed_image,
                    "query_image": os.path.join(input_path_images, query_row["folder"], query_row["ofile"]),
                    "output_image": os.path.join(output_path_images, query_row["folder"], query_row["ofile"]),
                    "output_tm": os.path.join(
                        output_path_tm, query_row["folder"], query_row["ofile"].replace(".tiff", ".npy")
                    ),
                }
            )

    pd.DataFrame(job_list).to_csv(output_path_csv, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coarse registration from hard stitched images - list jobs.")
    parser.add_argument("--input_path_images", type=str, help="Path to input images (path).")
    parser.add_argument("--output_path_images", type=str, help="Path to output path to save images (path).")
    parser.add_argument("--output_path_tm", type=str, help="Path to output path to save transformation matrices (path).")
    parser.add_argument("--ref_channel", type=str, help="Reference channel (string).")
    parser.add_argument("--ref_round", type=str, help="Reference round (string).")
    parser.add_argument("--ref_version", type=str, help="Reference version (string).")
    parser.add_argument("--output_path_csv", type=str, help="Path to output csv where the job list will be saved (.csv).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    coarse_registration_job_list(
        input_path_images=args.input_path_images,
        output_path_images=args.output_path_images,
        output_path_tm=args.output_path_tm,
        ref_channel=args.ref_channel,
        ref_round=args.ref_round,
        ref_version=args.ref_version,
        output_path_csv=args.output_path_csv,
    )
