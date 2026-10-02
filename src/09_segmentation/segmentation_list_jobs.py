#!/usr/bin/env python
"""Cell segmentation - list jobs for reference-round DAPI images only. Unlike a pure metadata-listing script, this one has a real
side effect: for conversion_factor != 1 it resizes every DAPI tile and writes the resized copy
under output_folder/Resized/ (MILAN/MVM uses conversion_factor=1, a plain copy; COMET/AKOYA
need the actual resize)."""
import argparse
import json
import os
import shutil
import sys

import cv2
import numpy as np
import pandas as pd
import tifffile

def resize_dapi(src_path, dst_path, conversion_factor):
    if conversion_factor == 1:
        shutil.copyfile(src_path, dst_path)
        return
    im = tifffile.imread(src_path)
    im_norm = im.astype(np.float64) / (2 ** 16 - 1)
    new_h = round(im.shape[0] / conversion_factor)
    new_w = round(im.shape[1] / conversion_factor)
    resized = cv2.resize(im_norm, (new_w, new_h), interpolation=cv2.INTER_LINEAR)  # validated against real R+EBImage baseline: 93.9% exact-pixel match, corr 1.000000; INTER_AREA/INTER_CUBIC/PIL bilinear all measurably worse
    resized = np.round(np.clip(resized, 0, 1) * (2 ** 16 - 1)).astype(np.uint16)
    tifffile.imwrite(dst_path, resized, compression="lzw")

def segmentation_job_list(input_path_images, output_folder, ref_round, conversion_factor,
                           path_model, model_name, output_path_csv, pp, ref_version=None, reference_map=None):
    print(f"### input path images: {input_path_images} ###")
    print(f"### output directory: {output_folder} ###")
    print(f"### reference round: {ref_round} ###")
    print(f"### conversion factor: {conversion_factor} ###")
    print(f"### path model: {path_model} ###")
    print(f"### model name: {model_name} ###")
    print(f"### output path csv job list: {output_path_csv} ###")
    print(f"### pre-processing: {pp} ###")

    if reference_map is None and not ref_round:
        raise ValueError("supply ref_round or reference_map")
    if reference_map is not None and (ref_round is not None or ref_version is not None):
        raise ValueError("reference_map and ref_round/ref_version are mutually exclusive")

    conversion_factor = float(conversion_factor)

    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(os.path.join(output_folder, "Matrix"), exist_ok=True)
    os.makedirs(os.path.join(output_folder, "QC"), exist_ok=True)
    os.makedirs(os.path.join(output_folder, "Resized"), exist_ok=True)
    os.makedirs(os.path.dirname(output_path_csv) or ".", exist_ok=True)

    folders = sorted(f.name for f in os.scandir(input_path_images) if f.is_dir())
    rows = []
    for folder in folders:
        for ofile in sorted(os.listdir(os.path.join(input_path_images, folder))):
            if not (ofile.endswith(".tif") or ofile.endswith(".tiff")):
                continue
            rows.append({"ofile": ofile, "folder": folder})
    if not rows:
        raise ValueError("no input TIFF images found")
    df_files = pd.DataFrame(rows)
    stem = df_files["ofile"].str.replace(r"\.tif+$", "", regex=True)
    stem = stem.str.replace("AF_FITC", "AF", regex=False).str.replace("FITC_AF", "AF", regex=False)
    fields = stem.str.split("_", expand=True)
    fields.columns = ["slide_id", "round_number", "version_id", "project_id", "user_id", "scan_region", "channel_id"]
    df_files = pd.concat([df_files, fields], axis=1)
    df_files = df_files[df_files["channel_id"] == "DAPI"].reset_index(drop=True)

    if df_files.empty:
        raise ValueError("no DAPI images found")
    # Select before resizing: one reference image per scene, never query rounds.
    selected = []
    for (slide, scene), group in df_files.groupby(["slide_id", "scan_region"], sort=False):
        if reference_map is not None:
            if slide not in reference_map:
                raise ValueError(f"slide_id {slide!r} not found in reference_map")
            round_id = reference_map[slide]["reference_round"]
            version_id = reference_map[slide]["reference_version"]
        else:
            round_id, version_id = ref_round, ref_version
        matches = group[group["round_number"] == round_id]
        if version_id is not None:
            matches = matches[matches["version_id"] == version_id]
        if len(matches) != 1:
            raise ValueError(
                f"expected one reference DAPI image for {slide}/{scene}, "
                f"round={round_id}, version={version_id}; found {len(matches)}. "
                "Use ref_version or reference_map to select the reference version."
            )
        selected.append(matches)
    df_files = pd.concat(selected, ignore_index=True)

    job_rows = []
    for i, tmp_file in df_files.iterrows():
        print(i)
        os.makedirs(os.path.join(output_folder, "Matrix", tmp_file["folder"]), exist_ok=True)
        os.makedirs(os.path.join(output_folder, "QC", tmp_file["slide_id"]), exist_ok=True)
        os.makedirs(os.path.join(output_folder, "Resized", tmp_file["folder"]), exist_ok=True)

        src = os.path.join(input_path_images, tmp_file["folder"], tmp_file["ofile"])
        resized_path = os.path.join(output_folder, "Resized", tmp_file["folder"], tmp_file["ofile"])
        resize_dapi(src, resized_path, conversion_factor)

        job_rows.append({
            "input_path_image": resized_path,
            "output_path_matrix": os.path.join(output_folder, "Matrix", tmp_file["folder"],
                                                os.path.splitext(tmp_file["ofile"])[0] + ".npy"),
            "output_path_qc": os.path.join(output_folder, "QC", tmp_file["slide_id"], tmp_file["ofile"]),
            "path_model": path_model,
            "model": model_name,
            "pp": pp,
        })

    pd.DataFrame(job_rows).to_csv(output_path_csv, index=False)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cell Segmentation - list jobs.")
    parser.add_argument("--input_path_images", type=str, help="Path to input tiles (path).")
    parser.add_argument("--output_folder", type=str, help="Path to output path to save images (path).")
    parser.add_argument("--ref_round", type=str, help="Only segment this round (e.g. R01). Exclusive with --reference_map_json.")
    parser.add_argument("--ref_version", default=None,
                        help="Reference version (e.g. V01); required if the round has multiple versions.")
    parser.add_argument("--reference_map_json", default=None,
                        help="Per-slide JSON: slide_id -> {reference_round, reference_version}.")
    parser.add_argument("--conversion_factor", type=str, help="Conversion factor (numeric).")
    parser.add_argument("--path_model", type=str, help="Path to segmentation models (path).")
    parser.add_argument("--model_name", type=str, help="Model name (string).")
    parser.add_argument("--output_path_csv", type=str, help="Path to output csv where the job list will be saved (.csv).")
    parser.add_argument("--pp", type=str, help="Indicator for the preprocessing (boolean).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    reference_map = None
    if args.reference_map_json:
        with open(args.reference_map_json, encoding="utf-8") as f:
            reference_map = json.load(f)
    segmentation_job_list(
        input_path_images=args.input_path_images,
        output_folder=args.output_folder,
        ref_round=args.ref_round,
        conversion_factor=args.conversion_factor,
        path_model=args.path_model,
        model_name=args.model_name,
        output_path_csv=args.output_path_csv,
        pp=args.pp,
        ref_version=args.ref_version,
        reference_map=reference_map,
    )
