import os
import numpy as np
import re
import sys
import tifffile
import xmltodict
import pandas as pd
import argparse
import unicodedata
from concurrent.futures import ThreadPoolExecutor

def _write_channel(image, output_directory, slide_id, project_id, user_id, row):
    image = image << 4  # transform the 12-bit effective to 16-bit.
    new_folder_name = f"{slide_id}_{row['round_number']}_V01_{project_id}_{user_id}"
    os.makedirs(os.path.join(output_directory, new_folder_name), exist_ok=True)
    tile_filename = f"{new_folder_name}_{row['channel_id']}.tiff"
    tifffile.imwrite(os.path.join(output_directory, new_folder_name, tile_filename), image, photometric='minisblack', dtype=image.dtype, compression='lzma')
    return tile_filename

def normalize_folder(x):
    if pd.isna(x):
        return None
    x = str(x)
    x = unicodedata.normalize("NFKC", x)
    x = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", x)   # dash variants
    x = re.sub(r"[\u00A0\u2000-\u200B\u202F\u205F\u3000]", " ", x)       # weird spaces
    x = re.sub(r"\s+", " ", x).strip()
    return x

def extract_lunaphore_processed(input_directory, output_directory, slide_dictionary_file, exp_design_rounds_file, user_id, project_id, rounds=None, n_workers=4):
    
    os.makedirs(output_directory, exist_ok=True)
    
    slide_dictionary = pd.read_csv(slide_dictionary_file)
    slide_dictionary["folder"] = slide_dictionary["folder"].map(lambda x: normalize_folder(str(x)))
    base_folder_name = os.path.basename(input_directory)
    slide_id = slide_dictionary[slide_dictionary['folder'] == base_folder_name]['slide_id'].tolist()[0]
    
    tiff_name = os.path.join(input_directory, base_folder_name + '.tiff')
    if not os.path.exists(tiff_name):
        tiff_name = os.path.join(input_directory, base_folder_name + '.ome.tiff')
    
    ## read exp design rounds
    exp_design_rounds = pd.read_csv(exp_design_rounds_file)
    exp_design_rounds = exp_design_rounds[exp_design_rounds['slide_id'] == slide_id] # filter for slide

    # Parse OME-XML metadata for channel identity/order (tifffile header read only -- no
    # pixel data touched here, so this stays cheap regardless of how many rounds are kept).
    with tifffile.TiffFile(tiff_name) as tif:
        ome_metadata = tif.ome_metadata
        highest_res_series = max(tif.series, key=lambda s: s.shape[1] * s.shape[2])
        full_shape = highest_res_series.levels[0].shape

    metadata_dict = xmltodict.parse(ome_metadata)
    channels_info = metadata_dict['OME']['Image']['Pixels']['Channel']

    channels_list = []
    if isinstance(channels_info, list):
        for channel in channels_info:
            channel_details = {
                'ID': channel['@ID'],
                'marker_name': channel.get('@Name', 'N/A'),
                'SamplesPerPixel': channel.get('@SamplesPerPixel', 'N/A'),
                'Color': channel.get('@Color', 'N/A')
            }
            channels_list.append(channel_details)

    channels_df = pd.DataFrame(channels_list)

    ## matching needs to be done by marker_name. However,
    ## in instances with multiple matches (TRITC, CY5, etc.),
    ## the matching will be done in order.
    channels_df['marker_name_count'] = channels_df.groupby('marker_name').cumcount()
    exp_design_rounds['marker_name_count'] = exp_design_rounds.groupby('marker_name').cumcount()

    # Count repeated names against the COMPLETE acquisition design. Filtering rounds
    # before cumcount shifts repeated DAPI/AF names onto the wrong source pages when
    # selecting nonconsecutive rounds (e.g. R01/R03/R04).
    channels_df = channels_df.merge(exp_design_rounds, left_on=['marker_name', 'marker_name_count'], right_on=['marker_name', 'marker_name_count'])
    channels_df.drop(columns='marker_name_count', inplace=True)
    if rounds is not None:
        channels_df = channels_df[channels_df['round_number'].isin(rounds)]
        print(f'Restricting extraction to rounds: {sorted(set(rounds))}')

    print(f'Highest resolution level shape: {full_shape}')
    print(f'Extracting {len(channels_df)} of {full_shape[0]} channels')

    # Read channels sequentially through one shared handle -- concurrent .asarray() calls
    # on separate TiffFile handles against the same large OME-TIFF (each worker opening its
    # own handle on the same physical file) was silently corrupting some reads, returning an
    # empty/scalar array for the page instead of raising. Confirmed by reproducing individual
    # page reads in isolation (always correct) vs under the previous ThreadPoolExecutor (some
    # channels came back with shape () and dtype float64).
    #
    # Reads are sequential, but each channel's write (compression + I/O, which doesn't touch
    # the shared source file) is handed off to a bounded pool so reads don't stall on
    # compression. Backpressure (blocking once n_workers writes are in flight, rather than
    # firing off every submit() immediately) caps live pixel data at n_workers channels --
    # ThreadPoolExecutor's own queue is unbounded, so without this a slow write side (lzma on
    # ~3.75GB arrays at 44643x44643 uint16) would let reads race ahead and reproduce the same
    # whole-run-in-memory footprint this is meant to avoid.
    with tifffile.TiffFile(tiff_name) as tif, ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = []
        for _, row in channels_df.iterrows():
            channel_index = int(row['ID'].split(':')[1])
            image = tif.series[0].pages[channel_index].asarray()
            futures.append(executor.submit(_write_channel, image, output_directory, slide_id, project_id, user_id, row))
            if len(futures) >= n_workers:
                print(f'  wrote {futures.pop(0).result()}')
        for future in futures:
            print(f'  wrote {future.result()}')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='extract channels from comet .ome.tiff. type extract_lunaphore_ometiff_processed.py -h for positional and optional inputs description')
    parser.add_argument('--input_directory', type=str,
                        help='Path to input files (dir). Example: /path/to/data_files')
    parser.add_argument('--output_directory', type=str,
                        help='Path to output tiles (dir). Example: /path/to/project_directory/output_tiles_tiffs')
    parser.add_argument('--slide_dictionary_file', type=str,
                        help='Path to input csv with slide names (csv). Example: /path/to/project_directory/experimental_design/exp_design_slides.csv')
    parser.add_argument('--exp_design_rounds_file', type=str,
                        help='Complete acquisition design for the rounds (csv), including unselected rounds; use --rounds to restrict extraction.')
    parser.add_argument('--user_id', type=str,
                        help='User identifier (str). Example: JM')
    parser.add_argument('--project_id', type=str,
                        help='Project identifier (str). Example: COMETP')
    parser.add_argument('--rounds', type=str, default=None,
                        help='Optional comma-separated round_number list to restrict extraction to (e.g. "R01,R02"). Default: all rounds.')
    parser.add_argument('--n_workers', type=int, default=4,
                        help='Maximum pending parallel channel writes; reads are sequential (default 4).')

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
    rounds = args.rounds.split(',') if args.rounds else None
    n_workers = args.n_workers

    extract_lunaphore_processed(input_directory=input_directory, output_directory=output_directory, slide_dictionary_file=slide_dictionary_file, exp_design_rounds_file=exp_design_rounds_file, user_id=user_id, project_id=project_id, rounds=rounds, n_workers=n_workers)
