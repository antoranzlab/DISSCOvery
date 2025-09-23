import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate Mask Generation. Type run_STS_mask.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/generate_mask_job_list.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. src/002_STS/STS_generate_mask.py')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path 

df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    input_image_path = str(row["input_image"])
    output_image_path = str(row["output_image"])
    model_path = str(row["model"])
    
    print(f"Running mask generation for {input_image_path}")
    
    subprocess.run([
        "python", script_path,
        "--input_image_path", input_image_path,
        "--output_image_path", output_image_path,
        "--model_path", model_path
    ])

