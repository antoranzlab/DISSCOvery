import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate AFS. Type run_AFS.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/afs_job_list.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. src/07_AFS/AFS_list_jobs.R')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path 

df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    input_path_medoids = str(row["input_path_medoids"])
    input_path_MS = str(row["input_path_MS"])
    input_path_AF = str(row["input_path_AF"])
    output_path_TS = str(row["output_path_TS"])
    output_path_QC = str(row["output_path_QC"])

    
    print(f"Running AFS for {input_path_MS}")
    
    subprocess.run([
        "python", script_path,
        "--input_path_medoids", input_path_medoids,
        "--input_path_MS", input_path_MS,
        "--input_path_AF", input_path_AF,
        "--output_path_TS", output_path_TS,
        "--output_path_QC", output_path_QC
    ])

