import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate BBs concordance evaluation. Type run_STS_concordance.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/bb_concordance_job_list.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. src/02_STS/STS_evaluate_concordance.R')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path 

df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    input_path_BB = str(row["input_folder"])
    output_heatmap_path_html = str(row["output_folder_html"])
    output_heatmap_path_json = str(row["output_folder_json"])
    ref_round = str(row["ref_round"])
    reference_version = str(row["ref_version"])
    
    print(f"Running evaluate concordance for {input_path_BB}")
    
    subprocess.run([
        "Rscript", script_path,
        "--input_path_BB", input_path_BB,
        "--output_heatmap_path_html", output_heatmap_path_html,
        "--output_heatmap_path_json", output_heatmap_path_json,
        "--reference_round", ref_round,
        "--reference_version", reference_version
    ])

