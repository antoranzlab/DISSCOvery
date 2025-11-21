import os
import sys
import argparse
import pandas as pd
from skimage import io, transform
from skimage.color import rgb2gray  # If needed
import numpy as np
from PIL import Image
import numpy as np
# import imageio
import tifffile

# Define the function equivalent to range.x1_q in R
def range_x1_q(x, q):
    x_positive = x[x > 0]
    tmp_q_high = np.quantile(x_positive, q)
    tmp_q_min = np.quantile(x_positive, 1 - q)
    x = (x - tmp_q_min) / (tmp_q_high - tmp_q_min)
    x[x > 1] = 1
    x[x < 0] = 0
    return x

def resize_processed(input_path_image, output_path_image, conversion_factor, skip_existing):
    print(f"### input image: {input_path_image} ###")
    print(f"### output image: {output_path_image} ###")
    print(f"### conversion factor: {conversion_factor} ###")
    print(f"### skip existing: {skip_existing} ###")
    
    if not os.path.exists(os.path.dirname(output_path_image)):
        print(f"### creating folder: {os.path.dirname(output_path_image)} ###")
        os.makedirs(os.path.dirname(output_path_image), exist_ok=True)
    
    # conversion_factor = int(conversion_factor)
    tmp_image = tifffile.imread(input_path_image)
        
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
    
    tmp_image = range_x1_q(tmp_image, 0.99)
    tmp_image = (2**8-1)*tmp_image
    tmp_image = tmp_image.astype('uint8')
    
    tifffile.imwrite(output_path_image, tmp_image, compression='lzma')

def str2bool(v):
    return v.lower() in ('yes', 'true', 't', '1')

parser = argparse.ArgumentParser(description="Coarse stitching from individual tiles.")
parser.add_argument("--input_path_image", type=str, help="Path to input images (path).")
parser.add_argument("--output_path_image", type=str, help="Path to output path to save images (path).")
parser.add_argument("--conversion_factor", type=float, help="Conversion factor for downscaling (numeric).")
parser.add_argument("--skip_existing", type=str2bool, help="Boolean to skip already existing results (boolean).")

# If no arguments are provided, show help and exit
if len(sys.argv) == 1:
    parser.print_help(sys.stderr)
    sys.exit(1)
args = parser.parse_args()

input_path_image = args.input_path_image
output_path_image = args.output_path_image
conversion_factor = args.conversion_factor
skip_existing = args.skip_existing

resize_processed(input_path_image, output_path_image, conversion_factor, skip_existing)
