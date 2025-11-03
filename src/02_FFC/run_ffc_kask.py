import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate FFC Kask. Type run_ffc_kask.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/FFC_job_list.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. src/04_FFC/FFC_kask.py')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path 

df = pd.read_csv(csv_path)
df = df[df['method'] == 'KASK']

for i, row in df.iterrows():
    in_path = str(row["input_path"])
    in_meta = str(row['input_meta'])
    in_mask = str(row['input_mask'])
    px_size = str(row['mask_pixel_size'])
    channel = str(row["channel"])
    out_path_corr = str(row["output_path_corr"])
    out_path_templates = str(row["output_path_templates"])
    n_cores = str(10)
    skip_existing = str('False')
    
    print(f"Running FFC Kask for {in_path}")
    
    subprocess.run([
        "python", script_path,
        "--input_images", in_path,
        "--input_metadata", in_meta,
        "--input_mask", in_mask,
        "--pixel_size", px_size,
        "--channel", channel,
        "--output_path_corrected_tiles", out_path_corr,
        "--output_path_templates", out_path_templates,
        "--n_cores", n_cores,
        "--skip_existing", skip_existing
    ])

