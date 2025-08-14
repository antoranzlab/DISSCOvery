import aicspylibczi
import numpy as np
import pandas as pd
import argparse
import xml.etree.ElementTree as ET
import os

def find_czi_files(directory):
    """Find all .czi files within the directory and its subdirectories."""
    czi_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.czi'):
                czi_files.append(os.path.join(root, file))
    return czi_files

def read_czi_from_meta(imfilename):
    czi = aicspylibczi.CziFile(imfilename)
    metadata_root = czi.meta
    return(metadata_root)

def get_unique_channel_details(metadata_root):
    channels = metadata_root.findall('.//Channels/Channel')
    unique_channels = {}
    for channel in channels:
        channel_id = channel.attrib.get('Id')
        if channel_id and channel_id not in unique_channels:
            unique_channels[channel_id] = channel.attrib.get('Name')
    
    # Convert the dictionary to a list of dictionaries
    unique_channel_details = [{'channel_id': name, 'channel_number': int(id.replace('Channel:', ''))} for id, name in unique_channels.items()]
    df_channels = pd.DataFrame(unique_channel_details)
    return df_channels

def parse_metadata(directory, output_csv_channels, output_csv_slides):
    # List all entries in the directory given by "path"
    czi_files = find_czi_files(directory)
    df_meta = pd.DataFrame()
    
    for index, czi_file in enumerate(czi_files):
        # Print progress
        print(f'{index + 1} out of {len(czi_files)}')
        
        tmp_meta = read_czi_from_meta(czi_file)
        df_channels = get_unique_channel_details(tmp_meta)
        df_channels['czi_file'] = czi_file
        # Append to the main DataFrame
        df_meta = pd.concat([df_meta, df_channels], ignore_index=True)
    
    # Create a new column with the basename of each file path
    df_meta['basename'] = df_meta['czi_file'].apply(lambda x: os.path.basename(x.replace('.czi', '')))
    # Split the basename into multiple columns
    df_meta[['slide_id', 'round_number', 'version_id', 'project_id', 'user_id']] = df_meta['basename'].str.split('_', expand=True)
    # Substitute AF_FITC for AF
    df_meta['channel_id'] = df_meta['channel_id'].replace('AF_FITC', 'AF')
    df_meta['channel_id'] = df_meta['channel_id'].replace('FITC_AF', 'AF')
    # Save to csv
    os.makedirs(os.path.dirname(output_csv_channels), exist_ok=True)
    df_meta.to_csv(output_csv_channels, index=False)
    
    df_slides = pd.DataFrame(df_meta['slide_id'].unique(), columns=['slide_id'])
    df_slides['folder'] = df_slides['slide_id']
    # Save to csv
    os.makedirs(os.path.dirname(output_csv_slides), exist_ok=True)
    df_slides.to_csv(output_csv_slides, index=False)

parser = argparse.ArgumentParser(description='CZIReader - extract metadata. type czi_extract_metadata.py -h for positional and optional inputs description')
parser.add_argument('directory', type=str,
                    help=' parent directory where the czi files are stored e.g. /media/Share2/benchmarking_experiment_MILAN/benchmarking_milan ')
parser.add_argument('output_csv_channels', type=str,
                    help='path to csv where the channel metadata will be stored e.g. /media/Share1/bencharked_datasets/P10_benchmarking_MILAN/experimental_design/channel_names.csv')
parser.add_argument('output_csv_slides', type=str,
                    help='path to csv where the channel metadata will be stored e.g. /media/Share1/bencharked_datasets/P10_benchmarking_MILAN/experimental_design/exp_design_slides.csv')
                    
args = parser.parse_args()

directory = args.directory #'/media/Share2/benchmarking_experiment_MILAN/benchmarking_milan'
output_csv_channels = args.output_csv_channels #'/media/Share1/bencharked_datasets/P10_benchmarking_MILAN/experimental_design/channel_names.csv'
output_csv_slides = args.output_csv_slides #'/media/Share1/bencharked_datasets/P10_benchmarking_MILAN/experimental_design/exp_design_slides.csv'

parse_metadata(directory=directory, output_csv_channels=output_csv_channels, output_csv_slides=output_csv_slides)
