import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate Bounding Boxes generation. Type run_STS_BBs.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/BB_estimation_job_list.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. src/02_STS/STS_generate_BB.py')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path 

df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    input_image_path = str(row["input_image"])
    bbox_tile_path = str(row["output_bb"])
    filter_small = str(row["filter_small"])
    
    print(f"Running Bounding Box estimation for {input_image_path}")
    
    subprocess.run([
        "python", script_path,
        "--input_image_path", input_image_path,
        "--bbox_tile_path", bbox_tile_path,
        "--filter_small", filter_small
    ])

