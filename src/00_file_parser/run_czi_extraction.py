import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate CZIReader. type run_czi_extraction.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/czi_extraction_csv.csv ')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. /path/to/src/00_file_parser/czi_reader.py')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path 

df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    input_path = row['input_path']
    output_folder = row['output_folder']
    input_channel_dictionary = row['input_channel_dictionary']

    print(f"Running extract_tiles_from_czi for {input_path}")
    
    subprocess.run([
        "python", script_path,
        "--imfilename", input_path,
        "--channel_names_dictionary", input_channel_dictionary,
        "--output_folder", output_folder
    ])
