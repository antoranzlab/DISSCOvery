import argparse
import os
import sys

import pandas as pd

from czi_metadata import find_czi_files

def generate_csv_czi_extraction(input_folder, input_channel_dictionary, output_folder, output_csv):
    """List raw CZI files and build the per-file extraction joblist."""
    print(f"### input folder: {input_folder} ###")
    print(f"### input channel dictionary: {input_channel_dictionary} ###")
    print(f"### output folder: {output_folder} ###")
    print(f"### output csv: {output_csv} ###")

    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)

    print("Listing files")
    czi_files = find_czi_files(input_folder)
    df = pd.DataFrame({"input_path": czi_files})
    czi_id = df["input_path"].apply(lambda x: os.path.basename(x).replace(".czi", ""))
    df["output_folder"] = czi_id.apply(lambda x: os.path.join(output_folder, x))
    df["input_channel_dictionary"] = input_channel_dictionary

    print("Creating csv file")
    folder = df["output_folder"].apply(os.path.basename)
    df[["slide_id", "round_id", "version_id", "project_id", "user_id"]] = folder.str.split("_", expand=True)
    df.to_csv(output_csv, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate csv for czi extraction.")
    parser.add_argument("--path.input.folder", dest="path_input_folder", type=str,
                         help="Path to input folder with raw czi files (directory).")
    parser.add_argument("--path.input.channel.dictionary", dest="path_input_channel_dictionary", type=str,
                         help="Path to input csv with channel names (csv).")
    parser.add_argument("--path.output.folder", dest="path_output_folder", type=str,
                         help="Path to output folder where raw tiles will be stored (directory).")
    parser.add_argument("--path.output.csv", dest="path_output_csv", type=str,
                         help="Path to output csv with the extraction joblist (csv).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    generate_csv_czi_extraction(
        input_folder=args.path_input_folder,
        input_channel_dictionary=args.path_input_channel_dictionary,
        output_folder=args.path_output_folder,
        output_csv=args.path_output_csv,
    )
