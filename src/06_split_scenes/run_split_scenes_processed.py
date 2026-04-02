import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate split scenes processed. type run_split_scenes_processed.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/split_scenes_job_list.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. src/04_split_scenes/split_scenes_processed.py')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path
 
df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    
    input_path_image = str(row["input_path_image"])
    input_path_bb = str(row['input_path_bb'])
    input_path_foreground = str(row['input_path_foreground'])
    input_path_qc = str(row['input_path_qc'])
    output_path_image = str(row['output_path_image'])
    conversion_factor_qc = str(row['conversion_factor_qc'])
    conversion_factor_sts = str(row['conversion_factor_sts'])
    skip_existing = str(False)
    
    print(f"Running split scenes for {input_path_image}")
    
    subprocess.run([
        "python", script_path,
        "--input_path_image", input_path_image,
        "--input_path_bb", input_path_bb,
        "--input_path_foreground", str(input_path_foreground),
        "--input_path_qc", str(input_path_qc),
        "--output_path_image", output_path_image,
        "--conversion_factor_qc", conversion_factor_qc,
        "--conversion_factor_sts", conversion_factor_sts,
        "--skip_existing", skip_existing
    ])
