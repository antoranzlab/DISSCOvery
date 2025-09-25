import sys
import os
import argparse
import pandas as pd
import shutil

def copy_files(in_path, channel, out_path_corr, skip_existing=False):
    """Copy the files from input- to output directory"""

    print(f"### input path tiles: {in_path} ###")
    print(f"### channel identifier: {channel} ###")
    print(f"### output directory tiles: {out_path_corr} ###")
    print(f"### skip existing: {skip_existing} ###")
    
    # Check if the output directories exist and create them if they do not
    if not os.path.isdir(out_path_corr):
        print(f"### creating folder: {out_path_corr} ###")
        os.makedirs(out_path_corr)
    
    # Proceed if the input directory and output directories exist
    if os.path.isdir(in_path) and os.path.isdir(out_path_corr):
        
        tmp_folder = os.path.basename(in_path)
        
        # List all files that match the TIFF pattern
        file_list = [f for f in os.listdir(in_path) if f.endswith('.tiff')]
    
        # Create a DataFrame from the list
        tmp_files = pd.DataFrame({'ofile': file_list})
    
        # Remove the '.tif' extension and handle specific string replacements
        tmp_files['file'] = tmp_files['ofile'].str.replace('.tiff', '', regex=True)
        tmp_files['file'] = tmp_files['file'].str.replace('AF_FITC', 'AFFITC', regex=True)
    
        # Split the 'file' into multiple columns based on the underscore delimiter
        file_components = tmp_files['file'].str.split('_', expand=True)
        file_components.columns = ['slide_id', 'round_id', 'version_id', 'project_id', 'user_id', 'mosaic_index', 'channel_id']
        
        # Concatenate these new columns back to the original DataFrame
        tmp_files = pd.concat([tmp_files, file_components], axis=1)
        tmp_files = tmp_files[tmp_files['channel_id'] == channel]
        
        # Copy files
        for _, row in tmp_files.iterrows():
            src = os.path.join(in_path, row['ofile'])  # Source file path
            dst = os.path.join(out_path_corr, row['ofile'])  # Destination file path
            shutil.copy2(src, dst)  # Copy with metadata

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Flat Field Correction')
    parser.add_argument("--input_images", help="path to input images. Example: path/to/project_directory/output_tiles_tiffs/BM_R00_V01_BENCHMARK_ND", type=str)
    parser.add_argument("--channel", help="channel identifier. Example: DAPI", type=str)
    parser.add_argument("--output_path_corrected_tiles", help="path to output corrected tiles. Example: path/to/project_directory/output_FFC/BM_R00_V01_BENCHMARK_ND", type=str)
    parser.add_argument("--skip_existing", help="skip existing results. Example: False", type=bool)

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    in_path = args.input_images
    channel = args.channel
    out_path_corr = args.output_path_corrected_tiles
    skip_existing = args.skip_existing

    copy_files(in_path=in_path, channel=channel, out_path_corr=out_path_corr, skip_existing=skip_existing)