import aicspylibczi
import pandas as pd
import argparse
import os
import sys

def find_czi_files(directory):
    """Find all .czi files within the directory and its subdirectories."""
    czi_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".czi"):
                czi_files.append(os.path.join(root, file))
    return czi_files

def read_czi_from_meta(imfilename):
    """Extract metadata"""
    czi = aicspylibczi.CziFile(imfilename)
    metadata_root = czi.meta
    return metadata_root

def get_unique_channel_details(metadata_root):
    """ Extract channels information from raw data"""
    channels = metadata_root.findall(".//Channels/Channel")
    unique_channels = {}
    for channel in channels:
        channel_id = channel.attrib.get("Id")
        if channel_id and channel_id not in unique_channels:
            unique_channels[channel_id] = channel.attrib.get("Name")

    # Convert the dictionary to a list of dictionaries
    unique_channel_details = [{"channel_id": name, "channel_number": int(id.replace("Channel:", ""))} for id, name in unique_channels.items()]
    df_channels = pd.DataFrame(unique_channel_details)
    return df_channels

def czi_files_qc(directory, output_txt):
    """ Check if the data is in the correct format """

    # List all entries in the directory given by "path"
    czi_files = find_czi_files(directory)
    df_meta = pd.DataFrame()
    
    for index, czi_file in enumerate(czi_files):
        # Print progress
        print(f"{index + 1} out of {len(czi_files)}")
        
        tmp_meta = read_czi_from_meta(czi_file)
        df_channels = get_unique_channel_details(tmp_meta)
        df_channels["czi_file"] = czi_file
        # Append to the main DataFrame
        df_meta = pd.concat([df_meta, df_channels], ignore_index=True)
    
    ## Check1: all files are format .czi
    all_czi = df_meta["czi_file"].str.endswith(".czi").all()
    
    if all_czi:
        message = "Check1 - File format QC: PASSED.\n"
    else:
        mismatch_files = df_meta["czi_file"][df_meta["czi_file"].str.endswith(".czi") == False]
        message = "Check1 - File format QC: NOT PASSED.\nCondition: File format mismatch: " + ", ".join([open(file).read().strip() for file in mismatch_files if open(file).readable()])
        
        with open(output_txt, "w") as file:
            file.write(message)  # Write to a text file
        return
    
    # Create a new column with the basename of each file path
    df_meta["basename"] = df_meta["czi_file"].apply(lambda x: os.path.basename(x.replace(".czi", "")))
    
    ## Check2: filenames have exactly 4 times the character '_'.
    check_underscores = df_meta["basename"].apply(lambda x: x.count("_") == 4).all()
    
    if check_underscores:
        message += "Check2 - File tabulation QC: PASSED.\n"
    else:
        mismatch_files = df_meta['czi_file'][df_meta["basename"].apply(lambda x: x.count("_") != 4)]
        message += "Check2 - File tabulation QC: NOT PASSED.\nCondition: File tabulation mismatch: " + ", ".join([file for file in mismatch_files])
        
        with open(output_txt, "w") as file:
            file.write(message)  # Write to a text file
        return
    
    # Split the basename into multiple columns
    df_meta[["slide_id", "round_number", "version_id", "project_id", "user_id"]] = df_meta["basename"].str.split("_", expand=True)
    
    ## Check3: the rounds/versions are in the right format
    rounds_correct_format = df_meta["round_number"].str.match(r"^R\d{1,2}$").all()
    
    if rounds_correct_format:
        message += "Check3 - Round naming QC: PASSED.\n"
    else:
        mismatch_files = df_meta["czi_file"][~df_meta["round_number"].str.match(r"^R\d{1,2}$", na=False)].unique()
        message += "Check3 - Round naming QC: NOT PASSED.\nCondition: Round naming mismatch: " + ", ".join([file for file in mismatch_files])
        
        with open(output_txt, "w") as file:
            file.write(message)  # Write to a text file
        return
    
    versions_correct_format = df_meta["version_id"].str.match(r"^V\d{1,2}$").all()
    
    if versions_correct_format:
        message += "Check4 - Version naming QC: PASSED.\n"
    else:
        mismatch_files = df_meta["czi_file"][~df_meta["version_id"].str.match(r"^V\d{1,2}$", na=False)].unique()
        message += "Check4 - Version naming QC: NOT PASSED.\nCondition: Version naming mismatch: " + ", ".join([file for file in mismatch_files])
        
        with open(output_txt, "w") as file:
            file.write(message)  # Write to a text file
        return
    
    ## Check5: channel names are within expectations
    unique_channel_names = set(df_meta["channel_id"].unique())
    allowed_channels = {
        "DAPI",
        "FITC",
        "AF",
        "AF_FITC",
        "FITC_AF",
        "TRITC",
        "CY5",
        "CY7",
        "CY3",
    }
    channels_correct_names = unique_channel_names.issubset(allowed_channels)
    
    if channels_correct_names:
        message += "Check5 - Channel naming QC: PASSED.\n"
    else:
        invalid_channels = unique_channel_names - allowed_channels
        mismatch_files = df_meta["czi_file"][df_meta["channel_id"].isin(invalid_channels)]
        message += "Check5 - Channel naming QC: NOT PASSED.\nCondition: Channel naming mismatch: " + ", ".join([file for file in mismatch_files])
        
        with open(output_txt, "w") as file:
            file.write(message)  # Write to a text file
        return
    
    ## Check6: all slides have the same round/versions
    df_meta["combined_id"] = df_meta["round_number"] + "_" + df_meta["version_id"]
    grouped_combinations = df_meta.groupby("slide_id")["combined_id"].apply(set)
    all_same_combinations = all(grouped_combinations.iloc[0] == x for x in grouped_combinations)
    
    if all_same_combinations:
        message += "Check6 - Round/Versions per slide QC: PASSED.\n"
    else:
        # invalid_slides = grouped_combinations[grouped_combinations != grouped_combinations.iloc[0]]
        message += "Check6 - Round/Versions per slide QC: NOT PASSED.\nRound/Versions per slide mismatch: \n"
        reference_combination = grouped_combinations.iloc[0]
        for slide_id, combinations in grouped_combinations.items():
            missing_combinations = reference_combination - combinations
            if missing_combinations:
                message += f"Slide {slide_id} is missing: {missing_combinations}\n"
        
        with open(output_txt, "w") as file:
            file.write(message)  # Write to a text file
        return
    
    ## Check7: all slide/round/versions have the same channels
    df_meta["combined_id"] = (df_meta["slide_id"] + "_" + df_meta["round_number"] + "_" + df_meta["version_id"])
    grouped_channels = df_meta.groupby("combined_id")["channel_id"].apply(set)
    all_same_channels = all(grouped_channels.iloc[0] == x for x in grouped_channels)
    
    if all_same_channels:
        message += "Check7 - Channels per Slide/Round/Version QC: PASSED.\n"
    else:
        # invalid_slides = grouped_combinations[grouped_combinations != grouped_combinations.iloc[0]]
        message += "Check7 - Channels per Slide/Round/Version QC: NOT PASSED.\nChannels per Slide/Round/Versions mismatch: \n"
        reference_channels = grouped_channels.iloc[0]
        
        for combined_id, channels in grouped_channels.items():
            if channels != reference_channels:
                extra_channels = channels - reference_channels
                missing_channels = reference_channels - channels
                if extra_channels:
                    message += f"Combination {combined_id} has extra channels: {extra_channels}\n"
                if missing_channels:
                    message += f"Combination {combined_id} is missing channels: {missing_channels}\n"
    
    with open(output_txt, "w") as file:
        file.write(message)  # Write to a text file
        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CZIFile - QC. type czi_files_qc.py -h for positional and optional inputs description")
    parser.add_argument("--directory", type=str, help=" parent directory where the czi files are stored e.g. /path/to/raw_data")
    parser.add_argument("--output_txt", type=str, help="path to txt where the QC report will be stored e.g. /path/to/project_directory/czi_qc_report.txt")

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    directory = args.directory  # Example: '/path/to/raw_data'
    output_txt = args.output_txt  #Example: '/path/to/project_directory/czi_qc_report.txt'

    czi_files_qc(directory=directory, output_txt=output_txt)

