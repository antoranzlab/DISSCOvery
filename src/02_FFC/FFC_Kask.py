import numpy as np
import sys
import os
from tifffile import imread, imwrite
import argparse
import imagecodecs
import tensorflow as tf
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.colors import TwoSlopeNorm, LinearSegmentedColormap
import pandas as pd
from PIL import Image
import cv2
from joblib import Parallel, delayed
from skimage.transform import resize

# Extract the background part of the image
def extract_background(tmp_position, in_path, tmp_files, tmp_csv, mask_background, conversion_factor):
    """Define the background"""

    tmp_file = tmp_files.iloc[tmp_position]  # Get the current row as a Series
    
    # Filter tile metadata
    tile_meta = tmp_csv[tmp_csv['tile_filename'] == tmp_file['ofile']]
    
    # Read the image
    tmp_image = imread(os.path.join(in_path, tmp_file['ofile']))
    
    # Extract tile metadata values
    tmp_X = tile_meta['tmp_X'].values[0]
    tmp_Y = tile_meta['tmp_Y'].values[0]
    tile_size_X = tile_meta['tile_size_X'].values[0]
    tile_size_Y = tile_meta['tile_size_Y'].values[0]

    # Compute the mask indices
    y_start = int(tmp_X - (tile_size_X / 2) / conversion_factor) + 1
    y_end = int(tmp_X + (tile_size_X / 2) / conversion_factor)
    x_start = int(tmp_Y - (tile_size_Y / 2) / conversion_factor) + 1
    x_end = int(tmp_Y + (tile_size_Y / 2) / conversion_factor)
    
    # Extract the corresponding mask
    tmp_mask = mask_background[x_start:x_end, y_start:y_end]
    tmp_mask = resize(tmp_mask, (int(tmp_image.shape[0]/conversion_factor), int(tmp_image.shape[1]/conversion_factor)), anti_aliasing=False)
    
    # Resize the image to match the mask dim
    tmp_image = resize(tmp_image, (tmp_mask.shape[0], tmp_mask.shape[1]), anti_aliasing=False, preserve_range=True)
    tmp_image = tmp_image.astype('float32')
    # Apply the mask: Set masked pixels to NaN
    tmp_image[tmp_mask == 255] = np.nan
    
    return tmp_file['ofile'], tmp_image  # Return filename and processed image

# Normalize the image centered at 1
def normalize_image(tmp_image):
    """ Normalize the image by its median background. """

    tmp_median_background = np.median(tmp_image[tmp_image > 0]) if np.any(tmp_image > 0) else np.nan

    if not np.isnan(tmp_median_background) and tmp_median_background > 0:
        return tmp_image / tmp_median_background  # Normalize the image
    return tmp_image  # Return unchanged if median is NaN or 0

# Process and save images after FFC
def process_image(tmp_position, tmp_files, df_medians, tmp_vignette_background, out_path_corr, in_path):
    """Apply the correction"""

    # Get the current file metadata
    tmp_file = tmp_files.iloc[tmp_position]
    
    # Get the corresponding median tile data
    tmp_median_tile = df_medians[df_medians['ofile'] == tmp_file['ofile']]
    
    if tmp_median_tile.empty:
        return  # Skip processing if no median data is found
    
    tmp_median_background = tmp_median_tile['median.background'].values[0]  # Extract median value
    
    # Read the image
    tmp_image = imread(os.path.join(in_path, tmp_file['ofile']))
    
    # Ensure tmp_vignette_background matches image dimensions
    if tmp_image.shape != tmp_vignette_background.shape:
        tmp_vignette_background = resize(tmp_vignette_background, (tmp_image.shape[0], tmp_image.shape[1]), anti_aliasing=False)
    
    # Apply background correction
    tmp_image = tmp_image - (tmp_median_background * tmp_vignette_background) + tmp_median_background
    
    # Clip before conversion: 65536 would wrap to zero in uint16.
    if not np.isfinite(tmp_image).all():
        raise ValueError(f"Non-finite FFC intensities in {tmp_file['ofile']}")
    tmp_image = np.clip(tmp_image, 0, 65535)
    tmp_image = tmp_image.astype('uint16')
    # Save the corrected image
    imwrite(os.path.join(out_path_corr, tmp_file['ofile']), tmp_image, compression='lzma')
    
    return True

def RunKask(in_path, in_meta, in_mask, px_size, channel, out_path_corr, out_path_templates, n_cores=10, skip_existing=False):
    """Main function that does the FFC using the method by Kask et al"""

    print(f"### input path tiles: {in_path} ###")
    print(f"### input path metadata: {in_meta} ###")
    print(f"### input path mask: {in_mask} ###")
    print(f"### mask pixel size: {px_size} ###")
    print(f"### channel identifier: {channel} ###")
    print(f"### output directory tiles: {out_path_corr} ###")
    print(f"### output directory templates: {out_path_templates} ###")
    print(f"### number of cores: {n_cores} ###")
    print(f"### skip existing: {skip_existing} ###")
    
    # Check if the output directories exist and create them if they do not
    if not os.path.isdir(out_path_corr):
        print(f"### creating folder: {out_path_corr} ###")
        os.makedirs(out_path_corr)
        
    if not os.path.isdir(out_path_templates):
        print(f"### creating folder: {out_path_templates} ###")
        os.makedirs(out_path_templates)
        
    # Proceed if the input directory and output directories exist
    if os.path.isdir(in_path) and os.path.isdir(out_path_templates) and os.path.isdir(out_path_corr):
        
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
        
        # Read the CSV file
        tmp_csv = pd.read_csv(in_meta)
        
        raw_px_size = tmp_csv['ImagePixelSize'].unique()
        split_px_size = float(raw_px_size[0].split(',')[0])/10
        conversion_factor = px_size/split_px_size
        
        # Group by 'S' and 'M', sample one per group
        # tmp_csv = tmp_csv.groupby(['S', 'M']).sample(n=1).reset_index(drop=True)
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
        tmp_csv['tmp_X'] = tmp_csv['tmp_X'] - 1
        tmp_csv['tmp_Y'] = tmp_csv['tmp_Y'] - 1
        # Add a tile ID column
        # tmp_csv['tile_id'] = np.arange(1, len(tmp_csv) + 1)

        ## Load and process mask
        mask_image = imread(in_mask)
        # mask_image = mask_image/255
        # Erosion and dilation with OpenCV
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (151, 151))
        mask_background = 255 - cv2.dilate(mask_image, kernel)
        mask_foreground = cv2.erode(mask_image, kernel)
        
        # Initialize an empty dictionary to store the background images
        tmp_list_background = Parallel(n_jobs=n_cores)(delayed(extract_background)(j, in_path, tmp_files, tmp_csv, mask_background, conversion_factor) for j in range(len(tmp_files)))
        tmp_list_background = {ofile: img for ofile, img in tmp_list_background if img is not None}
        
        # Extract the median of the background
        df_medians = []
        
        for x in range(len(tmp_files)):
            tmp_file = tmp_files.iloc[x].copy()  # Get the file metadata (as a Pandas Series)
            tmp_image = tmp_list_background[tmp_file['ofile']]  # Get the corresponding background image
            
            # Compute the median of non-zero values
            tmp_median_background = np.median(tmp_image[tmp_image > 0]) if np.any(tmp_image > 0) else np.nan
            
            # Add the median background as a new column
            tmp_file['median.background'] = tmp_median_background
            df_medians.append(tmp_file)
        
        # Convert list of dictionaries to DataFrame
        df_medians = pd.DataFrame(df_medians)
        
        # Fill missing median values with the global median
        global_median = df_medians['median.background'].median(skipna=True)
        df_medians['median.background'].fillna(global_median, inplace=True)
        
        # Save the dataframe as CSV
        tmp_files['tissue_id'] = tmp_files['slide_id'] + '_' + tmp_files['round_id'] + '_' + tmp_files['version_id'] + '_' + tmp_files['project_id'] + '_' + tmp_files['user_id'] + '_' + tmp_files['channel_id']
        
        output_filename = f"df_medians_{tmp_files['tissue_id'].unique()[0]}.csv"
        df_medians.to_csv(os.path.join(out_path_templates, output_filename), sep=',', index=False)
        
        # Apply parallel processing
        tmp_list_background = Parallel(n_jobs=n_cores)(delayed(normalize_image)(tmp_image) for tmp_image in tmp_list_background.values())
        
        # Stack all images into a 3D NumPy array (Height x Width x N images)
        arr = np.stack(tmp_list_background, axis=-1)  # Stack along the third dimension
        # Compute the median along the third dimension (ignoring NaNs)
        tmp_vignette_background = np.nanmedian(arr, axis=2)
        # Resize to original
        tmp_vignette_background = resize(tmp_vignette_background, (tmp_csv['tile_size_X'].unique()[0], tmp_csv['tile_size_Y'].unique()[0]), anti_aliasing=False) 
        
        # Run parallel execution with joblib
        tmp_run = Parallel(n_jobs=n_cores)(delayed(process_image)(x, tmp_files, df_medians, tmp_vignette_background, out_path_corr, in_path) for x in range(len(tmp_files)))
        
		    # Create a custom divergent colormap
        colors = ["indianred", "white", "dodgerblue"]
        n_bins = 100  # More bins will give you a smoother transition
        cmap_name = 'custom1'
        cm = LinearSegmentedColormap.from_list(cmap_name, colors, N=n_bins)
        
        # Save computations
        output_filename = f"{tmp_files['tissue_id'].unique()[0]}_darkfield.npy"
        np.save(os.path.join(out_path_templates, output_filename), tmp_vignette_background)
        
        epsilon = 1*10**(-3)
        if tmp_vignette_background.min() > 1:
            norm = TwoSlopeNorm(vmin=tmp_vignette_background.min()-epsilon, vcenter=tmp_vignette_background.mean(), vmax=tmp_vignette_background.max()+epsilon)
        else: 
            norm = TwoSlopeNorm(vmin=tmp_vignette_background.min()-epsilon, vcenter=1, vmax=tmp_vignette_background.max()+epsilon)
        
        sns_heatmap1 = sns.heatmap(tmp_vignette_background, cmap=cm, norm=norm)
        output_filename = f"{tmp_files['tissue_id'].unique()[0]}_darkfield.tiff"
        # Display the plot
        plt.tight_layout()  # Adjust subplots to fit into figure area.
        plt.savefig(os.path.join(out_path_templates, output_filename), dpi=300)  # Save the figure to a file
        plt.close()  # Close the plot

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Flat Field Correction with KASK')
    parser.add_argument("--input_images", help="path to input images. Example: /path/to/project_directory/output_tiles_tiffs/BM_R00_V01_BENCHMARK_ND", type=str)
    parser.add_argument("--input_metadata", help="path to input metadata. Example: /path/to/project_directory/output_tiles_tiffs/BM_R00_V01_BENCHMARK_ND/BM_R00_V01_BENCHMARK_ND.csv", type=str)
    parser.add_argument("--input_mask", help="path to input mask. Example: /path/to/project_directory/output_FFC_kask_masks/BM/BM_R00_V01_BENCHMARK_ND_DAPI.tiff", type=str)
    parser.add_argument("--pixel_size", help="pixel size used for the mask. Example: 2.6", type=float)
    parser.add_argument("--channel", help="channel identifier. Example: DAPI", type=str)
    parser.add_argument("--output_path_corrected_tiles", help="path to output corrected tiles. Example: /path/to/project_directory/output_FFC/BM_R00_V01_BENCHMARK_ND", type=str)
    parser.add_argument("--output_path_templates", help="path to output teampltes. Example: /path/to/project_directory/output_FFC_templates/KASK/BM_R00_V01_BENCHMARK_ND", type=str)
    parser.add_argument("--n_cores", help="number of cores. Example: 10", type=int)
    parser.add_argument("--skip_existing", help="skip existing results. Example: False", type=bool)

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    in_path = args.input_images
    in_meta = args.input_metadata
    in_mask = args.input_mask
    px_size = args.pixel_size
    channel = args.channel
    out_path_corr = args.output_path_corrected_tiles
    out_path_templates = args.output_path_templates
    n_cores = args.n_cores
    skip_existing = args.skip_existing

    RunKask(in_path=in_path, in_meta=in_meta, in_mask=in_mask, px_size=px_size, channel=channel, out_path_corr=out_path_corr, out_path_templates=out_path_templates, n_cores=n_cores, skip_existing=skip_existing)
