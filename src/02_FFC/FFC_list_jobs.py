import argparse
import os
import sys

import pandas as pd

def ffc_job_list(
    input_path_tiles,
    input_path_meta,
    input_path_masks,
    mask_pixel_size,
    input_method_dictionary,
    acquisition_technology,
    output_folder_corr,
    output_folder_templates,
    output_path_csv,
    output_path_csv_metadata,
):
    """List the tile folders under input_path_tiles and build the per-channel FFC joblist."""
    print(f"### input path tiles: {input_path_tiles} ###")
    print(f"### input path meta: {input_path_meta} ###")
    print(f"### input path masks: {input_path_masks} ###")
    print(f"### mask pixel size: {mask_pixel_size} ###")
    print(f"### input method dictionary: {input_method_dictionary} ###")
    print(f"### acquisition technology: {acquisition_technology} ###")
    print(f"### output corrected tiles: {output_folder_corr} ###")
    print(f"### output templates: {output_folder_templates} ###")
    print(f"### output path csv job list: {output_path_csv} ###")
    print(f"### output path csv job list metadata: {output_path_csv_metadata} ###")

    os.makedirs(output_folder_corr, exist_ok=True)
    os.makedirs(output_folder_templates, exist_ok=True)
    os.makedirs(os.path.dirname(output_path_csv), exist_ok=True)
    os.makedirs(os.path.dirname(output_path_csv_metadata), exist_ok=True)

    dictionary = pd.read_csv(input_method_dictionary)
    dictionary = dictionary[dictionary["technology"] == acquisition_technology]

    folders = sorted(f.name for f in os.scandir(input_path_tiles) if f.is_dir())

    job_list = []
    for folder in folders:
        tile_dir = os.path.join(input_path_tiles, folder)
        files = [f for f in os.listdir(tile_dir) if ".tif" in f]

        parsed = pd.DataFrame({"ofile": files})
        parsed["file"] = parsed["ofile"].str.replace(".tiff", "", regex=False)
        parsed["file"] = parsed["file"].str.replace("AF_FITC", "AFFITC", regex=False)
        parsed[["slide_id", "round_id", "version_id", "project_id", "user_id", "mosaic_index", "channel_id"]] = (
            parsed["file"].str.split("_", expand=True)
        )

        meta_files = [f for f in os.listdir(os.path.join(input_path_meta, folder)) if f.endswith(".csv")]
        meta_file = os.path.join(input_path_meta, folder, meta_files[0]) if meta_files else None

        for channel in parsed["channel_id"].unique():
            channel_files = parsed[parsed["channel_id"] == channel]
            slide_id = channel_files["slide_id"].iloc[0]
            job_list.append(
                {
                    "input_path": tile_dir,
                    "input_meta": meta_file,
                    "input_mask": os.path.join(input_path_masks, slide_id, f"{folder}_DAPI.tiff"),
                    "mask_pixel_size": mask_pixel_size,
                    "output_path_corr": os.path.join(output_folder_corr, folder),
                    "output_path_templates": os.path.join(output_folder_templates, folder),
                    "channel": channel,
                }
            )

    job_list = pd.DataFrame(job_list)
    job_list = job_list.merge(dictionary[["channel", "method"]], on="channel", how="left")
    job_list.to_csv(output_path_csv, index=False)

    job_list_meta = job_list.copy()
    job_list_meta["output_meta"] = job_list_meta.apply(
        lambda row: os.path.join(row["output_path_corr"], os.path.basename(row["input_meta"])), axis=1
    )
    job_list_meta = job_list_meta[["input_meta", "output_meta"]].drop_duplicates()
    job_list_meta.to_csv(output_path_csv_metadata, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flat Field Correction - list jobs.")
    parser.add_argument("--input_path_tiles", type=str, help="Path to input tiles (path).")
    parser.add_argument("--input_path_meta", type=str, help="Path to input metadata (path).")
    parser.add_argument("--input_path_masks", type=str, help="Path to input masks (path).")
    parser.add_argument("--mask_pixel_size", type=str, help="Pixel size of the masks (numeric).")
    parser.add_argument(
        "--input_method_dictionary",
        type=str,
        help="Path to input csv with the dictionary of method per technology/channel (csv).",
    )
    parser.add_argument("--acquisition_technology", type=str, help="Acquisition technology used (string).")
    parser.add_argument("--output_folder_corr", type=str, help="Path to output path to save images (path).")
    parser.add_argument("--output_folder_templates", type=str, help="Path to output path to save templates (path).")
    parser.add_argument("--output_path_csv", type=str, help="Path to output csv where the job list will be saved (.csv).")
    parser.add_argument(
        "--output_path_csv_metadata",
        type=str,
        help="Path to output csv where the job list will be saved for the metadata (.csv).",
    )

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    ffc_job_list(
        input_path_tiles=args.input_path_tiles,
        input_path_meta=args.input_path_meta,
        input_path_masks=args.input_path_masks,
        mask_pixel_size=args.mask_pixel_size,
        input_method_dictionary=args.input_method_dictionary,
        acquisition_technology=args.acquisition_technology,
        output_folder_corr=args.output_folder_corr,
        output_folder_templates=args.output_folder_templates,
        output_path_csv=args.output_path_csv,
        output_path_csv_metadata=args.output_path_csv_metadata,
    )
