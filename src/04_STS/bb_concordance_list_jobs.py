import argparse
import os
import sys

import pandas as pd

def bb_concordance_job_list(input_path_BB, output_path_html, output_path_json, ref_round, ref_version, path_output_csv):
    """List per-slide bounding-box folders and build the concordance-evaluation joblist."""
    print(f"### input path bounding boxes: {input_path_BB} ###")
    print(f"### output path heatmap in html format: {output_path_html} ###")
    print(f"### output path heatmap in json format: {output_path_json} ###")
    print(f"### reference round: {ref_round} ###")
    print(f"### reference version: {ref_version} ###")
    print(f"### output path csv job list: {path_output_csv} ###")

    os.makedirs(output_path_html, exist_ok=True)
    os.makedirs(output_path_json, exist_ok=True)
    os.makedirs(os.path.dirname(path_output_csv), exist_ok=True)

    folders = sorted(f.name for f in os.scandir(input_path_BB) if f.is_dir())

    job_list = pd.DataFrame(
        {
            "input_folder": [os.path.join(input_path_BB, folder) for folder in folders],
            "output_folder_html": [os.path.join(output_path_html, folder, "interactive_heatmap.html") for folder in folders],
            "output_folder_json": [os.path.join(output_path_json, folder, "interactive_heatmap.json") for folder in folders],
            "ref_round": ref_round,
            "ref_version": ref_version,
        }
    )

    job_list.to_csv(path_output_csv, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coarse registration from hard stitched images - list jobs.")
    parser.add_argument("--input_path_BB", type=str, help="Path to input bounding boxes (path).")
    parser.add_argument("--output_path_html", type=str, help="Path to output path to save the masks (path).")
    parser.add_argument("--output_path_json", type=str, help="Path to input path with the model (.h5).")
    parser.add_argument("--ref_round", type=str, help="Path to output csv where the job list will be saved (.csv).")
    parser.add_argument("--ref_version", type=str, help="Path to output csv where the job list will be saved (.csv).")
    parser.add_argument("--path_output_csv", type=str, help="Path to output csv where the job list will be saved (.csv).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    bb_concordance_job_list(
        input_path_BB=args.input_path_BB,
        output_path_html=args.output_path_html,
        output_path_json=args.output_path_json,
        ref_round=args.ref_round,
        ref_version=args.ref_version,
        path_output_csv=args.path_output_csv,
    )
