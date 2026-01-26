import os
import argparse
import pandas as pd

def data_filtering_post(input_folder, split_celltypes, output_csv):
    print(f"### input folder: {input_folder} ###")
    print(f"### split celltypes: {split_celltypes} ###")
    print(f"### output data: {output_csv} ###")

    # Create output dirs
    out_dir = os.path.dirname(output_csv)
    if out_dir and not os.path.exists(out_dir):
        print(f"### creating folder: {out_dir} ###")
        os.makedirs(out_dir, exist_ok=True)

    # Merge partitions
    print("Reading data")

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

    # Read selected celltypes
    df_celltypes = pd.read_csv(split_celltypes)

    df_celltypes = df_celltypes[df_celltypes["include"] == 1]
    allowed = set(df_celltypes["CellType"].dropna().astype(str).unique().tolist())

    # Filter data
    print("Filtering data")
    
    df_data["CellType"] = df_data["CellType"].astype(str)
    df_data = df_data[df_data["CellType"].isin(allowed)]
    # Drop CellType column (like select(-CellType))
    df_data = df_data.drop(columns=["CellType"])

    # Write data
    print("Writing data")
    df_data.to_csv(output_csv, index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data Filtering (merge annotated csvs + filter by selected celltypes) example: path/to/project_directory/data_annotated.")
    parser.add_argument("--path_input_folder", type=str, required=True, help="Path to input directory where the annotated data is stored (dir).")
    parser.add_argument("--path_split_celltypes", type=str, required=True, help="Path to input csv where the selected celltypes are listed (csv). Must contain columns: CellType, include, exmaple: path/to/project_directory/celltypes_filtered.csv.")
    parser.add_argument("--path_output_csv", type=str, required=True, help="Path to output csv where the filtered merged data will be stored (csv), example: path/to/project_directory/df_downstream.csv.")

    args = parser.parse_args()

    data_filtering_post(
        input_folder=args.path_input_folder,
        split_celltypes=args.path_split_celltypes,
        output_csv=args.path_output_csv,
    )
