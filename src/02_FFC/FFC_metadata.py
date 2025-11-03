import sys
import os
import argparse
import pandas as pd
import shutil

def copy_meta(input_meta, output_meta):
    """Copy the metadata files from input to output directory"""
    print(f"### input path metadata: {input_meta} ###")
    print(f"### output path metadata: {output_meta} ###")
    
    # Check if the output directories exist and create them if they do not
    if not os.path.isdir(os.path.dirname(output_meta)):
        print(f"### creating folder: {os.path.dirname(output_meta)} ###")
        os.makedirs(os.path.dirname(output_meta))
    
    shutil.copy2(input_meta, output_meta)  # Copy with metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Flat Field Correction - Copy metadata')
    parser.add_argument("--path_input_metadata", help="path to input metadata.", type=str)
    parser.add_argument("--path_output_metadata", help="path to output metadata.", type=str)

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args = parser.parse_args()

    input_meta = args.path_input_metadata
    output_meta = args.path_output_metadata

    copy_meta(input_meta=input_meta, output_meta=output_meta)