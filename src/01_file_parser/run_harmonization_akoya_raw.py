import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate CZIReader. type run_czi_extraction.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /mnt/P10_benchmarking_MILAN_test_bash/czi_extraction_csv.csv ')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. /media/Share1/bencharked_datasets/00_file_parser/czi_reader.py')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path 

df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    input_path = str(row['input_path'])
    output_folder = str(row['output_folder'])
    project_id = str(row['project_id'])
    user_id = str(row['user_id'])
    input_slide_dictionary = str(row['input_slide_dictionary'])
    exp_design_rounds_file = row['exp_design_rounds_file']
    
    print(f"Running harmonizing data for {input_path}")
    
    subprocess.run([
        "python", script_path,
        "--input_path", input_path,
        "--output_folder", output_folder,
        "--project_id", project_id,
        "--user_id", user_id,
        "--input_slide_dictionary", input_slide_dictionary,
        "--exp_design_rounds_file", exp_design_rounds_file
    ])

