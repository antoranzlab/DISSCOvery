#!/usr/bin/env python
"""Autofluorescence subtraction (AFS) - list jobs. For each real (non-DAPI/AF/BLANK) marker
tile, finds the matching AF-reference tile for the same slide/scene/channel and emits one AFS
job per marker tile. Join keys against exp_design_rounds are computed dynamically since its
schema varies by technology (MVM/MILAN's has no slide_id, e.g.)."""
import argparse
import os
import sys

import pandas as pd

def _normalize_channel(s):
    return s.str.replace("AF_FITC", "AF", regex=False).str.replace("FITC_AF", "AF", regex=False).str.upper()

NULL_MARKER_VALUES = ("NA", "AF", "BLANK", "<NA>", "--")

# shared by both the ref_round_af-based lookup and its fallback -- the two were functionally identical duplicate blocks in the R source
def _closest_af_reference(df_files, slide_id, scan_region, channel_id, target_round_n):
    cand = df_files[
        (df_files["slide_id"] == slide_id)
        & (df_files["scan_region"] == scan_region)
        & (df_files["channel_id"] == channel_id)
        & (df_files["marker_id"].isin(NULL_MARKER_VALUES) | df_files["marker_id"].isna())
        & (df_files["QC_include"] == 1)
    ].copy()
    if cand.empty:
        return cand
    cand["tmp_delta"] = (cand["roundn"] - target_round_n).abs()
    cand = cand[cand["tmp_delta"] == cand["tmp_delta"].min()]
    if len(cand) > 1:
        cand = cand[cand["roundn"] == cand["roundn"].min()]
    return cand

def afs_job_list(input_path_images, input_path_medoids, output_folder, output_folder_qc,
                  exp_design_rounds, output_path_csv):
    print(f"### input path images: {input_path_images} ###")
    print(f"### input path medoids: {input_path_medoids} ###")
    print(f"### output directory: {output_folder} ###")
    print(f"### output directory QC: {output_folder_qc} ###")
    print(f"### experimental design rounds: {exp_design_rounds} ###")
    print(f"### output path csv job list: {output_path_csv} ###")

    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(output_folder_qc, exist_ok=True)
    os.makedirs(os.path.dirname(output_path_csv), exist_ok=True)

    folders = sorted(f.name for f in os.scandir(input_path_images) if f.is_dir())
    rows = []
    for folder in folders:
        for ofile in sorted(os.listdir(os.path.join(input_path_images, folder))):
            if not (ofile.endswith(".tif") or ofile.endswith(".tiff")):
                continue
            rows.append({"ofile": ofile, "folder": folder})
    df_files = pd.DataFrame(rows)
    stem = df_files["ofile"].str.replace(r"\.tif+$", "", regex=True)
    stem = stem.str.replace("AF_FITC", "AF", regex=False).str.replace("FITC_AF", "AF", regex=False)
    fields = stem.str.split("_", expand=True)
    fields.columns = ["slide_id", "round_number", "version_id", "project_id", "user_id", "scan_region", "channel_id"]
    df_files = pd.concat([df_files, fields], axis=1)
    df_files["channel_id"] = df_files["channel_id"].str.upper()

    df_exp = pd.read_csv(exp_design_rounds)
    df_exp["channel_id"] = _normalize_channel(df_exp["channel_id"])
    df_exp.loc[df_exp["marker_id"] == "None", "marker_id"] = df_exp.loc[df_exp["marker_id"] == "None", "channel_id"]

    df_exp = df_exp.drop(columns=[c for c in ("folder",) if c in df_exp.columns])
    if "round_id" in df_exp.columns:
        df_exp = df_exp.rename(columns={"round_id": "round_number"})
    if "ref_round_afs" in df_exp.columns:
        df_exp = df_exp.rename(columns={"ref_round_afs": "ref_round_af"})

    df_exp = df_exp.drop_duplicates()
    dedup_keys = [c for c in ("slide_id", "round_number", "channel_id", "marker_id") if c in df_exp.columns]
    df_exp = df_exp.drop_duplicates(subset=dedup_keys, keep="first")

    join_keys = [c for c in df_files.columns if c in df_exp.columns]
    df_files = df_files.merge(df_exp, on=join_keys, how="left")
    df_files["roundn"] = df_files["round_number"].str.replace("R", "", regex=False).astype(float)

    has_ref_round_af = "ref_round_af" in df_files.columns
    job_rows = []
    for _, tmp_file in df_files.iterrows():
        if tmp_file.get("QC_include") != 1:
            continue
        marker_id = tmp_file.get("marker_id")
        if pd.isna(marker_id) or marker_id in ("NA", "<NA>"):
            continue
        if str(marker_id).upper() == str(tmp_file["channel_id"]).upper():
            continue
        if marker_id in NULL_MARKER_VALUES or marker_id == "DAPI":
            continue

        tmp_af_file = pd.DataFrame()
        if has_ref_round_af and pd.notna(tmp_file.get("ref_round_af")):
            tmp_af_file = df_files[
                (df_files["slide_id"] == tmp_file["slide_id"])
                & (df_files["scan_region"] == tmp_file["scan_region"])
                & (df_files["channel_id"] == tmp_file["channel_id"])
                & (df_files["round_number"] == tmp_file["ref_round_af"])
            ]
        if tmp_af_file.empty:
            tmp_af_file = _closest_af_reference(df_files, tmp_file["slide_id"], tmp_file["scan_region"],
                                                 tmp_file["channel_id"], tmp_file["roundn"])
        if tmp_af_file.empty:
            same = df_files[
                (df_files["slide_id"] == tmp_file["slide_id"])
                & (df_files["scan_region"] == tmp_file["scan_region"])
                & (df_files["channel_id"] == tmp_file["channel_id"])
            ]
            if same.empty:
                continue
            tmp_af_file = same.sample(n=1, random_state=1)

        af_row = tmp_af_file.iloc[0]
        job_rows.append({
            "marker_id": marker_id,
            "input_path_medoids": input_path_medoids,
            "input_path_MS": os.path.join(input_path_images, tmp_file["folder"], tmp_file["ofile"]),
            "input_path_AF": os.path.join(input_path_images, af_row["folder"], af_row["ofile"]),
            "output_path_QC": os.path.join(output_folder_qc, str(marker_id), tmp_file["ofile"]),
            "output_path_TS": os.path.join(output_folder, tmp_file["folder"], tmp_file["ofile"]),
        })

    pd.DataFrame(job_rows).to_csv(output_path_csv, index=False)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autofluorescence subtraction - list jobs.")
    parser.add_argument("--input_path_images", type=str, help="Path to input tiles (path).")
    parser.add_argument("--input_path_medoids", type=str, help="Path to input medoids (csv).")
    parser.add_argument("--output_folder", type=str, help="Path to output path to save images (path).")
    parser.add_argument("--output_folder_qc", type=str, help="Path to output path to save qc plots (path).")
    parser.add_argument("--exp_design_rounds", type=str, help="Path to experimental design for the rounds (.csv).")
    parser.add_argument("--output_path_csv", type=str, help="Path to output csv where the job list will be saved (.csv).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    afs_job_list(
        input_path_images=args.input_path_images,
        input_path_medoids=args.input_path_medoids,
        output_folder=args.output_folder,
        output_folder_qc=args.output_folder_qc,
        exp_design_rounds=args.exp_design_rounds,
        output_path_csv=args.output_path_csv,
    )
