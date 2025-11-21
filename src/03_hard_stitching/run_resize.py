import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate Hard Stitching. type run_czi_extraction.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. path/to/project_directory/hard_stitching_job_list.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. src/03_hard_stitching/01_resize_processed.py')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path 

df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    input_path_image = str(row["input_path_image"])
    output_path_image = str(row["output_path_image"])
    conversion_factor = str(row["conversion_factor"])
    skip_existing = str(False)
    
    print(f"Running HS for {input_path_image}")
    
    subprocess.run([
        "python", script_path,
        "--input_path_image", input_path_image,
        "--output_path_image", output_path_image,
        "--conversion_factor", str(conversion_factor),
        "--skip_existing", skip_existing
    ])
