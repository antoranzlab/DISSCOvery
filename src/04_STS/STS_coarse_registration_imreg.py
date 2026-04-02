#!/usr/bin/env python

# Load libraries
import os
import sys
import gc
import tifffile
import argparse
import imreg_dft as ird
# from skimage.io import imread, imsave
import tifffile
import PIL.Image
# increase maximum image size
# from PIL import Image, ImageOps
# PIL.Image.MAX_IMAGE_PIXELS = 29331200000000
# hacky thing to bypass the np.bool error
import numpy as np
import pandas as pd
np.bool = np.bool_

gc.collect()


def range_x1_q(image, q):
    """ Function to apply range normalization """
    non_zero_pixels = image[image > 0]
    q_high = np.quantile(non_zero_pixels, q)
    q_low = np.quantile(non_zero_pixels, 1 - q)
    image = (image - q_low) / (q_high - q_low)
    image = np.clip(image, 0, 1)
    return image

def get_regstat(fixed_image, query_image, output_image, output_tm):
    """Register images"""
    if not os.path.exists(os.path.dirname(output_image)):
        os.makedirs(os.path.dirname(output_image), exist_ok=True)
    
    if not os.path.exists(os.path.dirname(output_tm)):
        os.makedirs(os.path.dirname(output_tm), exist_ok=True)
        
    # loading images
    # fixed = np.asarray(Image.open(fixed_image))
    fixed = tifffile.imread(fixed_image)
    # query = np.asarray(Image.open(query_image))
    query = tifffile.imread(query_image)
    
    fixed_height, fixed_width = fixed.shape[:2]
    query_height, query_width = query.shape[:2]
    
    # Calculate the padding or cropping needed
    height_diff = fixed_height - query_height
    width_diff = fixed_width - query_width
    
    # Handle height adjustment
    if height_diff > 0:
        # Padding height
        query = np.pad(query, ((height_diff // 2, height_diff - height_diff // 2), (0, 0)), 'constant', constant_values=0)
    elif height_diff < 0:
        # Cropping height
        crop_top = -height_diff // 2
        crop_bottom = query_height + height_diff // 2
        query = query[crop_top:crop_bottom, :]
    
    # Handle width adjustment on the adjusted query
    if width_diff > 0:
        # Padding width
        query = np.pad(query, ((0, 0), (width_diff // 2, width_diff - width_diff // 2)), 'constant', constant_values=0)
    elif width_diff < 0:
        # Cropping width
        crop_left = -width_diff // 2
        crop_right = query_width + width_diff // 2
        query = query[:, crop_left:crop_right]
    
    # registration
    res=ird.similarity(fixed, query, constraints= {'angle': (0, 15), 'scale': (1, 0.05)})
    def_query=res['timg']
    scale=res['scale']
    angle=res['angle']
    (t0,t1)=res['tvec']
    
    #def_query, scale, angle, (t0, t1) = imreg.similarity(fixed, query)
    def_mov_array=np.array([scale,angle,t0,t1])
    
    def_query=np.clip(def_query, None, query.max())
    
    def_query = def_query.astype(query.dtype)
    
    # imsave(tm, def_query)
    tifffile.imwrite(output_image, def_query, compression='lzma')
    np.save(output_tm, def_mov_array)
    
    return(True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Smart Tissue Selection - coarse registration. Type STS_coarse_registration_imreg.py -h for positional and optional inputs description')
    parser.add_argument('--path_fixed_image', type=str,
                        help=' full path to the reference image (.tiff). Example, path/to/project_directory/hard_stitching/BM/BM_R01_V01_BENCHMARK_ND_DAPI.tiff')
    parser.add_argument('--path_query_image', type=str,
                        help='full path to the query/moving image (.tiff). Example, /path/to/project_directory/hard_stitching/BM/BM_R02_V01_BENCHMARK_ND_DAPI.tiff')
    parser.add_argument('--path_query_registered', type=str,
                        help='full path to the registered query/moving image (.tiff). Example, /path/to/project_directory/output_coarse_registration/images/BM/BM_R02_V01_BENCHMARK_ND_DAPI.tiff')
    parser.add_argument('--path_transformation_matrix', type=str,
                        help='full path to the transformation matrix (.npy). Example, /path/to/project_directory/output_coarse_registration/tm/BM/BM_R02_V01_BENCHMARK_ND_DAPI.npy')

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

fixed_image = args.path_fixed_image
query_image = args.path_query_image
output_image = args.path_query_registered
output_tm = args.path_transformation_matrix

get_regstat(fixed_image = fixed_image, query_image = query_image, output_image = output_image, output_tm = output_tm)
