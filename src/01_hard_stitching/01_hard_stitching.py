import os
import argparse
import pandas as pd
from skimage import io, transform
from skimage.color import rgb2gray  # If needed
import numpy as np
from PIL import Image
import numpy as np
# import imageio
import tifffile
import sys

# Define the function equivalent to range.x1_q in R
def range_x1_q(x, q):
    """Normalization function"""
    x_positive = x[x > 0]
    tmp_q_high = np.quantile(x_positive, q)
    tmp_q_min = np.quantile(x_positive, 1 - q)
    x = (x - tmp_q_min) / (tmp_q_high - tmp_q_min)
    x[x > 1] = 1
    x[x < 0] = 0
    return x

def hard_stitching(input_path_tiles, input_path_meta, output_folder, conversion_factor, skip_existing, only_dapi):
    """ Stitches the tiles together"""
    print(f"### input path tiles: {input_path_tiles} ###")
    print(f"### input path metadata: {input_path_meta} ###")
    print(f"### output directory: {output_folder} ###")
    print(f"### conversion factor: {conversion_factor} ###")
    print(f"### skip existing: {skip_existing} ###")
    print(f"### only dapi: {only_dapi} ###")
    
    if not os.path.exists(output_folder):
        print(f"### creating folder: {output_folder} ###")
        os.makedirs(output_folder, exist_ok=True)
    
    # conversion_factor = int(conversion_factor)
    
    tmp_folder = os.path.basename(input_path_tiles)
    
    # List all files that match the TIFF pattern
    file_list = [f for f in os.listdir(input_path_tiles) if f.endswith('.tiff')]

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
    
    # Read the CSV file
    tmp_csv = pd.read_csv(input_path_meta)
    # Group by 'S' and 'M', sample one per group
    tmp_csv = tmp_csv.groupby(['S', 'M']).sample(n=1).reset_index(drop=True)
    # Separate 'ImagePixelSize' into 'px_size_X' and 'px_size_Y'
    tmp_csv[['px_size_X', 'px_size_Y']] = tmp_csv['ImagePixelSize'].str.split(',', expand=True)
    # Convert 'px_size_X' and 'px_size_Y' to numeric and divide by 10
    tmp_csv['px_size_X'] = pd.to_numeric(tmp_csv['px_size_X']) / 10
    tmp_csv['px_size_Y'] = pd.to_numeric(tmp_csv['px_size_Y']) / 10
    # Update 'StageXPosition' and 'StageYPosition' based on pixel size
    tmp_csv['StageXPosition'] = tmp_csv['StageXPosition'] / tmp_csv['px_size_X']
    tmp_csv['StageYPosition'] = tmp_csv['StageYPosition'] / tmp_csv['px_size_Y']
    # Separate 'Frame' into multiple new columns
    tmp_csv[['aux_1', 'aux_2', 'tile_size_X', 'tile_size_Y']] = tmp_csv['Frame'].str.split(',', expand=True)
    # Convert 'tile_size_X' and 'tile_size_Y' to numeric
    tmp_csv['tile_size_X'] = pd.to_numeric(tmp_csv['tile_size_X'])
    tmp_csv['tile_size_Y'] = pd.to_numeric(tmp_csv['tile_size_Y'])
    # Calculate new columns 'tmp_X' and 'tmp_Y'
    tmp_csv['tmp_X'] = (tmp_csv['StageXPosition'] - tmp_csv['StageXPosition'].min() + tmp_csv['tile_size_X'] / 2) / conversion_factor
    tmp_csv['tmp_Y'] = (tmp_csv['StageYPosition'] - tmp_csv['StageYPosition'].min() + tmp_csv['tile_size_Y'] / 2) / conversion_factor
    # Round 'tmp_X' and 'tmp_Y'
    tmp_csv['tmp_X'] = np.round(tmp_csv['tmp_X'])
    tmp_csv['tmp_Y'] = np.round(tmp_csv['tmp_Y'])
    # Add a tile ID column
    tmp_csv['tile_id'] = np.arange(1, len(tmp_csv) + 1)
    
    unique_channels = tmp_files['channel_id'].unique()
    
    if only_dapi == True:
        unique_channels = ['DAPI']
    
    for j in unique_channels:
        output_path = os.path.join(output_folder, f"{tmp_folder}_{j}.tiff")
        if skip_existing and os.path.exists(output_path):
            print(f"Skipping existing file {output_path}")
            continue
        
        channel_files = tmp_files[tmp_files['channel_id'] == j]

        # Initialize an empty image matrix
        max_x = int(np.max(tmp_csv['tmp_X']) + np.max(tmp_csv['tile_size_X']) / 2 / conversion_factor)
        max_y = int(np.max(tmp_csv['tmp_Y']) + np.max(tmp_csv['tile_size_Y']) / 2 / conversion_factor)
        tmp_dapi = np.zeros((max_y, max_x))

        # Process each tile
        for index, tmp_row in tmp_csv.iterrows():
            
            tmp_file = channel_files[channel_files['mosaic_index'] == f"S{tmp_row['S']}M{tmp_row['M']}"]
            # tmp_image = imageio.imread(os.path.join(input_path_tiles, tmp_file['ofile'].iloc[0]))
            tmp_image = tifffile.imread(os.path.join(input_path_tiles, tmp_file['ofile'].iloc[0]))
                
            if isinstance(tmp_image, np.ndarray):
                tmp_image = Image.fromarray(tmp_image)
            
            if tmp_image.mode == 'I;16':
                tmp_image = tmp_image.convert('I')
            
            # Now resize using PIL Image methods
            tmp_image = tmp_image.resize(
                (int(tmp_image.width / conversion_factor), int(tmp_image.height / conversion_factor)),
                Image.Resampling.LANCZOS  # Note: ANTIALIAS is deprecated in Pillow >= 9.0.0; use  instead
            )
            tmp_image = np.array(tmp_image)
            
            # Calculate indices based on given formula
            start_x = int(tmp_row['tmp_X'] - (tmp_row['tile_size_X'] / 2 / conversion_factor))
            # end_x = int(tmp_row['tmp_X'] + (tmp_row['tile_size_X'] / 2 / conversion_factor))
            start_y = int(tmp_row['tmp_Y'] - (tmp_row['tile_size_Y'] / 2 / conversion_factor))
            # end_y = int(tmp_row['tmp_Y'] + (tmp_row['tile_size_Y'] / 2 / conversion_factor))
            
            # Check if tmp_image is three-dimensional
            if tmp_image.ndim == 3:
                # Insert tmp_image into tmp_dapi at calculated positions, adjust indexing for Python (zero-based)
                # tmp_dapi[start_y:end_y, start_x:end_x, :] = tmp_image
                tmp_dapi[start_y:(start_y + tmp_image.shape[0]), start_x:(end_x + tmp_image.shape[1]), :] = tmp_image
            else:
                # For non-3D images, ensure only the relevant slice is updated
                # tmp_dapi[start_y:end_y, start_x:end_x] = tmp_image
                tmp_dapi[start_y:(start_y + tmp_image.shape[0]), start_x:(start_x + tmp_image.shape[1])] = tmp_image
        
        # tmp_dapi2 = np.arcsinh(tmp_dapi)  # Apply the asinh transformation
        tmp_dapi = range_x1_q(tmp_dapi, 0.99)
        tmp_dapi = (2**8-1)*tmp_dapi
        tmp_dapi = tmp_dapi.astype('uint8')
        
        tifffile.imwrite(output_path, tmp_dapi, compression='lzma')

def str2bool(v):
    return v.lower() in ('yes', 'true', 't', '1')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coarse stitching from individual tiles.")
    parser.add_argument("--input_tiles", type=str, help="Path to input tiles (path).")
    parser.add_argument("--input_metadata", type=str, help="Path to input metadata file (.csv).")
    parser.add_argument("--output_folder", type=str, help="Path to output path to save images (path).")
    parser.add_argument("--conversion_factor", type=float, help="Conversion factor for downscaling (numeric).")
    parser.add_argument("--skip_existing", type=str2bool, help="skip already existing results (boolean).")
    parser.add_argument("--only_dapi", type=str2bool, help="Boolean to do only DAPI (boolean).")

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

input_path_tiles = args.input_tiles
input_path_meta = args.input_metadata
output_folder = args.output_folder
conversion_factor = args.conversion_factor
skip_existing = args.skip_existing
only_dapi = args.only_dapi

hard_stitching(input_path_tiles, input_path_meta, output_folder, conversion_factor, skip_existing, only_dapi)