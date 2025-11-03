# Load libraries
import os
import sys
import numpy as np
import tifffile as tiff
from skimage.io import imread
from patchify import patchify, unpatchify
import tensorflow as tf
import gc
import argparse
import pandas as pd
import matplotlib.pyplot as plt

gc.collect()
tf.keras.backend.clear_session()

gpus = tf.config.experimental.list_physical_devices('GPU')
if gpus:
    try:
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
    except RuntimeError as e:
        print(e)

def asinh_transform(image):
    """ Apply the asinh transformation """
    return np.arcsinh(2**16 * image)

def range_x1_q(image, q):
    """ Apply range normalization """
    non_zero_pixels = image[image > 0]
    q_high = np.quantile(non_zero_pixels, q)
    q_low = np.quantile(non_zero_pixels, 1 - q)
    image = (image - q_low) / (q_high - q_low)
    image = np.clip(image, 0, 1)
    return image


def reconstruct_from_patches(patches, image_shape, step):
    """ Reconstruct image from patches """
    reconstructed_image = np.zeros(image_shape)

    patch_height, patch_width = patches.shape[2], patches.shape[3]

    for i in range(patches.shape[0]):
        for j in range(patches.shape[1]):
            patch = patches[i, j, :, :]
            margin = int((patch.shape[0] - step)/2)
            x_start = int(margin)
            y_start = int(margin)
            x_end = int((patch.shape[0] - margin))
            y_end = int((patch.shape[0] - margin))
            valid_patch = patch[x_start:x_end, y_start:y_end]
            x_start = i * step + margin
            y_start = j * step + margin
            x_end = i * step + patch_height - margin
            y_end = j * step + patch_width - margin

            # Add the patch to the reconstructed image and increment the patch count
            reconstructed_image[x_start:x_end, y_start:y_end] = valid_patch

    return reconstructed_image

def plot_patches_and_predictions(image_patches, predictions):
    """
    Plots 16 image patches in a row and their corresponding predictions below them.

    Parameters:
    - image_patches: List or array of 16 image patches (each as a NumPy array).
    - predictions: List or array of 16 predicted images (each as a NumPy array).
    """
    assert len(image_patches) == 16 and len(predictions) == 16, "Must provide exactly 16 patches and 16 predictions"
    
    vmin, vmax = image_patches.min(), image_patches.max()  # Global intensity range

    fig, axes = plt.subplots(nrows=2, ncols=16, figsize=(20, 5))

    for i in range(16):
        # Top row: Original patches
        axes[0, i].imshow(image_patches[i], cmap='gray', vmin=vmin, vmax=vmax)
        axes[0, i].axis('off')

        # Bottom row: Predictions
        axes[1, i].imshow(predictions[i], cmap='gray', vmin=vmin, vmax=vmax)
        axes[1, i].axis('off')

    # Add row labels
    axes[0, 0].set_ylabel("Patches", fontsize=12, fontweight="bold")
    axes[1, 0].set_ylabel("Predictions", fontsize=12, fontweight="bold")

    plt.tight_layout()
    plt.show()

def generate_mask(input_image_path, output_image_path, model_path):
    
    os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
    
    # Load the model with the custom loss function
    model = tf.keras.models.load_model(model_path, compile=False)
    
    # Load and preprocess the input image
    input_image = tiff.imread(input_image_path)
    input_image = np.squeeze(input_image)
    input_image = asinh_transform(input_image)
    input_image = range_x1_q(input_image, 0.99)
    input_image = 255*input_image
    input_image = input_image.astype(np.uint8)
    input_image = input_image / 255.0
    
    # Define patch size and step size
    patch_size = 512
    overlap_percentage = 0.2
    batch_size = 16
    segmentation_threshold = 0.5
    overlap = int(patch_size * overlap_percentage)
    step = patch_size - overlap
    
    # Original image dimensions
    original_height, original_width = input_image.shape
    
    # Calculate the necessary padding for height and width
    n_step_height = np.ceil((original_height - patch_size) / step)
    n_step_width = np.ceil((original_width - patch_size) / step)
    next_multiple_height = patch_size + n_step_height * step
    next_multiple_width = patch_size + n_step_width * step
    
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
        # for i in range(input_patches.shape[0]):
            # for j in range(input_patches.shape[1]):
        
        # patch = input_patches[i, j, :, :]
        
        batch_start = batch_idx * batch_size
        batch_end = min(batch_start + batch_size, n_patches)
        
        # Access the patches in the current batch
        batch_patches = flat_patches[batch_start:batch_end]
        batch_prediction = model.predict(batch_patches)
        
        # plot_patches_and_predictions(batch_patches, batch_prediction)
        
        # Now we need to map the results back to the correct positions in the predicted_patches array
        for idx, flat_idx in enumerate(range(batch_start, batch_end)):
          # Compute row and column indices for the current patch
          row_idx = flat_idx // n_cols
          col_idx = flat_idx % n_cols
  
          # Insert the segmented result into the correct location in predicted_patches
          # predicted_patches[row_idx, col_idx, :, :, :] = qc_patch[idx]
          predicted_patches[row_idx, col_idx, :, :] = np.squeeze(batch_prediction[idx])
    
    # Reconstruct the full image from the predicted patches
    reconstructed_image = reconstruct_from_patches(predicted_patches, input_image.shape, step)
    reconstructed_image = reconstructed_image[0:original_height, 0:original_width]
    
    # Make the mask binary
    reconstructed_image[reconstructed_image > segmentation_threshold] = 1
    reconstructed_image[reconstructed_image <= segmentation_threshold] = 0
    
    reconstructed_image = 255 * reconstructed_image
    reconstructed_image = reconstructed_image.astype(np.uint8)
    
    tiff.imwrite(output_image_path, reconstructed_image, compression = 'lzma')
    
    return True



parser = argparse.ArgumentParser(description='Smart Tissue Selection - generate masks. Type STS_generate_mask.py -h for positional and optional inputs description')
parser.add_argument('--input_image_path', type=str,
                    help=' full path to the file containing the hard stitched image file, e.g. /path/to/project_directory/hard_stitching/BM_R00_V01_BENCHMARK_ND_DAPI.tiff ')
parser.add_argument('--output_image_path', type=str,
                    help='full path to the file where the STS masks will be saved, e.g. /path/to/project_directory/output_STS/masks/BM_R00_V01_BENCHMARK_ND_DAPI.tiff ')
parser.add_argument('--model_path', type=str,
                    help='full path to the directory where the uNet model is saved, e.g. models/02_uNet_simple_best.h5')


# If no arguments are provided, show help and exit
if len(sys.argv) == 1:
    parser.print_help(sys.stderr)
    sys.exit(1)

args = parser.parse_args()

input_image_path = args.input_image_path
output_image_path = args.output_image_path
model_path = args.model_path

generate_mask(input_image_path = input_image_path, output_image_path = output_image_path, model_path = model_path)