import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate Mask Generation. Type run_QC.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/qualifai_list_jobs.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. src/03_QC/QUALIFAI.py')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path 

df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    input_image_path = str(row["input_image"])
    output_image_path = str(row["output_image"])
    model_path = str(row["model_path"])
    
    print(f"Running Qual-IF-AI for {input_image_path}")
    
    subprocess.run([
        "python", script_path,
        "--input_image_path", input_image_path,
        "--output_image_path", output_image_path,
        "--model_path", model_path
    ])

