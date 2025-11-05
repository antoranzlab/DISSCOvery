# from tifffile import imread,tifffile,imwrite
# import tifffile
import os
import sys
import numpy as np
import re
import tifffile
import xmltodict
import pandas as pd
import argparse
    
def extract_lunaphore_processed(input_directory, output_directory, slide_dictionary_file, exp_design_rounds_file, user_id, project_id):
    
    os.makedirs(output_directory, exist_ok=True)
    
    slide_dictionary = pd.read_csv(slide_dictionary_file)
  
    base_folder_name = os.path.basename(input_directory)
    slide_id = slide_dictionary[slide_dictionary['folder'] == base_folder_name]['slide_id'].tolist()[0]
    
    tiff_name = os.path.join(input_directory, base_folder_name + '.tiff')
    if not os.path.exists(tiff_name):
        tiff_name = os.path.join(input_directory, base_folder_name + '.ome.tiff')
    
    ## read exp design rounds
    exp_design_rounds = pd.read_csv(exp_design_rounds_file)
    exp_design_rounds = exp_design_rounds[exp_design_rounds['slide_id'] == slide_id] # filter for slide
    # sort to match channel list: first DAPI, then rest.

    # Open the qptiff file
    with tifffile.TiffFile(tiff_name) as tif:
        # Access the highest resolution series and its highest resolution level
        highest_res_series = max(tif.series, key=lambda s: s.shape[1] * s.shape[2])  # Assuming shape is (channels, height, width)
        highest_level = highest_res_series.levels[0]
        
        ome_metadata = tif.ome_metadata
        # Parse the OME-XML metadata
        metadata_dict = xmltodict.parse(ome_metadata)
        # Extract channel information
        channels_info = metadata_dict['OME']['Image']['Pixels']['Channel']
        
        # Create a list to store channel details
        channels_list = []
        
        # If there are multiple channels, channels_info will be a list
        if isinstance(channels_info, list):
            for channel in channels_info:
                channel_details = {
                    'ID': channel['@ID'],
                    'marker_name': channel.get('@Name', 'N/A'),
                    'SamplesPerPixel': channel.get('@SamplesPerPixel', 'N/A'),
                    'Color': channel.get('@Color', 'N/A')
                }
                channels_list.append(channel_details)
        
        # Convert the list of channel details to a DataFrame
        channels_df = pd.DataFrame(channels_list)
        
        ## matching needs to be done by marker_name. However,
        ## in instances with multiple matches (TRITC, CY5, etc.), 
        ## the matching will be done in order.
        
        # Add a temporary column that counts each occurrence of marker_name cumulatively
        channels_df['marker_name_count'] = channels_df.groupby('marker_name').cumcount()
        
        # Do the same for exp_design_rounds
        exp_design_rounds['marker_name_count'] = exp_design_rounds.groupby('marker_name').cumcount()
        
        # Perform a left join on marker name and count
        channels_df = channels_df.merge(exp_design_rounds, left_on=['marker_name', 'marker_name_count'], right_on=['marker_name', 'marker_name_count'])
        
        # Drop helper column if no longer needed
        channels_df.drop(columns='marker_name_count', inplace=True)
        
        # channels_df = pd.concat([channels_df, exp_design_rounds], axis = 1)
        # channels_df2 = channels_df.merge(exp_design_rounds, left_on='marker_name', right_on='marker_name')
        
        # csv_filename = os.path.join(output_path, file.replace('.tiff', '.csv'))
        # channels_df.to_csv(csv_filename, index = False)
        
        print(f'Highest resolution level shape: {highest_level.shape}')
        
        # Process each channel
        for channel_index in range(highest_level.shape[0]):
            image = highest_level[channel_index].asarray()
            image = image << 4 # transform the 12-bit effective to 16-bit.
            tmp_meta = channels_df[channels_df['ID'] == ('Channel:' + str(channel_index))]
            new_folder_name = slide_id + '_' + tmp_meta['round_number'].tolist()[0] + '_' + 'V01' + '_' + project_id + '_' + user_id
            os.makedirs(os.path.join(output_directory, new_folder_name), exist_ok=True)
            tile_filename = new_folder_name + '_' + tmp_meta['channel_id'].tolist()[0] + '.tiff'
            tifffile.imwrite(os.path.join(output_directory, new_folder_name, tile_filename), image, photometric='minisblack', dtype=image.dtype, compression='lzma')

parser = argparse.ArgumentParser(description='extract channels from comet .ome.tiff. type extract_lunaphore_ometiff_processed.py -h for positional and optional inputs description')
parser.add_argument('--input_directory', type=str,
                    help='Path to input files (dir). Example: /path/to/data_files')
parser.add_argument('--output_directory', type=str,
                    help='Path to output tiles (dir). Example: /path/to/project_directory/output_tiles_tiffs')
parser.add_argument('--slide_dictionary_file', type=str,
                    help='Path to input csv with slide names (csv). Example: /path/to/project_directory/experimental_design/exp_design_slides.csv')
parser.add_argument('--exp_design_rounds_file', type=str,
                    help='Path to experimental design file rounds (csv). Example: /path/to/project_directory/experimental_design/exp_design_rounds.csv')
parser.add_argument('--user_id', type=str,
                    help='User identifier (str). Example: JM')
parser.add_argument('--project_id', type=str,
                    help='Project identifier (str). Example: PROJECT_COMET')

# If no arguments are provided, show help and exit
if len(sys.argv) == 1:
    parser.print_help(sys.stderr)
    sys.exit(1)

args = parser.parse_args()

input_directory = args.input_directory
output_directory = args.output_directory
slide_dictionary_file = args.slide_dictionary_file
exp_design_rounds_file = args.exp_design_rounds_file
user_id = args.user_id
project_id = args.project_id

extract_lunaphore_processed(input_directory=input_directory, output_directory=output_directory, slide_dictionary_file=slide_dictionary_file, exp_design_rounds_file=exp_design_rounds_file, user_id=user_id, project_id=project_id)
