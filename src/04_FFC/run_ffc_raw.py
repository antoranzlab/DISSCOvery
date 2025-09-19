import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate FFC. Type run_ffc_raw.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/FFC_job_list.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. src/04_FFC/FFC_raw.py')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path 

df = pd.read_csv(csv_path)
df = df[df['method'] == 'RAW']

for i, row in df.iterrows():
    in_path = str(row['input_path'])
    channel = str(row['channel'])
    out_path_corr = str(row['output_path_corr'])
    skip_existing = str(False)
    
    print(f"Running FFC basic for {in_path}")
    
    subprocess.run([
        "python", script_path,
        "--input_images", in_path,
        "--channel", channel,
        "--output_path_corrected_tiles", out_path_corr,
        "--skip_existing", skip_existing
    ])
