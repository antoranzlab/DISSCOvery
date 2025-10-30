import os
import sys
import argparse
import numpy as np
import pandas as pd
from skimage.io import imread
from skimage.transform import resize
from pathlib import Path
from PIL import Image
import warnings
import re
from glob import glob

warnings.filterwarnings("ignore")

def feature_extraction(path_input_afs, path_exp_design_rounds, path_input_seg, ref_round, path_output_csv):
    print(f"### input AFS images: {path_input_afs} ###")
    print(f"### experimental design rounds: {path_exp_design_rounds} ###")
    print(f"### input segmentation matrices: {path_input_seg} ###")
    print(f"### reference round during segmentation: {ref_round} ###")
    print(f"### output quality control image: {path_output_csv} ###")

    os.makedirs(path_output_csv, exist_ok=True)

    tmp_folders = [f.name for f in Path(path_input_afs).iterdir() if f.is_dir()]

    df_list = []
    for folder in tmp_folders:
        folder_path = os.path.join(path_input_afs, folder)
        files = os.listdir(folder_path)
        df_tmp = pd.DataFrame({
            "ofile": files,
            "folder": folder
        })
        df_tmp["file"] = df_tmp["ofile"].str.replace(".tiff", "", regex=False)
        df_tmp["file"] = df_tmp["file"].str.replace("AF_FITC", "FITCAF")
        
        split_cols = df_tmp["file"].str.split("_", expand=True)
        split_cols.columns = ["slide_id", "round_number", "version_id", "project_id", "user_id", "scan_region", "channel_id"]
        
        df_tmp = pd.concat([df_tmp, split_cols], axis=1)
        df_list.append(df_tmp)
    
    df_files = pd.concat(df_list, ignore_index=True)
    df_files["channel_id"] = df_files["channel_id"].str.upper()
    tmp_dictionary = pd.read_csv(path_exp_design_rounds)
    tmp_dictionary["channel_id"] = tmp_dictionary["channel_id"].str.upper()
    
    df_files = df_files.merge(
        tmp_dictionary[["slide_id", "round_number", "channel_id", "marker_id"]],
        on=["slide_id", "round_number", "channel_id"], how="left"
    )
    df_files["tissue_id"] = df_files["slide_id"] + "_" + df_files["scan_region"]

    print(f"{df_files['tissue_id'].nunique()} unique tissue(s) found: {', '.join(df_files['tissue_id'].unique())}")

    for tissue_id in df_files["tissue_id"].unique():
        print(tissue_id)
        scene_files = df_files[df_files["tissue_id"] == tissue_id]
        output_csv_file = os.path.join(path_output_csv, f"{tissue_id}.csv")
        
        all_npy_files = glob(os.path.join(path_input_seg, '**', '*.npy'), recursive=True)
        
        dapi_file = [
            f for f in all_npy_files
            if scene_files["slide_id"].iloc[0] in os.path.basename(f)
            and scene_files["user_id"].iloc[0] in os.path.basename(f)
            and ref_round in os.path.basename(f)
            and os.path.basename(f).endswith(scene_files["scan_region"].iloc[0] + '_DAPI.npy')
        ]
        
        if len(dapi_file) != 1:
            raise ValueError("Ambiguous DAPI file selection")
        
        dapi_file = dapi_file[0]
        
        segmentation_matrix = np.load(dapi_file)#.T

        tmp_file = scene_files.iloc[0]
        tmp_image = imread(os.path.join(path_input_afs, tmp_file["folder"], tmp_file["ofile"]))

        if tmp_image.shape != segmentation_matrix.shape:
            segmentation_matrix = resize(segmentation_matrix, tmp_image.shape, order=0, preserve_range=True, anti_aliasing=False).astype(segmentation_matrix.dtype) # NEAREST-NEIGHBOR interpolation

        rows, cols = np.where(segmentation_matrix != 0)
        oids = segmentation_matrix[rows, cols]
        df_oid = pd.DataFrame({"OID": oids})
        df_oid["row"], df_oid["col"] = rows, cols

        df_oid["OID"] = df_oid["OID"].astype(str)
        tmp_dictionary = df_oid.groupby("OID").size().reset_index(name="s.area")

        tmp_location = df_oid.groupby("OID").agg(X=("col", "mean"), Y=("row", "mean")).reset_index()
        tmp_location = tmp_location.merge(tmp_dictionary, on="OID")
        tmp_features = tmp_location[tmp_location["OID"] != "0"].copy()

        scene_files = scene_files.groupby("marker_id").sample(n=1)

        for _, row in scene_files.iterrows():
            tmp_image = imread(os.path.join(path_input_afs, row["folder"], row["ofile"]))
            if tmp_image.shape != segmentation_matrix.shape:
                tmp_image = resize(tmp_image, segmentation_matrix.shape, order=0, preserve_range=True, anti_aliasing=False).astype(tmp_image.dtype) # NEAREST-NEIGHBOR interpolation

            tmp_oid = df_oid.copy()
            tmp_oid["marker"] = tmp_image[tmp_oid["row"], tmp_oid["col"]]
            tmp_marker = tmp_oid.groupby("OID")["marker"].mean().reset_index()
            tmp_marker.columns = ["OID", row["marker_id"]]
            tmp_features = tmp_features.merge(tmp_marker, on="OID", how="left")

        tmp_features["slide_id"] = scene_files["slide_id"].iloc[0]
        tmp_features["scan_region"] = scene_files["scan_region"].iloc[0]
        tmp_features['scene_id'] = tmp_features['scan_region'].str.replace('S', '', regex=False).astype(int) + 1
        tmp_features['scene_id'] = 'scene' + tmp_features['scene_id'].astype(str).str.rjust(2, '0')
        tmp_features.to_csv(output_csv_file, sep = ';', decimal=',', index=False)

    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Feature Extraction.")
    parser.add_argument("--path_input_AFS", required=True, help="Path to input AFS images (dir).")
    parser.add_argument("--path_exp_design_rounds", required=True, help="Path to input experimental design for the rounds (.csv).")
    parser.add_argument("--path_input_seg", required=True, help="Path to input segmentation matrices (dir).")
    parser.add_argument("--ref_round", required=True, help="Round of reference used during segmentation (str).")
    parser.add_argument("--path_output_csv", required=True, help="Path to output feature extracted tables (dir).")

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)


    args = parser.parse_args()

    feature_extraction(
        path_input_afs=args.path_input_AFS,
        path_exp_design_rounds=args.path_exp_design_rounds,
        path_input_seg=args.path_input_seg,
        ref_round=args.ref_round,
        path_output_csv=args.path_output_csv
    )
