import tifffile
import os
import numpy as np
import re
import sys
import pandas as pd
import argparse

def extract_tiles(input_path, output_folder, project_id, user_id, input_slide_dictionary, exp_design_rounds_file):
    print(f"### input path: {input_path} ###")
    print(f"### output folder: {output_folder} ###")
    print(f"### project identifier: {project_id} ###")
    print(f"### user identifier: {user_id} ###")
    print(f"### slide dictionary: {input_slide_dictionary} ###")
    print(f"### experimental design rounds: {exp_design_rounds_file} ###")
    
    tmp_files = [f for f in os.listdir(os.path.join(input_path, 'raw')) if re.match(r'.*\.qptiff', f)]
    tmp_files = [file for file in tmp_files if not re.search(r'\.intermediate\.qptiff$', file)]
    tmp_files = [file for file in tmp_files if not re.search(r'\.qptiff\.intermediate$', file)]
    
    os.makedirs(output_folder, exist_ok = True)
    
    exp_design_slides = pd.read_csv(input_slide_dictionary)
    exp_design_rounds = pd.read_csv(exp_design_rounds_file)
    
    for imfilename in tmp_files:
      print(imfilename)
      
      # Perform partial match
      matched_slide_id = None
      for index, row in exp_design_slides.iterrows():
          if row['folder'] in imfilename:
              matched_slide_id = row['slide_id']
              break
      
      cycle_id = 'R' + str(int(imfilename.replace(row['folder'] + '_Cycle', '').replace('.raw.qptiff', '').replace('.qptiff.raw', '')) + 1).zfill(2)
      new_name = matched_slide_id + '_' + cycle_id + '_V01_' + project_id + '_' + user_id
      
      os.makedirs(os.path.join(output_folder, new_name), exist_ok = True)
      
      qptiff_path = os.path.join(input_path, 'raw', imfilename)
      
      # Open the qptiff file
      with tifffile.TiffFile(qptiff_path) as tif:
        # Access the highest resolution series and its highest resolution level
        highest_res_series = max(tif.series, key=lambda s: s.shape[1] * s.shape[2])  # Assuming shape is (channels, height, width)
        highest_level = highest_res_series.levels[0]

        # Tile dimensions
        tile_width, tile_height = 960, 720
        
        print(f'Highest resolution level shape: {highest_level.shape}')
        
        image = highest_level.asarray()
        
        # Step 1: Create an empty DataFrame with predefined column names
        columns = ['C', 'Frame', 'ImagePixelSize', 'M', 'S', 'StageXPosition', 'StageYPosition', 'ValidBitsPerPixel', 'tile_filename']
        df_metadata = pd.DataFrame(columns=columns)
        # Process each channel
        
        for channel_index in range(highest_level.shape[0]):
            # Calculate number of tiles in each dimension
            
            num_tiles_x = highest_level.shape[2] // tile_width
            num_tiles_y = highest_level.shape[1] // tile_height
            
            m_index = 0
            # Iterate over each tile position
            for ty in range(num_tiles_y):
                for tx in range(num_tiles_x):
                    # Define the slice for the current tile
                    x_start = tx * tile_width
                    x_end = x_start + tile_width
                    y_start = ty * tile_height
                    y_end = y_start + tile_height
    
                    # Extract the tile from the image array
                    tile = image[channel_index, y_start:y_end, x_start:x_end]
                    
                    tmp_row = exp_design_rounds[exp_design_rounds['round_number'] == cycle_id]
                    tmp_row = tmp_row[tmp_row['channel_number'] == channel_index]
                    
                    if 'pixel_size' in tmp_row.columns:
                        px_size = tmp_row['pixel_size'].values[0]
                    else:
                        px_size = 0.5
                    
                    tile_name = new_name + '_S0M' + str(m_index) + '_' + tmp_row['channel_id'].values[0] + '.tiff'
                    
                    tmp_metadata = {'C': channel_index, 
                    'Frame': '4,4,' + str(tile_width) + ',' + str(tile_height),
                    'ImagePixelSize': str(10*px_size) + ',' + str(10*px_size),
                    'M': m_index,
                    'S': '0',
                    'StageXPosition': str(((x_start + x_end)/2) * px_size),
                    'StageYPosition': str(((y_start + y_end)/2) * px_size),
                    'ValidBitsPerPixel': 16,
                    'tile_filename': tile_name}
                    
                    df_metadata = pd.concat([df_metadata, pd.DataFrame([tmp_metadata])], ignore_index=True)
                    
                    # tifffile.imwrite(tile_filename, tile)
                    tifffile.imwrite(os.path.join(output_folder, new_name, tile_name), tile, compression='lzma', dtype = tile.dtype)
                    
                    m_index = m_index + 1
      
      # output_path_csv = new_name + '_meta.csv'
      output_path_csv = new_name + '.csv'
      df_metadata.to_csv(os.path.join(output_folder, new_name, output_path_csv), index=False)

parser = argparse.ArgumentParser(description='Extract tiles qptiff Akoya. Type extract_tiles_qptiff_akoya.py -h for positional and optional inputs description')
parser.add_argument('--input_path', type=str,
                    help=' full path to the input folder (directory). For example, /media/Share2/benchmarking_experiment_Akoya/20240201_TMA_francesca_Scan1 ')
parser.add_argument('--output_folder', type=str,
                    help='output folder (directory). For example, /media/Share1/bencharked_datasets/P11_benchmarking_AKOYA/output_tiles_tiffs ')
parser.add_argument('--project_id', type=str,
                    help='project identifier (character). For example, AkoyaBmark ')
parser.add_argument('--user_id', type=str,
                    help='user identifier (character). For example, JC ')
parser.add_argument('--input_slide_dictionary', type=str,
                    help='full path to the dictionary for the slides (.csv). For example, /media/Share1/bencharked_datasets/P11_benchmarking_AKOYA/experimental_design/exp_design_slides.csv ')
parser.add_argument('--exp_design_rounds_file', type=str,
                    help='full path to the dictionary for the rounds (.csv). For example, /media/Share1/bencharked_datasets/P11_benchmarking_AKOYA/experimental_design/exp_design_rounds.csv')

args = parser.parse_args()

input_path = args.input_path 
output_folder = args.output_folder 
project_id = args.project_id 
user_id = args.user_id 
input_slide_dictionary = args.input_slide_dictionary 
exp_design_rounds_file = args.exp_design_rounds_file

extract_tiles(input_path=input_path, output_folder=output_folder, project_id=project_id, user_id=user_id, input_slide_dictionary=input_slide_dictionary, exp_design_rounds_file=exp_design_rounds_file)