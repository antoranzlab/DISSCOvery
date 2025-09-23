#!/usr/bin/env python

# Load libraries
import os
import sys
import gc
import tifffile
import argparse
import cv2
import pandas as pd
import numpy as np

gc.collect()

# Function to apply the transformation to a single point (x, y)
def transform_points(x, y, tvec, scale, angle):
    # Step 1: Apply reverse translation
    x_translated = x + tvec[0]
    y_translated = y + tvec[1]

    # Step 2: Convert angle from degrees to radians and apply reverse rotation
    angle_radians = np.deg2rad(angle)
    x_rotated = x_translated * np.cos(angle_radians) - y_translated * np.sin(angle_radians)
    y_rotated = x_translated * np.sin(angle_radians) + y_translated * np.cos(angle_radians)

    # Step 3: Apply scaling
    x_scaled = x_rotated * scale
    y_scaled = y_rotated * scale

    return x_scaled, y_scaled

def transform_image(img, scale=1.0, angle=0.0, tvec=(0, 0)):
    
    img = np.array(img)
    # Create the Translation Matrix
    translation_matrix = np.float32([
        [1, 0, tvec[1]],
        [0, 1, tvec[0]]
    ])
    # angle_radians = np.deg2rad(angle)
    # Note: OpenCV calculates the center point of rotation from the dimensions
    center = (img.shape[1] // 2, img.shape[0] // 2)
    # Create the rotation matrix
    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1)  # scale is set to 1 here
    # Create the scaling matrix
    scaling_matrix = np.array([[scale, 0, 0], [0, scale, 0]])

    # Apply Translation
    translated_image = cv2.warpAffine(img, translation_matrix, (img.shape[1], img.shape[0]))
    # Apply Rotation
    rotated_image = cv2.warpAffine(translated_image, rotation_matrix, (translated_image.shape[1], translated_image.shape[0]))
    # Apply Scaling
    scaled_image = cv2.warpAffine(rotated_image, scaling_matrix, (rotated_image.shape[1], rotated_image.shape[0]))
    
    return(scaled_image)

def reverse_transformation(input_path_tm, input_path_masks, input_path_bb, output_path_masks, output_path_bb): #output_image #moving_image
    
    if not os.path.exists(os.path.dirname(output_path_masks)):
        os.makedirs(os.path.dirname(output_path_masks))
    
    if not os.path.exists(os.path.dirname(output_path_bb)):
        os.makedirs(os.path.dirname(output_path_bb))

    # loading images
    tmp_mask = tifffile.imread(input_path_masks)
    tmp_bb = pd.read_csv(input_path_bb)
    
    print(f"Trying to load: {input_path_tm}")

    trans=np.load(input_path_tm)

    scale=trans[0]
    angle=trans[1]
    t1=trans[2]
    t2=trans[3]
    tvec=np.array([t1,t2])
    img_center = tmp_mask.shape
    tmp_x=img_center[0]/2
    tmp_y=img_center[1]/2
    img_center=(tmp_x,tmp_y)
    # # Invert the translation vector
    tvec = -np.array(tvec)
    # # Invert the angle
    angle = -angle  # Ensure this is in radians if using trigonometric functions
    # # Invert the scaling factor
    scale = 1 / scale

    tmp_mask = transform_image(tmp_mask, scale, angle, tvec)
    tifffile.imwrite(output_path_masks, tmp_mask, compression='lzma')
    
    translation_matrix = np.float32([
        [1, 0, tvec[1]],
        [0, 1, tvec[0]]
    ])
    # Note: OpenCV calculates the center point of rotation from the dimensions
    center = (tmp_mask.shape[1] // 2, tmp_mask.shape[0] // 2)
    # Create the rotation matrix
    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1)  # scale is set to 1 here
    # Create the scaling matrix
    scaling_matrix = np.array([[scale, 0, 0], [0, scale, 0]])

    new_bb = []
    
    # Set points in the image based on DataFrame
    for index, row in tmp_bb.iterrows():
        # Get top-left and bottom-right corners
        top_left = [row['minc'], row['minr'], 1]   # x, y, 1
        bottom_right = [row['maxc'], row['maxr'], 1]

        # Apply inverse transform
        tl_transformed = translation_matrix @ top_left
        br_transformed = translation_matrix @ bottom_right
        tl_transformed = rotation_matrix @ [tl_transformed[0], tl_transformed[1], 1]
        br_transformed = rotation_matrix @ [br_transformed[0], br_transformed[1], 1]
        tl_transformed = scaling_matrix @ [tl_transformed[0], tl_transformed[1], 1]
        br_transformed = scaling_matrix @ [br_transformed[0], br_transformed[1], 1]

        # Build transformed box (and convert to ints)
        minc_t, minr_t = tl_transformed[:2]
        maxc_t, maxr_t = br_transformed[:2]

        new_bb.append({
            'minr': int(round(min(minr_t, maxr_t))),
            'minc': int(round(min(minc_t, maxc_t))),
            'maxr': int(round(max(minr_t, maxr_t))),
            'maxc': int(round(max(minc_t, maxc_t))),
            'scan_region': row['scan_region']
        })

    new_bb = pd.DataFrame(new_bb)
    
    new_bb.to_csv(output_path_bb, index = False)
    
    return(True)

parser = argparse.ArgumentParser(description='Split scenes - reverse transformation. Type reverse_transformation.py -h for positional and optional inputs description')
parser.add_argument('--input_path_tm', type=str,
                    help='Full path to the transformation matrix (.npy). Example: /path/to/project_directory/output_coarse_registration_tm/BM_R05_V01_BENCHMARK_ND_DAPI.npy')
parser.add_argument('--input_path_masks', type=str,
                    help='Full path to the foreground mask (.tiff). Example: /path/to/project_directory/output_STS/masks/BM_R01_V02_BENCHMARK_ND_DAPI.tiff ')
parser.add_argument('--input_path_bb', type=str,
                    help='Full path to the bounding boxes (.csv). Example: /path/to/project_directory/output_STS/BB/BM_R01_V02_BENCHMARK_ND_DAPI.csv ')
parser.add_argument('--output_path_masks', type=str,
                    help='Full path to the inverted masks (.tiff). Example: /path/to/project_directory/output_split_scenes/inverted_masks/BM_R05_V01_BENCHMARK_ND_DAPI.tiff')
parser.add_argument('--output_path_bb', type=str,
                    help='Full path to the inverted bounding boxes (.csv). Example: /path/to/project_directory/output_split_scenes/inverted_BB/BM_R05_V01_BENCHMARK_ND_DAPI.csv')

# If no arguments are provided, show help and exit
if len(sys.argv) == 1:
    parser.print_help(sys.stderr)
    sys.exit(1)

args = parser.parse_args()

input_path_tm = args.input_path_tm
input_path_masks = args.input_path_masks
input_path_bb = args.input_path_bb
output_path_masks = args.output_path_masks
output_path_bb = args.output_path_bb
reverse_transformation(input_path_tm = input_path_tm, input_path_masks = input_path_masks, input_path_bb = input_path_bb, output_path_masks = output_path_masks, output_path_bb = output_path_bb)
