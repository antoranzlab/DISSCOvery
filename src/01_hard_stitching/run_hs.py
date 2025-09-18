import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate Hard Stitching. type run_czi_extraction.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/hard_stitching_job_list.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. /src/01_hard_stitching/01_hard_stitching.py')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path

df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    input_tiles = str(row["input_path_tiles"])
    input_metadata = str(row["input_path_meta"])
    output_folder = str(row["output_folder"])
    conversion_factor = str(row["conversion_factor"])
    skip_existing = str(False)
    only_dapi = str(row['only_dapi'])
    
    print(f"Running HS for {input_tiles}")
    
    subprocess.run([
        "python", script_path,
        "--input_tiles", input_tiles,
        "--input_metadata", input_metadata,
        "--output_folder", output_folder,
        "--conversion_factor", str(conversion_factor),
        "--skip_existing", skip_existing,
        "--only_dapi", only_dapi
    ])

