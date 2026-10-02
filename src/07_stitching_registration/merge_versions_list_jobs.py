#!/usr/bin/env python
"""Merge versions - list jobs. Groups registered images by everything except version (slide_id,
round_id, project_id, user_id, scan_region, channel_id) -- one job per group. Matches each
group's algnqc score csvs by tissue_id (same key, without channel_id)."""
import argparse
import os
import shutil
import sys

import pandas as pd

def _tabulate(root, pattern_suffix, columns):
    rows = []
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            if fname.endswith(pattern_suffix):
                rows.append(os.path.join(dirpath, fname))
    if not rows:
        return pd.DataFrame(columns=["full_path", "ofile"] + columns + ["tissue_id", "tissue_id_channel"])
    df = pd.DataFrame({"full_path": pd.Series(rows, dtype="object")})
    df["ofile"] = df["full_path"].apply(os.path.basename).astype("object")
    stem = df["ofile"].str.replace(r"\.tiff?$", "", regex=True) if pattern_suffix != ".csv" else df["ofile"].str.replace(r"\.csv$", "", regex=True)
    fields = stem.str.split("_", expand=True)
    fields.columns = columns
    df = pd.concat([df, fields], axis=1)
    df["tissue_id"] = df[["slide_id", "round_id", "project_id", "user_id", "scan_region"]].agg("_".join, axis=1)
    df["tissue_id_channel"] = df[["slide_id", "round_id", "project_id", "user_id", "scan_region", "channel_id"]].agg("_".join, axis=1)
    return df

def merge_versions_list_jobs(input_path_registration, input_path_algnqc, ref_version,
                              output_path_folder, output_path_csv):
    print(f"### input path registration: {input_path_registration} ###")
    print(f"### input path algnqc: {input_path_algnqc} ###")
    print(f"### reference version: {ref_version} ###")
    print(f"### output path folder: {output_path_folder} ###")
    print(f"### output path csv job list: {output_path_csv} ###")

    os.makedirs(output_path_folder, exist_ok=True)
    os.makedirs(os.path.dirname(output_path_csv), exist_ok=True)

    cols = ["slide_id", "round_id", "version_id", "project_id", "user_id", "scan_region", "channel_id"]
    df_files_reg = _tabulate(input_path_registration, (".tif", ".tiff"), cols)
    df_files_algnqc = _tabulate(input_path_algnqc, ".csv", cols)

    job_rows = []
    n_single, n_multi = 0, 0
    for tissue_id_channel in df_files_reg["tissue_id_channel"].unique():
        tmp_files_reg = df_files_reg[df_files_reg["tissue_id_channel"] == tissue_id_channel]
        tissue_id = tmp_files_reg["tissue_id"].iloc[0]
        tmp_files_algnqc = df_files_algnqc[df_files_algnqc["tissue_id"] == tissue_id]

        n_versions = tmp_files_reg["version_id"].nunique()

        ref_row = tmp_files_reg.iloc[0]  # first row, not R's random sample_n(1) -- version_id is the only field that varies within a group and gets overwritten regardless, so the pick doesn't affect the result
        ref_folder = "_".join([ref_row["slide_id"], ref_row["round_id"], ref_version,
                                ref_row["project_id"], ref_row["user_id"], ref_row["scan_region"]])
        # scan_region included in the filename (unlike R, which only put it in the folder name) --
        # AFS_list_jobs.py/segmentation_list_jobs.py parse scan_region from the filename itself
        ref_ofile = "_".join([ref_row["slide_id"], ref_row["round_id"], ref_version,
                               ref_row["project_id"], ref_row["user_id"], ref_row["scan_region"],
                               f"{ref_row['channel_id']}.tiff"])
        output_image = os.path.join(output_path_folder, ref_folder, ref_ofile)

        if n_versions == 1:
            # Only one version exists for this (slide, round, scene, channel) --
            # nothing to merge, so copy it straight through here instead of
            # queuing a job for merge_versions.py to do the same trivial copy.
            n_single += 1
            os.makedirs(os.path.dirname(output_image), exist_ok=True)
            shutil.copy(tmp_files_reg["full_path"].iloc[0], output_image)
            continue

        n_multi += 1
        job_rows.append({
            "input_images": ",".join(tmp_files_reg["full_path"]),
            "input_algnqc": ",".join(tmp_files_algnqc["full_path"]),
            "output_image": output_image,
            "n_versions": n_versions,
        })

    print(f"### {n_single} (slide, round, scene, channel) groups had only 1 version -- copied directly ###")
    print(f"### {n_multi} groups had >1 version -- queued as merge jobs ###")

    pd.DataFrame(job_rows).to_csv(output_path_csv, index=False)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge versions - list jobs.")
    parser.add_argument("--input_path_registration", type=str, help="Path to input registration images (path).")
    parser.add_argument("--input_path_algnqc", type=str, help="Path to input algnqc scores (path).")
    parser.add_argument("--ref_version", type=str, help="Reference version (string).")
    parser.add_argument("--output_path_folder", type=str, help="Full path to output directory (folder).")
    parser.add_argument("--output_path_csv", type=str, help="Path to output csv where the job list will be saved (.csv).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    merge_versions_list_jobs(
        input_path_registration=args.input_path_registration,
        input_path_algnqc=args.input_path_algnqc,
        ref_version=args.ref_version,
        output_path_folder=args.output_path_folder,
        output_path_csv=args.output_path_csv,
    )
