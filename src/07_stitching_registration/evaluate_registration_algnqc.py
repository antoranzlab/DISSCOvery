import numpy as np
import sys
# from PIL import Image
import tifffile
from tensorflow.keras.layers import TFSMLayer
from tensorflow.keras.models import load_model
import pandas as pd
import argparse
import matplotlib.pyplot as plt
from tensorflow.keras.preprocessing.image import img_to_array, load_img
import gc
import os
from patchify import patchify, unpatchify
import plotly.graph_objects as go

gc.collect()

# Increase the maximum allowed image size
# Image.MAX_IMAGE_PIXELS = None  # Removes the limit entirely

def range_x1_q(image, q):
    non_zero_pixels = image[image > 0]
    q_high = np.quantile(non_zero_pixels, q)
    q_low = np.quantile(non_zero_pixels, 1 - q)
    image = (image - q_low) / (q_high - q_low)
    image = np.clip(image, 0, 1)
    return image

def evaluate_registration(path_ref_image, path_query_image, path_model, path_csv, path_html, path_json):
    print(f'### path ref image: {path_ref_image} ###')
    print(f'### path query image: {path_query_image} ###')
    print(f'### path model: {path_model} ###')
    print(f'### path csv: {path_csv} ###')
    print(f'### path html: {path_html} ###')
    print(f'### path json: {path_json} ###')
    
    # Check if the directory for the csv file exists, create if not
    csv_dir = os.path.dirname(path_csv)
    if not os.path.exists(csv_dir):
        print(f'### creating folder: {csv_dir} ###')
        os.makedirs(csv_dir, exist_ok=True)
        
    # Check if the directory for the HTML file exists, create if not
    html_dir = os.path.dirname(path_html)
    if not os.path.exists(html_dir):
        print(f'### creating folder: {html_dir} ###')
        os.makedirs(html_dir, exist_ok=True)
    
    # Check if the directory for the JSON file exists, create if not
    json_dir = os.path.dirname(path_json)
    if not os.path.exists(json_dir):
        print(f'### creating folder: {json_dir} ###')
        os.makedirs(json_dir, exist_ok=True)  
    
    # Legacy AlignQC uses RGB (reference, query, zero); the new model uses two channels.
    model_channels = 3
    # Keras model files and legacy SavedModel exports require different loaders.
    if os.path.isfile(path_model) and path_model.lower().endswith((".h5", ".hdf5", ".keras")):
        model = load_model(path_model, compile=False)
        model_channels = model.input_shape[-1]
        if model_channels not in (2, 3):
            raise ValueError(f"AlignQC expects a 2- or 3-channel model, got {model.input_shape}")
    elif os.path.isdir(path_model) and any(
        os.path.isfile(os.path.join(path_model, name))
        for name in ("saved_model.pb", "saved_model.pbtxt")
    ):
        model = TFSMLayer(path_model, call_endpoint="serving_default")
    else:
        raise ValueError(
            f"Expected an AlignQC .h5/.hdf5/.keras model file or a SavedModel directory, got: {path_model}"
        )
    
    ref_image = tifffile.imread(path_ref_image)
    if (ref_image.max()) > 0:
        ref_image = range_x1_q(ref_image, 0.99)
    
    ref_image = np.squeeze(ref_image)

    query_image = tifffile.imread(path_query_image)
    if (query_image.max()) > 0:
        query_image = range_x1_q(query_image, 0.99)
    
    query_image = np.squeeze(query_image)

    # ref/query aren't guaranteed to be the same shape -- true for MILAN (COLLAGE warps
    # both onto a shared canvas before this script runs) but not for a technology like AKOYA
    # that skips COLLAGE: each round's STS bounding box is detected independently, so the
    # "same" scan_region can crop to a slightly different size per round. Padding below is
    # computed from ref_image's shape alone and applied to both -- without reconciling shapes
    # first, a smaller query patchifies into fewer patches than ref, and indexing query's
    # patches with indices valid for ref's raises IndexError. Crop both to their common
    # top-left region so shapes always match before patchifying.
    if ref_image.shape != query_image.shape:
        min_h = min(ref_image.shape[0], query_image.shape[0])
        min_w = min(ref_image.shape[1], query_image.shape[1])
        print(f'### ref/query shape mismatch: {ref_image.shape} vs {query_image.shape} -- cropping both to common ({min_h}, {min_w}) ###')
        ref_image = ref_image[:min_h, :min_w]
        query_image = query_image[:min_h, :min_w]

    # Define patch size and step size
    patch_size = 256
    overlap_percentage = 0
    overlap = int(patch_size * overlap_percentage)
    step = patch_size - overlap
    
    # Original image dimensions
    original_height, original_width = ref_image.shape
    
    # Calculate the necessary padding for height and width
    next_multiple_height = np.ceil(original_height / patch_size) * patch_size
    next_multiple_width = np.ceil(original_width / patch_size) * patch_size
    
    # Calculate padding
    padding_height = int(next_multiple_height - original_height)
    padding_width = int(next_multiple_width - original_width)
    
    # Create a padded array
    ref_image = np.pad(ref_image, ((0, padding_height), (0, padding_width)), 'constant', constant_values=0)
    query_image = np.pad(query_image, ((0, padding_height), (0, padding_width)), 'constant', constant_values=0)
    
    image_rows = ref_image.shape[0]
    image_cols = ref_image.shape[1]
    
    # Tesselate the input image into patches
    ref_image = patchify(ref_image, (patch_size, patch_size), step=step)
    query_image = patchify(query_image, (patch_size, patch_size), step=step)
    
    patch_rows = ref_image.shape[0]
    patch_cols = ref_image.shape[1]
    
    # Flatten patch arrays for easier batch processing
    ref_image = ref_image.reshape(-1, patch_size, patch_size)
    query_image = query_image.reshape(-1, patch_size, patch_size)
    # Prepare an array to store the predictions
    
    results = []
    num_patches = ref_image.shape[0]
    batch_size = 32
    predicted_algnqc = np.zeros(len(ref_image))
    
    for i in range(0, num_patches, batch_size):
        print(i)
        batch_ref_patches = ref_image[i:(i+batch_size)]
        batch_query_patches = query_image[i:(i+batch_size)]
        
        # Check if any patch in the batch_ref_patches is all zeros
        non_zero_indices = [index for index, patch in enumerate(batch_ref_patches) if not np.all(patch == 0)]
        
        if len(non_zero_indices) == 0:
          continue
        
        filtered_ref_patches = batch_ref_patches[non_zero_indices]
        filtered_query_patches = batch_query_patches[non_zero_indices]
        
        # Create batch inputs for the model
        channels = [filtered_ref_patches, filtered_query_patches]
        if model_channels == 3:
            channels.append(np.zeros_like(filtered_ref_patches))
        batch_input = np.stack(channels, axis=-1)

        # Get scores from the model
        scores = model(batch_input.astype(np.float32), training=False)
        if isinstance(scores, dict):
            scores = list(scores.values())[0]
        scores = np.asarray(scores)
        
        # Record results with coordinates
        for j, score in enumerate(scores):
            actual_index = non_zero_indices[j]
            patch_index = i + actual_index

            predicted_algnqc[patch_index] = np.squeeze(score[0])
    
    predicted_algnqc = predicted_algnqc.reshape(patch_rows, patch_cols)
    # Convert results to DataFrame and save to CSV
    
    rows, cols = np.nonzero(predicted_algnqc) 
    values = predicted_algnqc[rows, cols]
    sparse_data = np.stack([rows, cols, values], axis=1)
    df_algnqc = pd.DataFrame(sparse_data, columns=["tmp_row", "tmp_column", "score"])
    
    # df_algnqc = pd.DataFrame(results)
    df_algnqc.to_csv(path_csv, index=False)
    
    # Ensure tmp_row and tmp_column are sorted numerically
    df_algnqc['tmp_row'] = pd.to_numeric(df_algnqc['tmp_row'])
    df_algnqc['tmp_column'] = pd.to_numeric(df_algnqc['tmp_column'])
    df_algnqc = df_algnqc.sort_values(by=['tmp_row', 'tmp_column'])
    
    # Custom color scale
    color_scale = [
        [0, 'indianred'],   # low color
        [0.5, 'gold'],      # midpoint color
        [1, 'seagreen']     # high color
    ]
    
    # Create the heatmap
    heatmap_plot = go.Figure(data=go.Heatmap(
        x=df_algnqc['tmp_column'],
        y=-df_algnqc['tmp_row'],
        z=df_algnqc['score'],
        colorscale=color_scale,
        colorbar=dict(title='AlgnQC')
    ))
    
    # Update layout to remove x-ticks and y-ticks
    heatmap_plot.update_layout(
        title=None,
        xaxis=dict(title='', tickvals=[], showticklabels=False, scaleanchor='y', scaleratio=1),  # Hide x-ticks
        yaxis=dict(title='', tickvals=[], showticklabels=False),  # Hide y-ticks
        hoverlabel=dict(bgcolor="white")
    )
    
    # Save the plot as an interactive HTML file
    heatmap_plot.write_html(path_html)
    
    # Save the JSON representation of the plot
    with open(path_json, 'w') as f:
        f.write(heatmap_plot.to_json())
    
    # # Plotting - Adjust as necessary
    # plt.imshow(df_results.pivot('tmp_row', 'tmp_column', 'score'), cmap='viridis')
    # plt.colorbar()
    # plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Evaluate registration - Algnqc. Type evaluate_registration_algnqc.py -h for positional and optional inputs description')
    parser.add_argument('--path_ref_image', type=str,
                        help=' full path to the reference image (.tiff). Example, /path/to/project_directory/output_registration_collage/BM_R01_V01_BENCHMARK_ND_S0/BM_R01_V01_BENCHMARK_ND_S0_DAPI.tiff')
    parser.add_argument('--path_query_image', type=str,
                        help=' full path to the query image (.tiff). Example, /path/to/project_directory/output_registration_collage/BM_R01_V01_BENCHMARK_ND_S0/BM_R01_V01_BENCHMARK_ND_S0_DAPI.tiff')
    parser.add_argument('--path_model', type=str,
                        help='AlignQC model: .h5/.hdf5/.keras file or legacy SavedModel directory')
    parser.add_argument('--path_csv', type=str,
                        help=' full path to the output where the AlgnQC stats will be saved. Example, /path/to/project_directory/output_registration_qc/csv/BM_S0/BM_R01_V01_BENCHMARK_ND_S0_DAPI.csv')
    parser.add_argument('--path_html', type=str,
                        help=' full path to the output where the AlgnQC stats will be saved. Example, /path/to/project_directory/output_registration_qc/html/BM_S0/BM_R01_V01_BENCHMARK_ND_S0_DAPI.html')
    parser.add_argument('--path_json', type=str,
                        help=' full path to the output where the AlgnQC stats will be saved. Example, /path/to/project_directory/output_registration_qc/json/BM_S0/BM_R01_V01_BENCHMARK_ND_S0_DAPI.json')

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    path_ref_image = args.path_ref_image
    path_query_image = args.path_query_image
    path_model = args.path_model
    path_csv = args.path_csv
    path_html = args.path_html
    path_json = args.path_json

    evaluate_registration(path_ref_image = path_ref_image, path_query_image = path_query_image, path_model = path_model, path_csv = path_csv, path_html = path_html, path_json = path_json)