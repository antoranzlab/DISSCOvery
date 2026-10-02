#!/usr/bin/env python
"""Generate csv for data extraction - COMET. One row per top-level slide folder under input_folder."""
import argparse
import os
import sys

import pandas as pd

def generate_csv_image_extraction(input_folder, output_folder, input_slide_dictionary,
                                   exp_design_rounds_file, user_id, project_id, output_csv):
    print(f"### input folder: {input_folder} ###")
    print(f"### output folder: {output_folder} ###")
    print(f"### input channel dictionary: {input_slide_dictionary} ###")
    print(f"### experimental design rounds: {exp_design_rounds_file} ###")
    print(f"### user identifier: {user_id} ###")
    print(f"### project identifier: {project_id} ###")
    print(f"### output csv: {output_csv} ###")

    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)

    folders = sorted(f.path for f in os.scandir(input_folder) if f.is_dir())
    df = pd.DataFrame({"input_path": folders})
    df["output_folder"] = output_folder
    df["project_id"] = project_id
    df["user_id"] = user_id
    df["input_slide_dictionary"] = input_slide_dictionary
    df["exp_design_rounds_file"] = exp_design_rounds_file

    df.to_csv(output_csv, index=False)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate csv for data extraction - COMET.")
    parser.add_argument("--path.input.folder", dest="path_input_folder", type=str, help="Path to the main project folder (directory).")
    parser.add_argument("--path.output.folder", dest="path_output_folder", type=str, help="Path to output folder where to save (directory).")
    parser.add_argument("--path.input.slide.dictionary", dest="path_input_slide_dictionary", type=str, help="Path to input csv with slide dictionary (csv).")
    parser.add_argument("--path.exp.design.rounds.file", dest="path_exp_design_rounds_file", type=str, help="Path to input csv with the experimental design for the rounds (csv).")
    parser.add_argument("--user.id", dest="user_id", type=str, help="Identifier for the user.")
    parser.add_argument("--project.id", dest="project_id", type=str, help="Identifier for the project.")
    parser.add_argument("--path.output.csv", dest="path_output_csv", type=str, help="Path to the output csv where to save the list of jobs (csv).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    generate_csv_image_extraction(
        input_folder=args.path_input_folder,
        output_folder=args.path_output_folder,
        input_slide_dictionary=args.path_input_slide_dictionary,
        exp_design_rounds_file=args.path_exp_design_rounds_file,
        user_id=args.user_id,
        project_id=args.project_id,
        output_csv=args.path_output_csv,
    )
