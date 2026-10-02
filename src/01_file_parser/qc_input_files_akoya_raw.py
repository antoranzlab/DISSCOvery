import tifffile
import os
import numpy as np
import re
import pandas as pd
import json
import argparse
import sys

def process_metadata(path_to_json):
    # Load JSON data
    with open(path_to_json, 'r') as f:
        tmp_data = json.load(f)
        try:
            tmp_resolution = tmp_data['resolution']
        except KeyError:
            tmp_resolution = 0.5  # default in microns per pixel
        
        all_markers = []
        # Process each well and its items
        for well in tmp_data['wells']:
            well_name = well['wellName']
            items = well.get('items', [])
            for k, item in enumerate(items):
                marker_info = {
                    'well_name': well_name,
                    'marker_id': item['markerName'],
                    'channel_id': item['channel'],
                    'channel_number': k,  # Python uses 0-based indexing
                }
                all_markers.append(marker_info)
        
        # Convert to DataFrame
        tmp_markers = pd.DataFrame(all_markers)
        tmp_markers['pixel_size'] = tmp_resolution
        
        # Assign round numbers
        unique_wells = tmp_markers['well_name'].unique()
        round_numbers = {well: f"R{str(i+1).zfill(2)}" for i, well in enumerate(unique_wells)}
        tmp_markers['round_number'] = tmp_markers['well_name'].map(round_numbers)
        
        # Replace '--' with 'AF'
        tmp_markers['marker_id'] = tmp_markers['marker_id'].replace('--', 'AF')
        
        # Add QC_include column
        tmp_markers['QC_include'] = 1
        
    return tmp_markers

def qc_akoya_input_raw(input_path, output_txt):
    print(f"### input path raw data: {input_path} ###")
    print(f"### output path qc report (txt): {output_txt} ###")

    output_dir = os.path.dirname(output_txt)
    if not os.path.exists(output_dir):
        print(f"### creating folder: {output_dir} ###")
        os.makedirs(output_dir, exist_ok=True)

    # listing folders in parent directory. Each folder corresponds to a different slide.
    tmp_folders = [f for f in os.listdir(input_path) if os.path.isdir(os.path.join(input_path, f))]

    # Check1: The .xpd jobfile exists for all slides
    df_check1 = pd.DataFrame(columns=["folder", "xpd_file"])
    df_check3 = pd.DataFrame(columns=["folder", "raw_folder_qc"])
    for folder in tmp_folders:
        xpd_files = [f for f in os.listdir(os.path.join(input_path, folder)) if f.endswith(".xpd")]
        xpd_files = xpd_files[0] if xpd_files else "the file does not exist"
        raw_directory = os.path.isdir(os.path.join(input_path, folder, "raw"))
        if raw_directory:
            qptiff_files = [f for f in os.listdir(os.path.join(input_path, folder, 'raw')) if f.endswith(".qptiff")]
            if(len(qptiff_files) == 0):
                qptiff_files = [f for f in os.listdir(os.path.join(input_path, folder, 'raw')) if f.endswith(".qptiff.raw")]
            
            raw_directory = len(qptiff_files) > 0
        
        df_check1 = pd.concat([df_check1, pd.DataFrame({"folder": [folder], "xpd_file": [xpd_files]})], ignore_index=True)
        df_check3 = pd.concat([df_check3, pd.DataFrame({"folder": [folder], "raw_folder_qc": [raw_directory]})], ignore_index=True)
    
    bad_qc = df_check1[df_check1["xpd_file"] == "the file does not exist"]
    if not bad_qc.empty:
        message = (f"Check1 - xpd file QC: NOT PASSED.\nCondition: xpd file not found:\n" + "\n".join(bad_qc["folder"]))
        with open(output_txt, "w") as f:
            f.write(message)
    else:
        message = "Check1 - xpd file QC: PASSED.\n"
    
    # Tabulate metadata
    df_metadata = pd.DataFrame(columns=['well_name', 'marker_id', 'channel_id', 'channel_number', 'pixel_size',
       'round_number', 'QC_include', 'folder'])
    for folder in tmp_folders:
        xpd_files = [f for f in os.listdir(os.path.join(input_path, folder)) if f.endswith(".xpd")]
        xpd_file = xpd_files[0]
        tmp_metadata = process_metadata(os.path.join(input_path, folder, xpd_file))
        tmp_metadata['folder'] = folder
        df_metadata = pd.concat([df_metadata, tmp_metadata], ignore_index=True)
    
    valid_channels = {'DAPI', 'ATTO550', 'CY5', 'AF750'}

    ## Check2: if all values in the FluorescenceChannel column are valid
    df_check2 = df_metadata[~df_metadata["channel_id"].isin(valid_channels)]

    if not df_check2.empty:
        message += (
            f"Check2 - metadata channel names QC: NOT PASSED.\nCondition: channel names not matching expectations:.\n"
            + "\n".join(df_check2["folder"].unique())
        )
        with open(output_txt, "w") as f:
            f.write(message)
    else:
        message += "Check2 - metadata channel names QC: PASSED.\n"

    ## Check3: The raw data exists and has qptiff files inside
    bad_qc = df_check3[df_check3["raw_folder_qc"] == False]
    if not bad_qc.empty:
        message += (f"Check3 - raw data QC: NOT PASSED.\nCondition: raw data not found:\n" + "\n".join(bad_qc["folder"]))
        with open(output_txt, "w") as f:
            f.write(message)
    else:
        message += "Check3 - raw data QC: PASSED.\n"
    
    # Tabulate and list all the qptiff files per folder
    df_files = pd.DataFrame(columns=["folder", "qptiff_file"])
    for folder in tmp_folders:
        qptiff_files = [f for f in os.listdir(os.path.join(input_path, folder, 'raw')) if re.match(r'.*\.qptiff', f)]
        qptiff_files = [file for file in qptiff_files if not re.search(r'\.intermediate\.qptiff$', file)]
        qptiff_files = pd.DataFrame({'qptiff_file':qptiff_files})
        qptiff_files['folder'] = folder
        df_files = pd.concat([df_files, qptiff_files], ignore_index = True)
    
    # Extract cycle numbers from qptiff_file
    df_files['cycle_number'] = df_files['qptiff_file'].apply(lambda x: int(re.search(r'Cycle(\d+)', x).group(1)) if re.search(r'Cycle(\d+)', x) else None)
    # Convert cycle numbers to round format (R01, R02, etc.)
    df_files['round_number'] = df_files['cycle_number'].apply(lambda x: f'R{str(x+1).zfill(2)}')
    
    # Check4: The qptiff and metadata have the same cycles
    df_check4 = pd.DataFrame(columns=["folder", "QC_cycles"])
    for folder in tmp_folders:
        df_metadata_subset = df_metadata[df_metadata['folder'] == folder]
        df_files_subset = df_files[df_files['folder'] == folder]
        # Check if the round numbers from df_files match those in df_metadata
        missing_rounds = set(df_metadata_subset['round_number']) - set(df_files_subset['round_number'])
        extra_rounds = set(df_files_subset['round_number']) - set(df_metadata_subset['round_number'])
        matching = missing_rounds == set() and extra_rounds == set()
        tmp_check4 = pd.DataFrame({'folder': [folder], 'QC_cycles': [matching]})
        df_check4 = pd.concat([df_check4, tmp_check4], ignore_index = True)
    
    bad_qc = df_check4[df_check4["QC_cycles"] == False]
    if not bad_qc.empty:
        message += (f"Check4 - matching rounds QC: NOT PASSED.\nCondition: cycles in qptiff and metadata do not matchs:\n" + "\n".join(bad_qc["folder"]))
        with open(output_txt, "w") as f:
            f.write(message)
    else:
        message += "Check4 - matching rounds QC: PASSED.\n"
    
    ## Check5: All the slides have the same number of rounds
    cycle_values_by_folder = df_metadata.groupby("folder")["round_number"].unique()

    # Compare values across folders
    cycle_consistency = all(
        (cycle_values_by_folder.iloc[i] == cycle_values_by_folder.iloc[0]).all()
        for i in range(1, len(cycle_values_by_folder))
    )

    if not cycle_consistency:
        first_cycle_set = set(cycle_values_by_folder.iloc[0])
        inconsistent_folders = cycle_values_by_folder[
            ~cycle_values_by_folder.apply(lambda x: set(x) == first_cycle_set)
        ].index.tolist()
        message += (
            f"Check5 - cycle consistency QC: NOT PASSED.\nCondition: the following slides have different number of cycles:\n"
            + "\n".join(inconsistent_folders)
        )
        with open(output_txt, "w") as f:
            f.write(message)
    else:
        message += "Check5 - cycle consistency QC: PASSED.\n"

    ## Check6: All the slides have the same set of markers
    channel_values_by_folder = df_metadata.groupby("folder")["marker_id"].unique()

    channel_consistency = all(
        (channel_values_by_folder.iloc[i] == channel_values_by_folder.iloc[0]).all()
        for i in range(1, len(channel_values_by_folder))
    )

    if not channel_consistency:
        first_cycle_set = set(channel_values_by_folder.iloc[0])
        inconsistent_folders = channel_values_by_folder[
            ~channel_values_by_folder.apply(lambda x: set(x) == first_cycle_set)
        ].index.tolist()
        message += (
            f"Check6 - marker consistency QC: NOT PASSED.\nCondition: the following slides have different markers:\n"
            + "\n".join(inconsistent_folders)
        )
    else:
        message += "Check6 - marker consistency QC: PASSED.\n"
    
    with open(output_txt, "w") as f:
        f.write(message)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QC input data AKOYA: raw data. type qc_input_files_akoya_raw.py -h for positional and optional inputs description")
    parser.add_argument("--input_path", type=str, help=" full path to the slide folder, e.g. /path/to/input_data_files_folder ")
    parser.add_argument("--output_txt", type=str, help="path to the output txt where the qc report is saved, e.g. /path/to/project_directory/qc_input_files.txt ")

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    input_path = args.input_path
    output_txt = args.output_txt

    qc_akoya_input_raw(input_path=input_path, output_txt=output_txt)

