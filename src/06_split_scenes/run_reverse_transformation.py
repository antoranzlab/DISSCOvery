import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='Orchestrate reverse transformation. Type run_reverse_transformation.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/reverse_transformation_job_list.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. src/04_split_scenes/reverse_transformation.py')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path 

df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    input_input_path_tm = str(row["input_path_tm"])
    input_path_masks = str(row["input_path_masks"])
    input_path_bb = str(row["input_path_bb"])
    output_path_masks = str(row["output_path_masks"])
    output_path_bb = str(row["output_path_bb"])

    
    print(f"Running reverse transformation for {input_path_masks}")
    
    subprocess.run([
        "python", script_path,
        "--input_path_tm", input_input_path_tm,
        "--input_path_masks", input_path_masks,
        "--input_path_bb", input_path_bb,
        "--output_path_masks", output_path_masks,
        "--output_path_bb", output_path_bb
    ])

