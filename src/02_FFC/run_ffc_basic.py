import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate CZIReader. type run_czi_extraction.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/FFC_job_list.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. src/00_file_parser/czi_reader.py')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path 

df = pd.read_csv(csv_path)
df = df[df['method'] == 'BASIC']

for i, row in df.iterrows():
    in_path = row["input_path"]
    channel = row["channel"]
    out_path_corr = row["output_path_corr"]
    out_path_templates = row["output_path_templates"]
    # skip_existing = 'False'

    print(f"Running FFC basic for {in_path}")
    
    subprocess.run([
        "python", script_path,
        "--in_path", in_path,
        "--channel", channel,
        "--out_path_corr", out_path_corr,
        "--out_path_templates", out_path_templates#,
        # skip_existing
    ])

