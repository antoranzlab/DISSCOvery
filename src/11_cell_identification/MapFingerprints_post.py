import os
import argparse
import pandas as pd

def map_fingerprints_post(input_folder, output_folder, annotation_log, celltypes, node_id, version_id):
    print(f"### input folder: {input_folder} ###")
    print(f"### output folder: {output_folder} ###")
    print(f"### annotation log: {annotation_log} ###")
    print(f"### celltypes: {celltypes} ###")
    print(f"### node identifier: {node_id} ###")
    print(f"### version identifier: {version_id} ###")
    
    # Create output dirs
    if not os.path.exists(output_folder):
        print(f"### creating folder: {output_folder} ###")
        os.makedirs(output_folder, exist_ok=True)
    
    ann_dir = os.path.dirname(annotation_log)
    if ann_dir and not os.path.exists(ann_dir):
        print(f"### creating folder: {ann_dir} ###")
        os.makedirs(ann_dir, exist_ok=True)
    
    ct_dir = os.path.dirname(celltypes)
    if ct_dir and not os.path.exists(ct_dir):
        print(f"### creating folder: {ct_dir} ###")
        os.makedirs(ct_dir, exist_ok=True)
    
    # Merge partitions
    print("Merging partitions")
    
    tmp_files = [os.path.join(input_folder, f) for f in os.listdir(input_folder) if f.lower().endswith(".csv")]
    tmp_files.sort()
    
    if len(tmp_files) == 0:
        raise FileNotFoundError(f"No .csv files found in input folder: {input_folder}")
    
    dfs = []
    for fp in tmp_files:
        try:
            dfs.append(pd.read_csv(fp))
        except Exception as e:
            raise RuntimeError(f"Failed reading {fp}: {e}") from e
    
    df_data = pd.concat(dfs, ignore_index=True)
    
    if "CellType" not in df_data.columns and "predicted.celltype" in df_data.columns:
        df_data = df_data.rename(columns={"predicted.celltype": "CellType"})
    
    required_cols = {"slide_id", "scene_id", "CellType"}
    missing = sorted(list(required_cols - set(df_data.columns)))
    if missing:
        raise ValueError(
            f"Missing required columns in merged data: {missing}. "
            f"Available columns: {list(df_data.columns)}"
        )
    
    df_data["tissue_id"] = df_data["slide_id"].astype(str) + "_" + df_data["scene_id"].astype(str)
    
    # Keep logs
    print("Keeping logs")
    
    log_cols = ["slide_id", "scene_id", "OID", "X", "Y", "CellType"]
    missing_log = [c for c in log_cols if c not in df_data.columns]
    if missing_log:
        raise ValueError(f"Missing columns required for annotation log: {missing_log}")
    
    df_log = df_data.loc[:, log_cols].copy()
    df_log["node_id"] = node_id
    df_log["version_id"] = version_id
    
    # Create celltypes
    print("Creating celltypes")
    df_celltypes = (
        df_data.groupby("CellType", dropna=False)
        .size()
        .reset_index(name="N")
    )
    df_celltypes["include"] = 1
    
    # Write data
    print("Writing data")
    
    # per-tissue CSVs (drop tissue_id column, like select(-tissue_id))
    for tissue in df_data["tissue_id"].unique():
        tmp_data = df_data[df_data["tissue_id"] == tissue].drop(columns=["tissue_id"])
        out_fp = os.path.join(output_folder, f"{tissue}.csv")
        tmp_data.to_csv(out_fp, index=False)
    
    df_log.to_csv(annotation_log, index=False)
    df_celltypes.to_csv(celltypes, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Map fingerprints post.")
    parser.add_argument("--path_input_folder", type=str, required=True, help="Path to input directory where partitions have been stored (dir). Example: /path/to/project_directory/output_cell_identification/n01/v01/tmp_partitions_annotated.")
    parser.add_argument("--path_output_folder", type=str, required=True, help="Path to output directory where csvs will be stored (dir). Example: /path/to/project_directory/output_cell_identification/n01/v01/data_annotated.")
    parser.add_argument("--path_annotation_log", type=str, required=True, help="Path to csv to keep track of cell labels (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/annotation_log.csv.")
    parser.add_argument("--path_celltypes", type=str, required=True, help="Path to output csv where the cell types for split selection are stored (.csv). Example: /path/to/project_directory/output_cell_identification/n01/v01/unique_celltypes.csv.")
    parser.add_argument("--node_id", type=str, required=True, help="Identifier for the level at which the annotations will be stored (.string). Example: n01.")
    parser.add_argument("--version_id", type=str, required=True, help="Version performed clustering (string). Example: v01.")

    args = parser.parse_args()

    map_fingerprints_post(
        input_folder=args.path_input_folder,
        output_folder=args.path_output_folder,
        annotation_log=args.path_annotation_log,
        celltypes=args.path_celltypes,
        node_id=args.node_id,
        version_id=args.version_id,
    )
