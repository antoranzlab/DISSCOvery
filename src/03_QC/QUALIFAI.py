#!/usr/bin/env python

import argparse
import os
import sys
import numpy as np
import shutil
import torch
import pandas as pd
import tifffile
from tqdm import tqdm
from torch.utils.data import Dataset, DataLoader
from segmentation_models_pytorch import UnetPlusPlus

from PIL import Image
import tifffile as tiff
import pandas as pd

# import skimage
from skimage import io
from skimage.io import imread
from patchify import patchify, unpatchify
import gc

gc.collect()

# Define patch size and step size
patch_size = 512
overlap_percentage = 0.2
overlap = int(patch_size * overlap_percentage)
step = patch_size - overlap
batch_size = 16
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
n_classes = 6

# Function to apply range normalization
def range_x1_q(image, q):
  non_zero_pixels = image[image > 0]
  q_high = np.quantile(non_zero_pixels, q)
  q_low = np.quantile(non_zero_pixels, 1 - q)
  image = (image - q_low) / (q_high - q_low)
  image = np.clip(image, 0, 1)
  return image

 # if cpu_only:
 #    os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

# Function to reconstruct image from patches
def reconstruct_from_patches(patches, image_shape, step):
    # reconstructed_image = np.zeros((image_shape[0], image_shape[1], 5), dtype = np.float32)
    reconstructed_image = np.zeros((image_shape[0], image_shape[1]), dtype = np.uint8)
    # patch_count = np.zeros(image_shape)

    patch_height, patch_width = patches.shape[2], patches.shape[3]
    
    for i in range(patches.shape[0]):
        for j in range(patches.shape[1]):
            # patch = patches[i, j, :, :, :]
            patch = patches[i, j, :, :]
            margin = int((patch.shape[0] - step)/2)
            x_start = int(margin)
            y_start = int(margin)
            x_end = int((patch.shape[0] - margin))
            y_end = int((patch.shape[0] - margin))
            # valid_patch = patch[x_start:x_end, y_start:y_end, :]
            valid_patch = patch[x_start:x_end, y_start:y_end]
            x_start = i * step + margin
            y_start = j * step + margin
            x_end = i * step + patch_height - margin
            y_end = j * step + patch_width - margin

            # Add the patch to the reconstructed image and increment the patch count
            # reconstructed_image[x_start:x_end, y_start:y_end, :] = valid_patch
            reconstructed_image[x_start:x_end, y_start:y_end] = valid_patch
            # patch_count[x_start:x_end, y_start:y_end] += 1
    
    # Divide the reconstructed image by the patch count to average the overlapping areas
    # reconstructed_image /= patch_count
    return reconstructed_image

def qualifai(input_image_path, output_image_path, model_path):
  
  ## Load models
  # tmp_model = load_model(model_path, compile=False)
  tmp_model = UnetPlusPlus(encoder_name="resnet34", in_channels=1, classes=n_classes)
  #model = DeepLabV3Plus(encoder_name="efficientnet-b4", in_channels=1, classes=n_classes)
  
  tmp_model.load_state_dict(torch.load(model_path, map_location=device))
  # tmp_model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))
  tmp_model.to(device)
  tmp_model.eval()
  
  ## Create output directory if it doesnt exists
  os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
  
  ## Load image and preprocess it
  input_image = tiff.imread(input_image_path)
  
  # Normalize and convert to 8 bit
  input_image = range_x1_q(input_image, 0.99)
  input_image = 255*input_image
  input_image = input_image.astype(np.uint8)
  
  # Original image dimensions
  original_height, original_width = input_image.shape
  
  # Calculate the necessary padding for height and width
  next_multiple_height = np.ceil(original_height / patch_size) * patch_size
  next_multiple_width = np.ceil(original_width / patch_size) * patch_size
  
  # Calculate padding
  padding_height = int(next_multiple_height - original_height)
  padding_width = int(next_multiple_width - original_width)
  
  # Create a padded array
  input_image = np.pad(input_image, ((0, padding_height), (0, padding_width)), 'constant', constant_values=0)
  
  # Tesselate the input image into patches
  input_patches = patchify(input_image, (patch_size, patch_size), step=step)
  
  n_rows, n_cols, patch_height, patch_width = input_patches.shape

  # Prepare an array to store the predictions with 5 channels (for 5 artifact types)
  # predicted_patches = np.zeros((n_rows, n_cols, patch_height, patch_width, 5), dtype=np.float32)
  predicted_patches = np.zeros((n_rows, n_cols, patch_height, patch_width), dtype=np.uint8)
  
  # Flatten the grid of patches for easier batch processing
  flat_patches = input_patches.reshape(-1, patch_height, patch_width)
  
  # Number of patches and batches
  n_patches = n_rows * n_cols
  n_batches = (n_patches // batch_size) + int(n_patches % batch_size != 0)
  
  # Process each batch
  for batch_idx in range(n_batches):
      print(batch_idx)
      # Generate predictions for each patch
      batch_start = batch_idx * batch_size
      batch_end = min(batch_start + batch_size, n_patches)
      
      # Access the patches in the current batch
      batch_patches = flat_patches[batch_start:batch_end]
      batch_tensor = torch.tensor(batch_patches / 255.0, dtype=torch.float32).unsqueeze(1).to(device)

      # Perform inference
      with torch.no_grad():
          tmp_segmentation = tmp_model(batch_tensor).cpu().numpy()
      
      tmp_segmentation = np.squeeze(tmp_segmentation)  # shape: (B, H, W, C) or (B, C, H, W)
      if tmp_segmentation.ndim == 3:
          tmp_segmentation = np.expand_dims(tmp_segmentation, axis=0)  # (1, C, H, W)
      
      # if tmp_segmentation.ndim == 4 and tmp_segmentation.shape[1] == 7:
      tmp_segmentation = np.transpose(tmp_segmentation, (0, 2, 3, 1))  # (B, H, W, C)
      
      # Find the index of the maximum value along the last axis
      max_indices = np.argmax(tmp_segmentation, axis=-1)
      # Find the maximum values along the last axis
      max_values = np.max(tmp_segmentation, axis=-1)
      # Set indices to 0 where the maximum value is below 0.5
      qc_patch = np.where(max_values >= 0.5, max_indices, 0)

      # Now we need to map the results back to the correct positions in the predicted_patches array
      for idx, flat_idx in enumerate(range(batch_start, batch_end)):
        # Compute row and column indices for the current patch
        row_idx = flat_idx // n_cols
        col_idx = flat_idx % n_cols

        # Insert the segmented result into the correct location in predicted_patches
        predicted_patches[row_idx, col_idx, :, :] = qc_patch[idx]

      gc.collect()
  
  # Reconstruct the full image from the predicted patches
  reconstructed_image = reconstruct_from_patches(predicted_patches, input_image.shape, step)
  reconstructed_image = reconstructed_image[0:original_height, 0:original_width]
  
  # Mapping: old qualifai to multiclass qualifai
  value_map = {
      0: 0, # background to background
      1: 0, # foreground to background
      2: 4, # ab
      3: 1, #ea
      4: 3, # oof
      5: 5 # tf
      # 6: 3 # oof
  }
  
  reconstructed_image = np.vectorize(value_map.get)(reconstructed_image)
  
  # Save the array to a .npy file
  reconstructed_image = reconstructed_image.astype('uint8')
  tiff.imwrite(output_image_path, reconstructed_image, compression='lzma')
  
  # Clear up memory
  gc.collect()
  # tf.keras.backend.clear_session()
  
  return True

parser = argparse.ArgumentParser(description='QC - QUALIFAI. Type QUALIFAI.py -h for positional and optional inputs description')
parser.add_argument('--input_image_path', type=str,
                    help=' full path to the file containing the hard stitched image file in full resolution, e.g. /path/to/project_directory/hard_stitching_full_res')
parser.add_argument('--output_image_path', type=str,
                    help='full path to the file where the STS masks will be saved, e.g. path/to/project_directory/output_QC/subfolder_name/image_name.tiff')
parser.add_argument('--model_path', type=str,
                    help='full path to where the model is saved, e.g. /src/03_QC/model_20_DAPI_resnet34_currated/unetpp_best.pth')

# If you use the csv job list file comment out everything starting from here to 'Job list parser' comment

# If no arguments are provided, show help and exit
if len(sys.argv) == 1:
    parser.print_help(sys.stderr)
    sys.exit(1)

args = parser.parse_args()

input_image_path = args.input_image_path
output_image_path = args.output_image_path
model_path = args.model_path

qualifai(input_image_path = input_image_path, output_image_path = output_image_path, model_path = model_path)


# tmp_csv = pd.read_csv('/path/to/project_directory/qualifai_list_jobs.csv')
# for index, row in tmp_csv.iterrows():
#     input_image_path = row['input_image']
#     print(input_image_path)
#     output_image_path = row['output_image']
#     model_path = row['model_path']
#
#     # Assuming `hard_stitching` is defined as previously described
#     qualifai(input_image_path=input_image_path, output_image_path=output_image_path, model_path=model_path) #skip_existing
