import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate QC evaluation after registration with COLLAGE. Type run_algnqc.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/algnqc_job_list.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. src/05_reg_COLLAGE/algnqc_list_jobs.R')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path 

df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    path_ref_image = str(row["path_ref_image"])
    path_query_image = str(row["path_query_image"])
    path_model = str(row["path_model"])
    path_csv = str(row["path_csv"])
    path_html = str(row["path_html"])
    path_json = str(row["path_json"])

    
    print(f"Running AlgnQC for {path_query_image}")
    
    subprocess.run([
        "python", script_path,
        "--path_ref_image", path_ref_image,
        "--path_query_image", path_query_image,
        "--path_model", path_model,
        "--path_csv", path_csv,
        "--path_html", path_html,
        "--path_json", path_json
    ])

