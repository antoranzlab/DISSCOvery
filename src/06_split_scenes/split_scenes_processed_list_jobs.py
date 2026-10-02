#!/usr/bin/env python
"""List split_scenes_processed jobs: one row per tile image found under input_path_images, matched
against a reference-round/version/channel BB file, foreground mask, and QC mask for that slide.
Reference round/version comes from either a single global --ref_round/--ref_version, or a
per-slide --reference_map_json map (see reference_map_slide_round_version.json) -- mutually
exclusive; the latter is the GUI-curated mechanism and should be preferred when slides differ."""
import argparse
import json
import os
import sys

import pandas as pd

def _parse_fields(filename, ext):
    stem = filename[: -len(ext)] if filename.endswith(ext) else os.path.splitext(filename)[0]
    stem = stem.replace("AF_FITC", "AFFITC")
    parts = stem.split("_")
    if len(parts) != 6:
        raise ValueError(f"expected 6 underscore-delimited fields in {filename!r}, got {parts}")
    return dict(zip(["slide_id", "round_id", "version_id", "project_id", "user_id", "channel_id"], parts))

def _resolve_ref(slide_id, ref_round, ref_version, reference_map):
    if reference_map is None:
        return ref_round, ref_version
    if slide_id not in reference_map:
        raise ValueError(f"slide_id {slide_id!r} not found in reference_map")
    ref_info = reference_map[slide_id]
    return ref_info["reference_round"], ref_info["reference_version"]

def _find_ref_file(directory, slide_id, ref_channel, ref_round, ref_version, reference_map):
    slide_ref_round, slide_ref_version = _resolve_ref(slide_id, ref_round, ref_version, reference_map)
    matches = []
    for f in sorted(os.listdir(os.path.join(directory, slide_id))):
        fields = _parse_fields(f, os.path.splitext(f)[1])
        if fields["round_id"] == slide_ref_round and fields["version_id"] == slide_ref_version and fields["channel_id"] == ref_channel:
            matches.append(f)
    return matches

def split_scenes_processed_job_list(input_path_images, input_bb, input_mask_foreground, input_mask_qc,
                                     output_folder, pixel_size_full, pixel_size_qc, pixel_size_sts,
                                     ref_channel, output_path_csv,
                                     ref_round=None, ref_version=None, reference_map=None):
    if reference_map is None and (ref_round is None or ref_version is None):
        raise ValueError("must supply either reference_map, or both ref_round and ref_version")
    if reference_map is not None and (ref_round is not None or ref_version is not None):
        raise ValueError("reference_map and ref_round/ref_version are mutually exclusive")

    print(f"### input path images: {input_path_images} ###")
    print(f"### input path bounding boxes: {input_bb} ###")
    print(f"### input path foreground masks: {input_mask_foreground} ###")
    print(f"### input path qc masks: {input_mask_qc} ###")
    print(f"### output directory: {output_folder} ###")
    print(f"### pixel size (acquired images): {pixel_size_full} ###")
    print(f"### pixel size (quality control): {pixel_size_qc} ###")
    print(f"### pixel size (hard stitching): {pixel_size_sts} ###")
    if reference_map is not None:
        print(f"### reference round/version: per-slide, from reference_map ({len(reference_map)} slides) ###")
    else:
        print(f"### reference round: {ref_round} ###")
        print(f"### reference version: {ref_version} ###")
    print(f"### reference channel: {ref_channel} ###")
    print(f"### output path csv job list: {output_path_csv} ###")

    pixel_size_full = float(pixel_size_full)
    pixel_size_qc = float(pixel_size_qc)
    pixel_size_sts = float(pixel_size_sts)

    conversion_factor_qc = pixel_size_qc / pixel_size_full
    conversion_factor_sts = pixel_size_sts / pixel_size_full

    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(os.path.dirname(output_path_csv), exist_ok=True)

    tmp_folders = sorted(f.name for f in os.scandir(input_path_images) if f.is_dir())

    job_rows = []
    for folder in tmp_folders:
        tile_files = sorted(f for f in os.listdir(os.path.join(input_path_images, folder))
                             if f.endswith(".tif") or f.endswith(".tiff"))
        for ofile in tile_files:
            fields = _parse_fields(ofile, os.path.splitext(ofile)[1])
            slide_id = fields["slide_id"]

            bb_matches = _find_ref_file(input_bb, slide_id, ref_channel, ref_round, ref_version, reference_map)
            if len(bb_matches) != 1:
                raise ValueError(f"number of BB files different from 1 for slide {slide_id} ({ofile}): {bb_matches}")

            fg_matches = _find_ref_file(input_mask_foreground, slide_id, ref_channel, ref_round, ref_version, reference_map)
            if len(fg_matches) != 1:
                raise ValueError(f"number of foreground files different from 1 for slide {slide_id} ({ofile}): {fg_matches}")

            qc_matches = _find_ref_file(input_mask_qc, slide_id, ref_channel, ref_round, ref_version, reference_map)
            if len(qc_matches) != 1:
                raise ValueError(f"number of QC files different from 1 for slide {slide_id} ({ofile}): {qc_matches}")

            job_rows.append({
                "input_path_image": os.path.join(input_path_images, folder, ofile),
                "input_path_bb": os.path.join(input_bb, slide_id, bb_matches[0]),
                "input_path_foreground": os.path.join(input_mask_foreground, slide_id, fg_matches[0]),
                "input_path_qc": os.path.join(input_mask_qc, slide_id, qc_matches[0]),
                "output_path_image": os.path.join(output_folder, slide_id, ofile),
                "conversion_factor_qc": conversion_factor_qc,
                "conversion_factor_sts": conversion_factor_sts,
            })

    pd.DataFrame(job_rows).to_csv(output_path_csv, index=False)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Split scenes processed - list jobs.")
    parser.add_argument("--input_path_images", type=str, help="Path to input tiles (path).")
    parser.add_argument("--input_bb", type=str, help="Path to input bounding boxes (.csv).")
    parser.add_argument("--input_mask_foreground", type=str, help="Path to input foreground mask (.tiff).")
    parser.add_argument("--input_mask_qc", type=str, help="Path to input quality masks directory (path).")
    parser.add_argument("--output_folder", type=str, help="Path to output path to save images (path).")
    parser.add_argument("--pixel_size_full", type=str, help="Pixel size in full resolution (numeric).")
    parser.add_argument("--pixel_size_qc", type=str, help="Pixel size for quality control (numeric).")
    parser.add_argument("--pixel_size_sts", type=str, help="Pixel size for hard stitching (numeric).")
    parser.add_argument("--ref_round", type=str, default=None,
                        help="Reference round (character). Mutually exclusive with --reference_map_json.")
    parser.add_argument("--ref_version", type=str, default=None,
                        help="Reference version (character). Mutually exclusive with --reference_map_json.")
    parser.add_argument("--reference_map_json", type=str, default=None,
                        help=("Path to a JSON file mapping slide_id -> {reference_round, reference_version} "
                              "(see reference_map_slide_round_version.json). Mutually exclusive with "
                              "--ref_round/--ref_version."))
    parser.add_argument("--ref_channel", type=str, help="Reference channel (character).")
    parser.add_argument("--output_path_csv", type=str, help="Path to output csv where the job list will be saved (.csv).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    reference_map = None
    if args.reference_map_json:
        with open(args.reference_map_json, "r", encoding="utf-8") as f:
            reference_map = json.load(f)

    split_scenes_processed_job_list(
        input_path_images=args.input_path_images,
        input_bb=args.input_bb,
        input_mask_foreground=args.input_mask_foreground,
        input_mask_qc=args.input_mask_qc,
        output_folder=args.output_folder,
        pixel_size_full=args.pixel_size_full,
        pixel_size_qc=args.pixel_size_qc,
        pixel_size_sts=args.pixel_size_sts,
        ref_round=args.ref_round,
        ref_version=args.ref_version,
        reference_map=reference_map,
        ref_channel=args.ref_channel,
        output_path_csv=args.output_path_csv,
    )
