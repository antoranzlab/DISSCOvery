# Load libraries
import os
import sys
import numpy as np
import tifffile as tiff
from skimage.io import imread
from patchify import patchify, unpatchify
import gc
import argparse
import pandas as pd
from skimage.measure import label, regionprops

gc.collect()

def extract_bounding_boxes(mask):
    """Extract bounding boxes from a mask """
    labeled_mask = label(mask)
    regions = regionprops(labeled_mask)
    bounding_boxes = []
    for region in regions:
        min_row, min_col, max_row, max_col = region.bbox
        bounding_boxes.append([min_row, min_col, max_row, max_col])
    return bounding_boxes

def filter_small_annotations(mask, threshold=0.1):
    """Filter small annotations from the mask"""
    labeled_mask = label(mask)
    regions = regionprops(labeled_mask)
    if not regions:
        return mask

    max_area = mask.shape[0]*mask.shape[1]
    min_area = 0.001 * max_area
    
    filtered_mask = np.zeros_like(mask)
    for region in regions:
        if region.area >= min_area:
            for coords in region.coords:
                filtered_mask[coords[0], coords[1]] = 1
    return filtered_mask

def create_bounding_boxes(input_image_path, bbox_tile_path, filter_small = True):
  
    if not os.path.exists(os.path.dirname(bbox_tile_path)):
        os.makedirs(os.path.dirname(bbox_tile_path))
    
    input_mask = imread(input_image_path)
    
    if filter_small:
        input_mask = filter_small_annotations(input_mask)
    
    # tiff.imwrite(input_image_path.replace('manual_masks', 'manual_masks_postprocessed'), 255*input_mask, compression = 'lzma')
    
    bounding_boxes = extract_bounding_boxes(input_mask)
    
    # Create DataFrame
    df = pd.DataFrame(bounding_boxes, columns=['minr', 'minc', 'maxr', 'maxc'])
    
    # Add labels
    df['scan_region'] = [f'S{i}' for i in range(len(df))]
    
    # Sort DataFrame by label (if necessary)
    df = df.sort_values(by='scan_region').reset_index(drop=True)
    
    df.to_csv(bbox_tile_path, index = False)
    
    return True

def str2bool(v):
    return v.lower() in ('yes', 'true', 't', '1')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Smart Tissue Selection - generate BB. type STS_generate_BB.py -h for positional and optional inputs description')
    parser.add_argument('--input_image_path', type=str,
                        help='full path to the file containing the mask, e.g. /path/to/project_directory/output_STS/masks/BM_R00_V01_BENCHMARK_ND_DAPI.tiff ')
    parser.add_argument('--bbox_tile_path', type=str,
                        help='full path to csv file where the STS bounding boxes will be saved, e.g./path/to/project_directory/output_STS/BB/BM_R00_V01_BENCHMARK_ND_DAPI.csv ')
    parser.add_argument('--filter_small', type=str2bool, default=True,
                        help='boolean indicating whether small objects are filtered out or not, e.g. True ')

    # If you use the csv job list file comment out everything starting from here to 'Job list parser' comment

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    input_image_path = args.input_image_path #'/path/to/project_directory/output_STS/masks/BM_R00_V01_BENCHMARK_ND_DAPI.tiff'
    bbox_tile_path = args.bbox_tile_path #'/path/to/project_directory/output_STS/BB/BM_R00_V01_BENCHMARK_ND_DAPI.csv'
    filter_small = args.filter_small #True

    create_bounding_boxes(input_image_path = input_image_path, bbox_tile_path = bbox_tile_path, filter_small = filter_small)


    # Job list parser
    # tmp_csv = pd.read_csv('/path/to/project_directory/BB_estimation_job_list.csv')
    #
    # for index, row in tmp_csv.iterrows():
    #     input_image_path = row['input_image']
    #     bbox_tile_path = row['output_bb']
    #     filter_small = row['filter_small']
    #
    #     # Assuming `hard_stitching` is defined as previously described
    #     create_bounding_boxes(input_image_path=input_image_path, bbox_tile_path=bbox_tile_path, filter_small=filter_small)
