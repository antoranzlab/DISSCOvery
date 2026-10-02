import argparse
import os
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor

import czifile
import numpy as np
import pandas as pd
import tifffile

def metadata_to_dict(string_xml):
    # Arrange xml metadata information in a dictionary. Skips whitespace-only text (some
    # CZI metadata has doubly-nested wrapper elements, e.g. <ImageScaling><ImageScaling>...,
    # whose outer tag has only indentation whitespace as its own .text) -- without this,
    # those wrapper tags show up as junk columns full of '\n  '.
    root = ET.fromstring(string_xml)
    meta_dict = {}
    for info in root.iter():
        if info.text and info.text.strip():
            meta_dict[info.tag] = info.text
    return meta_dict

def process_metadata(subblock_metadata, x_scaling, y_scaling, imbasename, ch_dict):
    # Process metadata for each tile
    metadata_df = []
    for dims_tile, meta_tile in subblock_metadata:
        meta_tile = metadata_to_dict(meta_tile)
        channel_id = ch_dict.get(dims_tile['C'], f"UnknownChannel_{dims_tile['C']}")
        meta_tile['tile_filename'] = f"{imbasename}_S{dims_tile['S']}M{dims_tile['M']}_{channel_id}.tiff"
        meta_tile['ImagePixelSize'] = f"{x_scaling},{y_scaling}"
        meta_tile.update(dims_tile)
        metadata_df.append(meta_tile)
    return pd.DataFrame(metadata_df)

def _read_subblock_directory(imfilename):
    # (S, C, M, raw metadata XML) for every subblock, plus an (S, C, M) -> directory index
    # lookup for _write_tile below. Read via czifile (BSD-3-Clause; replaces
    # aicspylibczi/bioio-czi, both GPL-3.0-or-later -- see project memory for the license
    # audit). scene_index/mosaic_index confirmed to match aicspylibczi's own S/M numbering
    # exactly on real data (same tile, same pixels, same filename).
    czi = czifile.CziFile(imfilename)
    entries = []
    index_map = {}
    for idx, e in enumerate(czi.filtered_subblock_directory):
        channel = dict(zip(e.dims, e.start)).get('C', 0)
        dims_tile = {'C': channel, 'M': e.mosaic_index, 'S': e.scene_index}
        xml_str = e.read_segment_data(czi).metadata(asdict=False)
        entries.append((dims_tile, xml_str))
        index_map[(dims_tile['S'], dims_tile['C'], dims_tile['M'])] = idx
    czi.close()
    return entries, index_map

def _write_tile(imfilename, subblock_index, output_path):
    # Each worker reopens the file (cheap: opening is near-instant/lazy) rather than sharing
    # a handle across processes. Process-based, not thread-based: imagecodecs' JPEG-XR
    # decoder is not thread-safe (confirmed: real, reproducible segfault under
    # ThreadPoolExecutor on real CZI data; fine sequentially or across separate processes).
    czi = czifile.CziFile(imfilename)
    entry = czi.filtered_subblock_directory[subblock_index]
    tile = np.squeeze(np.asarray(entry.asimage(czi).asarray()))
    czi.close()
    tifffile.imwrite(output_path, tile, compression="lzma", dtype=tile.dtype)

def extract_tiles_from_czi(imfilename, channel_names_dictionary, output_folder, n_workers=None):
    os.makedirs(output_folder, exist_ok=True)
    imfilename = os.path.normpath(imfilename)

    czi = czifile.CziFile(imfilename)
    x_scaling, y_scaling = czi.metadata(asdict=True)['ImageDocument']['Metadata']['ImageScaling']['ImagePixelSize']
    czi.close()

    imbasename = os.path.basename(imfilename).replace(".czi", "")
    metadata_filename = f"{imbasename}_meta.csv"

    df_channel_names = pd.read_csv(channel_names_dictionary)
    df_channel_names = df_channel_names[df_channel_names["czi_file"] == imfilename]
    ch_dict = df_channel_names.set_index("channel_number")["channel_id"].to_dict()

    subblock_metadata, index_map = _read_subblock_directory(imfilename)
    metadata_df = process_metadata(subblock_metadata, x_scaling, y_scaling, imbasename, ch_dict)
    metadata_df.to_csv(os.path.join(output_folder, metadata_filename), index=False)

    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = []
        for _, tile_meta in metadata_df.iterrows():
            output_path = os.path.join(output_folder, tile_meta["tile_filename"])
            subblock_index = index_map[(tile_meta["S"], tile_meta["C"], tile_meta["M"])]
            futures.append(pool.submit(_write_tile, imfilename, subblock_index, output_path))
        for future in futures:
            future.result()

    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='CZIReader. type czi_reader.py -h for positional and optional inputs description')
    parser.add_argument('--imfilename', type=str,
                        help=' full path to the czi. file e.g. /path/to/raw_data/subfolder/czi_file.czi ')
    parser.add_argument('--channel_names_dictionary', type=str,
                        help='path to csv where the channel dictionary has been stored. e.g. /path/to/project_directory/experimental_design/channel_names.csv ')
    parser.add_argument('--output_folder', type=str,
                        help='output directory where the tiles and metadata will be stored. e.g. indicate scene number to read e.g. /path/to/project_directory/output_tiles_tiffs')
    parser.add_argument('--n_workers', type=int, default=5,
                        help='number of processes used to read/write tiles concurrently. Defaults to 5')

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    imfilename = args.imfilename # Example: /path/to/raw_data/subfolder/czi_file.czi
    channel_names_dictionary = args.channel_names_dictionary # Example: /path/to/project_directory/experimental_design/channel_names.csv
    output_folder = args.output_folder # Example: /path/to/project_directory/output_tiles_tiffs/BM_R01_V02_BENCHMARK_ND
    n_workers = args.n_workers

    extract_tiles_from_czi(imfilename=imfilename, channel_names_dictionary=channel_names_dictionary, output_folder=output_folder, n_workers=n_workers)
