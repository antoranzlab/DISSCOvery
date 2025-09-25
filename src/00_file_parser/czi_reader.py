import aicspylibczi
import numpy as np
import tifffile
import pandas as pd
import argparse
import xml.etree.ElementTree as ET
import os
import sys

def metadata_to_dict(string_xml):
    """Arrange xml metadata information in a dictionary"""
    root = ET.fromstring(string_xml)
    meta_dict = {}
    for info in root.iter():
        if info.text:
            meta_dict[info.tag] = info.text
    return meta_dict

def process_metadata(metadata, x_scaling, y_scaling, imbasename, ch_dict):
    """Process metadata for each tile."""
    metadata_df = []
    for dims_tile, meta_tile in metadata:
        meta_tile = metadata_to_dict(meta_tile)
        channel_id = ch_dict.get(dims_tile['C'], f"UnknownChannel_{dims_tile['C']}")
        meta_tile['tile_filename'] = f"{imbasename}_S{dims_tile['S']}M{dims_tile['M']}_{channel_id}.tiff"
        meta_tile['ImagePixelSize'] = f"{x_scaling},{y_scaling}"
        meta_tile.update(dims_tile)
        metadata_df.append(meta_tile)
    return pd.DataFrame(metadata_df)

def extract_tiles_from_czi(imfilename, channel_names_dictionary, output_folder):
    """Main function that processes provided data and creates tiff files"""
    ## create output directory
    os.makedirs(output_folder, exist_ok=True)
    
    ## read czi
    tmp_czi = aicspylibczi.CziFile(imfilename)
    metadata_root = tmp_czi.meta
        
    ## extract tile sizes
    x_scaling = metadata_root.find(".//Distance[@Id='X']/Value").text
    y_scaling = metadata_root.find(".//Distance[@Id='Y']/Value").text
        
    # convert to tenths of micrometers (from meters)
    x_scaling = float(x_scaling) * 1e7
    y_scaling = float(y_scaling) * 1e7
        
    imbasename = os.path.basename(imfilename).replace('.czi', '')
    metadata_filename = f"{imbasename}_meta.csv"

    df_channel_names = pd.read_csv(channel_names_dictionary)
    df_channel_names = df_channel_names[df_channel_names['czi_file'] == imfilename] 

    # Create the dictionary from the DataFrame
    ch_dict = df_channel_names.set_index('channel_number')['channel_id'].to_dict()
    
    metadata = tmp_czi.read_subblock_metadata()
    metadata_df = process_metadata(metadata, x_scaling, y_scaling, imbasename, ch_dict)
    metadata_df.to_csv(os.path.join(output_folder, metadata_filename), index=False)

    for ind, tile_meta in metadata_df.iterrows():
        tile = tmp_czi.read_image(S = int(tile_meta['S']), C = int(tile_meta['C']), M = int(tile_meta['M']))[0]
        tile = np.squeeze(tile)
        tifffile.imwrite(os.path.join(output_folder, tile_meta['tile_filename']), tile, compression='lzma', dtype=tile.dtype)

        tile = np.squeeze(tile)
        tifffile.imwrite(os.path.join(output_folder, tile_meta['tile_filename']), tile, compression='lzma', dtype=tile.dtype)
    
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='CZIReader. type czi_reader.py -h for positional and optional inputs description')
    parser.add_argument('--imfilename', type=str,
                        help=' full path to the czi. file e.g. /path/to/raw_data/subfolder/czi_file.czi ')
    parser.add_argument('--channel_names_dictionary', type=str,
                        help='path to csv where the channel dictionary has been stored. e.g. /path/to/project_directory/experimental_design/channel_names.csv ')
    parser.add_argument('--output_folder', type=str,
                        help='output directory where the tiles and metadata will be stored. e.g. indicate scene number to read e.g. /path/to/project_directory/output_tiles_tiffs')

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()


    imfilename = args.imfilename # Example: /path/to/raw_data/subfolder/czi_file.czi
    channel_names_dictionary = args.channel_names_dictionary # Example: /path/to/project_directory/experimental_design/channel_names.csv
    output_folder = args.output_folder # Example: /path/to/project_directory/output_tiles_tiffs/BM_R01_V02_BENCHMARK_ND

    extract_tiles_from_czi(imfilename=imfilename, channel_names_dictionary=channel_names_dictionary, output_folder=output_folder)
