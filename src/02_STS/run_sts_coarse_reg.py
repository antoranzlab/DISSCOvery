import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate STS coarse registration. type run_czi_extraction.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/coarse_registration_job_list.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. src/02_STS/STS_coarse_registration_imreg.py')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path 

df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    fixed_image = str(row['fixed_image'])
    query_image = str(row["query_image"])
    output_image = str(row["output_image"])
    output_tm = str(row["output_tm"])
    
    print(f"Running coarse registration for {query_image}")
    
    subprocess.run([
        "python", script_path,
        "--path_fixed_image", fixed_image,
        "--path_query_image", query_image,
        "--path_query_registered", output_image,
        "--path_transformation_matrix", output_tm
    ])
