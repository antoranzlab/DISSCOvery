import pandas as pd
import argparse
import os
import sys

from czi_metadata import find_czi_files, read_channel_tables

def parse_metadata(directory, output_csv_channels, output_csv_slides):
    # List all entries in the directory given by "path"
    czi_files = find_czi_files(directory)
    df_meta = read_channel_tables(czi_files)

    # Create a new column with the basename of each file path
    df_meta['basename'] = df_meta['czi_file'].apply(lambda x: os.path.basename(x.replace('.czi', '')))
    # Split the basename into multiple columns
    df_meta[['slide_id', 'round_number', 'version_id', 'project_id', 'user_id']] = df_meta['basename'].str.split('_',
                                                                                                                 expand=True)
    # Substitute AF_FITC for AF
    df_meta['channel_id'] = df_meta['channel_id'].replace('AF_FITC', 'AF')
    df_meta['channel_id'] = df_meta['channel_id'].replace('FITC_AF', 'AF')
    # Save to csv
    os.makedirs(os.path.dirname(output_csv_channels), exist_ok=True)
    df_meta.to_csv(output_csv_channels, index=False)

    df_slides = pd.DataFrame(df_meta['slide_id'].unique(), columns=['slide_id'])
    df_slides['folder'] = df_slides['slide_id']
    # Save to csv
    os.makedirs(os.path.dirname(output_csv_slides), exist_ok=True)
    df_slides.to_csv(output_csv_slides, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='CZIReader - extract metadata. type czi_extract_metadata.py -h for positional and optional inputs description')
    parser.add_argument('--directory', type=str,
                        help=' parent directory where the czi files are stored e.g. /path/to/raw_data_files ')
    parser.add_argument('--output_csv_channels', type=str,
                        help='path to csv where the channel metadata will be stored e.g. /path/to/project_directory/experimental_design/channel_names.csv')
    parser.add_argument('--output_csv_slides', type=str,
                        help='path to csv where the slide metadata will be stored e.g. /path/to/project_directory/experimental_design/exp_design_slides.csv')

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    directory = args.directory # Example: /path/to/raw_data_files
    output_csv_channels = args.output_csv_channels # Example: /path/to/project_directory/channel_names.csv
    output_csv_slides = args.output_csv_slides

    parse_metadata(directory=directory, output_csv_channels=output_csv_channels, output_csv_slides=output_csv_slides)

