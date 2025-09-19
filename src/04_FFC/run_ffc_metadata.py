import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate copying the metadata after running FFC. Type run_czi_extraction.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/FFC_job_list_metadata.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. src/04_FFC/FFC_metadata.py')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path 

df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    input_meta = str(row['input_meta'])
    output_meta = str(row['output_meta'])
    
    print(f"Copy metadata for {input_meta}")
    
    subprocess.run([
        "python", script_path,
        "--path_input_metadata", input_meta,
        "--path_output_metadata", output_meta
    ])
