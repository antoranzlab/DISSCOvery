import pandas as pd
import subprocess
import argparse

parser = argparse.ArgumentParser(description='orchestrate Hard Stitching. type run_czi_extraction.py -h for positional and optional inputs description')
parser.add_argument('csv_path', type=str,
                    help=' full path to the csv with the joblist. file e.g. /mnt/P10_benchmarking_MILAN_test_bash/czi_extraction_csv.csv ')
parser.add_argument('script_path', type=str,
                    help='path to python script to be executed. e.g. /media/Share1/bencharked_datasets/00_file_parser/czi_reader.py')
                    
args = parser.parse_args()

csv_path = args.csv_path 
script_path = args.script_path
 
df = pd.read_csv(csv_path)

for i, row in df.iterrows():
    
    input_path_tiles = str(row["input_path_tiles"])
    input_path_meta = str(row["input_path_meta"])
    input_path_bb = str(row['input_path_bb'])
    input_path_masks_foreground = str(row['input_path_masks_foreground'])
    input_path_masks_qc = str(row['input_path_masks_qc'])
    channel_id = str(row['channel_id'])
    conversion_factor_qc = str(row['conversion_factor_qc'])
    conversion_factor_sts = str(row['conversion_factor_sts'])
    output_path_folder = str(row['output_path_folder'])
    skip_existing = str(False)
    
    print(f"Running split scenes for {input_path_tiles}")
    
    subprocess.run([
        "Rscript", script_path,
        "--input_path_tiles", input_path_tiles,
        "--input_path_meta", input_path_meta,
        "--input_path_bb", input_path_bb,
        "--input_path_masks_foreground", str(input_path_masks_foreground),
        "--input_path_masks_qc", str(input_path_masks_qc),
        "--channel_id", channel_id,
        "--conversion_factor_qc", conversion_factor_qc,
        "--conversion_factor_sts", conversion_factor_sts,
        "--output_path_folder", output_path_folder,
        "--skip_existing", skip_existing
    ])
