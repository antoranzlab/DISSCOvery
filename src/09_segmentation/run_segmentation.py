import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate cell segmentation. Type run_segmentation.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /path/to/project_directory/cell_segmentation_joblist.csv')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. src/06_segmentation/segmentation.py')
                    
args = parser.parse_args()
csv_path = args.csv_path
script_path = args.script_path

df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    path_to_the_image = str(row["input_path_image"])
    output_path = str(row["output_path_matrix"])
    QC_path = str(row["output_path_qc"])
    model_path = str(row["path_model"])
    model_name = str(row["model"])
    pp = str(row["pp"])

    
    print(f"Running cell segmentation for {path_to_the_image}")
    
    subprocess.run([
        "python", script_path,
        "--path_to_the_image", path_to_the_image,
        "--path_to_the_models", model_path,
        "--model_name", model_name,
        "--output_path", output_path,
        "--QC_path", QC_path,
        "--PP", pp
    ])