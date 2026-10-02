#!/usr/bin/env python
"""Crop FFC-corrected tiles into per-scene (per-tissue-core) folders, applying the STS foreground mask and QUALIFAI QC mask to each tile. Uses plain numpy (row, col) semantics throughout -- the BB CSV's own minr/minc/maxr/maxc directly, matching the convention validated in addons/STS_BB_qc_plots.py and split_scenes_processed.py."""
import argparse
import os
import sys

import numpy as np
import pandas as pd
import tifffile
from PIL import Image
from scipy.ndimage import label as cc_label, binary_fill_holes

# BBs are generated with some padding tolerance around the mask's own connected-component
# extent (~25px), so a BB slightly exceeding the foreground mask's bounds is expected. A
# larger overshoot than that likely means the mask/BB/metadata don't actually correspond.
BB_OVERSHOOT_WARN_THRESHOLD = 25

def load_tile_metadata(input_path_meta, channel_id, conversion_factor_sts, conversion_factor_qc):
    """Read the per-tile metadata CSV and compute tile-center coordinates for one channel."""
    meta = pd.read_csv(input_path_meta)
    meta = meta[meta["tile_filename"].str.endswith(f"{channel_id}.tiff")].reset_index(drop=True)

    px_size = meta["ImagePixelSize"].str.split(",", expand=True).astype(float) / 10
    px_size_x, px_size_y = px_size[0], px_size[1]

    stage_x = meta["StageXPosition"] / px_size_x  # X = column coordinate
    stage_y = meta["StageYPosition"] / px_size_y  # Y = row coordinate

    frame = meta["Frame"].str.split(",", expand=True)
    meta["tile_size_X"] = frame[2].astype(float)
    meta["tile_size_Y"] = frame[3].astype(float)

    meta["tmp_X"] = stage_x - stage_x.min() + meta["tile_size_X"] / 2
    meta["tmp_Y"] = stage_y - stage_y.min() + meta["tile_size_Y"] / 2
    meta["tmp_X_STS"] = np.round(meta["tmp_X"] / conversion_factor_sts)
    meta["tmp_Y_STS"] = np.round(meta["tmp_Y"] / conversion_factor_sts)
    meta["tmp_X_QC"] = np.round(meta["tmp_X"] / conversion_factor_qc)
    meta["tmp_Y_QC"] = np.round(meta["tmp_Y"] / conversion_factor_qc)
    return meta

def largest_component_fill_holes(mask):
    """Keep only the largest connected component of a binary mask, then fill its holes."""
    labeled, n = cc_label(mask)
    if n > 0:
        sizes = np.bincount(labeled.ravel())
        sizes[0] = 0
        mask = np.where(labeled == sizes.argmax(), mask, 0)
    return binary_fill_holes(mask > 0).astype(mask.dtype)

def resize_nearest(mask, shape):
    """Resize a 2D mask to `shape` (rows, cols) using nearest-neighbor interpolation."""
    resized = Image.fromarray(mask).resize((shape[1], shape[0]), Image.NEAREST)
    return np.array(resized)

def _adjust_axis(arr, axis, offset, target_size):
    if offset > 0:
        start = int(round(offset))
        return arr.take(range(start, start + target_size), axis=axis)
    if offset < 0:
        pad = int(round(-offset))
        pad_width = [(0, 0), (0, 0)]
        pad_width[axis] = (pad, pad)
        return np.pad(arr, pad_width, mode="constant", constant_values=0)
    return arr

def reconcile_mask_shape(mask, expected_shape):
    """Centered crop/pad `mask` to `expected_shape` = (rows, cols) -- the foreground mask's actual
    size doesn't always match the tile-grid-derived canvas (seen on a real project, ~460px off).
    Returns (reconciled_mask, offset_rows, offset_cols); a BB against the original mask must be
    shifted by -offset per axis to line up with the returned mask."""
    actual_rows, actual_cols = mask.shape
    expected_rows, expected_cols = expected_shape
    offset_rows = (actual_rows - expected_rows) / 2
    offset_cols = (actual_cols - expected_cols) / 2

    if offset_rows != 0:
        mask = _adjust_axis(mask, 0, offset_rows, expected_rows)
    if offset_cols != 0:
        mask = _adjust_axis(mask, 1, offset_cols, expected_cols)
    return mask, offset_rows, offset_cols

def split_scenes(input_path_tiles, input_path_meta, input_path_bb, input_path_masks_foreground,
                  input_path_masks_qc, channel_id, conversion_factor_qc, conversion_factor_sts,
                  output_path_folder, skip_existing):
    print(f"### input path tiles: {input_path_tiles} ###")
    print(f"### input path metadata: {input_path_meta} ###")
    print(f"### input path bounding boxes: {input_path_bb} ###")
    print(f"### input path foreground mask: {input_path_masks_foreground} ###")
    print(f"### input path qualifai mask: {input_path_masks_qc} ###")
    print(f"### channel identifier: {channel_id} ###")
    print(f"### conversion factor STS: {conversion_factor_sts} ###")
    print(f"### conversion factor QC: {conversion_factor_qc} ###")
    print(f"### output directory: {output_path_folder} ###")
    print(f"### skip existing: {skip_existing} ###")

    conversion_factor_sts = float(conversion_factor_sts)
    conversion_factor_qc = float(conversion_factor_qc)

    os.makedirs(output_path_folder, exist_ok=True)

    tile_folder_name = os.path.basename(input_path_tiles.rstrip("/"))
    slide_id, round_id, version_id, project_id, user_id = tile_folder_name.split("_")[:5]

    tmp_csv_meta = load_tile_metadata(input_path_meta, channel_id, conversion_factor_sts, conversion_factor_qc)
    tile_size_x = tmp_csv_meta["tile_size_X"].iloc[0]
    tile_size_y = tmp_csv_meta["tile_size_Y"].iloc[0]

    bb_df = pd.read_csv(input_path_bb)  # columns: minr, minc, maxr, maxc, scan_region

    mask_foreground_full = tifffile.imread(input_path_masks_foreground)
    mask_foreground_full = (mask_foreground_full > 0).astype(np.uint8)

    expected_rows = round((tmp_csv_meta["tmp_Y_STS"] + tile_size_y / conversion_factor_sts / 2).max())
    expected_cols = round((tmp_csv_meta["tmp_X_STS"] + tile_size_x / conversion_factor_sts / 2).max())
    mask_foreground_full, offset_rows, offset_cols = reconcile_mask_shape(
        mask_foreground_full, (expected_rows, expected_cols)
    )
    if offset_rows != 0 or offset_cols != 0:
        print(f"  reconciling foreground mask shape: offset_rows={offset_rows}, offset_cols={offset_cols}")
        bb_df["minr"] -= offset_rows
        bb_df["maxr"] -= offset_rows
        bb_df["minc"] -= offset_cols
        bb_df["maxc"] -= offset_cols
        bb_df = bb_df[(bb_df["minr"] >= 0) & (bb_df["minc"] >= 0)].reset_index(drop=True)

    # force the QC mask to the exact QC-resolution canvas size implied by the (now reconciled)
    # foreground mask, rather than trusting its own on-disk shape -- eliminates the same class
    # of model-output-size mismatch for the QC mask
    mask_qc_full = tifffile.imread(input_path_masks_qc)
    mask_qc_full = (mask_qc_full > 0).astype(np.uint8)
    qc_target_shape = (
        round(mask_foreground_full.shape[0] * conversion_factor_sts / conversion_factor_qc),
        round(mask_foreground_full.shape[1] * conversion_factor_sts / conversion_factor_qc),
    )
    if mask_qc_full.shape != qc_target_shape:
        mask_qc_full = resize_nearest(mask_qc_full, qc_target_shape)

    for j, bb_row in bb_df.iterrows():
        print(j)

        overshoot = max(
            0, -bb_row["minr"], -bb_row["minc"],
            bb_row["maxr"] - mask_foreground_full.shape[0],
            bb_row["maxc"] - mask_foreground_full.shape[1],
        )
        if overshoot > BB_OVERSHOOT_WARN_THRESHOLD:
            print(
                f"  WARNING: BB row {j} (scan_region={bb_row['scan_region']}) extends "
                f"{overshoot:.1f}px past the foreground mask's bounds -- more than the "
                f"~{BB_OVERSHOOT_WARN_THRESHOLD}px tolerance expected from BB generation. "
                "This BB is still being clipped to the mask bounds, but an overshoot this "
                "large may mean the mask/BB/metadata don't actually correspond -- worth "
                "checking by hand."
            )

        minr_sts = int(bb_row["minr"])
        minc_sts = int(bb_row["minc"])
        maxr_sts = int(min(bb_row["maxr"], mask_foreground_full.shape[0]))
        maxc_sts = int(min(bb_row["maxc"], mask_foreground_full.shape[1]))

        minr_full = round(minr_sts * conversion_factor_sts)
        maxr_full = round(maxr_sts * conversion_factor_sts)
        minc_full = round(minc_sts * conversion_factor_sts)
        maxc_full = round(maxc_sts * conversion_factor_sts)

        scan_region = bb_row["scan_region"]
        new_folder_name = os.path.join(output_path_folder, f"{tile_folder_name}_{scan_region}M")
        scene_csv_path = os.path.join(new_folder_name, f"{os.path.basename(new_folder_name)}.csv")

        if skip_existing and os.path.exists(scene_csv_path):
            continue

        os.makedirs(new_folder_name, exist_ok=True)

        # tiles whose full-resolution footprint overlaps this BB (tmp_X=col coord, tmp_Y=row coord)
        scene_files = tmp_csv_meta[
            (tmp_csv_meta["tmp_X"] + tmp_csv_meta["tile_size_X"] / 2 >= minc_full)
            & (tmp_csv_meta["tmp_Y"] + tmp_csv_meta["tile_size_Y"] / 2 >= minr_full)
            & (tmp_csv_meta["tmp_X"] - tmp_csv_meta["tile_size_X"] / 2 <= maxc_full)
            & (tmp_csv_meta["tmp_Y"] - tmp_csv_meta["tile_size_Y"] / 2 <= maxr_full)
        ].copy()

        group_sizes = scene_files.groupby("S")["S"].transform("size")
        scene_files = scene_files[group_sizes == group_sizes.max()].copy()

        mosaic_index_set = set("S" + scene_files["S"].astype(str) + "M" + scene_files["M"].astype(str))

        # isolate this BB's own tissue core within the whole-slide foreground mask
        scene_mask_foreground = mask_foreground_full.copy()
        scene_mask_foreground[minr_sts:maxr_sts, minc_sts:maxc_sts] = 0
        scene_mask_foreground = mask_foreground_full - scene_mask_foreground

        # clamped to the mask's own bounds: the BB's tolerance padding (added when the BB was
        # generated) can push the tile-coverage extent slightly outside the mask, e.g. when the
        # BB already spans nearly the whole tissue/mask
        row_min = max(0, round(scene_files["tmp_Y_STS"].min() - tile_size_y / 2 / conversion_factor_sts))
        row_max = min(scene_mask_foreground.shape[0],
                       round(scene_files["tmp_Y_STS"].max() + tile_size_y / 2 / conversion_factor_sts))
        col_min = max(0, round(scene_files["tmp_X_STS"].min() - tile_size_x / 2 / conversion_factor_sts))
        col_max = min(scene_mask_foreground.shape[1],
                       round(scene_files["tmp_X_STS"].max() + tile_size_x / 2 / conversion_factor_sts))
        scene_mask_foreground = scene_mask_foreground[row_min:row_max, col_min:col_max]
        scene_mask_foreground = largest_component_fill_holes(scene_mask_foreground)

        row_min_qc = max(0, round(scene_files["tmp_Y_QC"].min() - tile_size_y / 2 / conversion_factor_qc))
        row_max_qc = min(mask_qc_full.shape[0],
                          round(scene_files["tmp_Y_QC"].max() + tile_size_y / 2 / conversion_factor_qc))
        col_min_qc = max(0, round(scene_files["tmp_X_QC"].min() - tile_size_x / 2 / conversion_factor_qc))
        col_max_qc = min(mask_qc_full.shape[1],
                          round(scene_files["tmp_X_QC"].max() + tile_size_x / 2 / conversion_factor_qc))
        scene_mask_qualifai = mask_qc_full[row_min_qc:row_max_qc, col_min_qc:col_max_qc]

        # renumber M densely (0-indexed); shared mapping so scene_files and the per-scene
        # metadata csv agree on the same "SxMy" component of the output filenames
        m_map = {m: i for i, m in enumerate(sorted(scene_files["M"].unique()))}
        scene_number = int(str(scan_region).replace("S", ""))

        full_meta = pd.read_csv(input_path_meta)
        full_meta["mosaic_index"] = "S" + full_meta["S"].astype(str) + "M" + full_meta["M"].astype(str)
        scene_meta = full_meta[full_meta["mosaic_index"].isin(mosaic_index_set)].copy()
        prefix = f"{slide_id}_{round_id}_{version_id}_{project_id}_{user_id}_" + scene_meta["mosaic_index"] + "_"
        channel_from_filename = [
            fn[len(p):-len(".tiff")] for fn, p in zip(scene_meta["tile_filename"], prefix)
        ]
        scene_meta["S"] = scene_number
        scene_meta["M"] = scene_meta["M"].map(m_map)
        scene_meta["tile_filename"] = (
            f"{slide_id}_{round_id}_{version_id}_{project_id}_{user_id}_"
            + "S" + scene_meta["S"].astype(str) + "M" + scene_meta["M"].astype(str) + "_"
            + pd.Series(channel_from_filename, index=scene_meta.index) + ".tiff"
        )
        scene_meta = scene_meta.drop(columns=["mosaic_index"])

        # Global (whole-slide, full-resolution) pixel offset of this scene's
        # crop -- same gap as split_scenes_processed.py had (computed above
        # as minr_full/minc_full/maxr_full/maxc_full for cropping, then never
        # persisted). Broadcast onto every tile-row here since scene_meta is
        # one row per tile, not per scene; FeatureExtraction.py's
        # --path_split_scenes lookup only reads the first row.
        scene_meta["offset_row"] = minr_full
        scene_meta["offset_col"] = minc_full
        scene_meta["global_minr"] = minr_full
        scene_meta["global_minc"] = minc_full
        scene_meta["global_maxr"] = maxr_full
        scene_meta["global_maxc"] = maxc_full

        scene_meta.to_csv(scene_csv_path, index=False)

        scene_files["S"] = scene_number
        scene_files["M"] = scene_files["M"].map(m_map)
        scene_files["new_filename"] = (
            f"{slide_id}_{round_id}_{version_id}_{project_id}_{user_id}_"
            + "S" + scene_files["S"].astype(str) + "M" + scene_files["M"].astype(str) + f"_{channel_id}.tiff"
        )

        # rebase to the scene's own local coordinate origin
        scene_files["tmp_X_STS"] = (scene_files["tmp_X_STS"] - scene_files["tmp_X_STS"].min()
                                     + tile_size_x / 2 / conversion_factor_sts)
        scene_files["tmp_Y_STS"] = (scene_files["tmp_Y_STS"] - scene_files["tmp_Y_STS"].min()
                                     + tile_size_y / 2 / conversion_factor_sts)
        scene_files["tmp_X_QC"] = (scene_files["tmp_X_QC"] - scene_files["tmp_X_QC"].min()
                                    + tile_size_x / 2 / conversion_factor_qc)
        scene_files["tmp_Y_QC"] = (scene_files["tmp_Y_QC"] - scene_files["tmp_Y_QC"].min()
                                    + tile_size_y / 2 / conversion_factor_qc)

        for _, tmp_tile in scene_files.iterrows():
            tmp_image = tifffile.imread(os.path.join(input_path_tiles, tmp_tile["tile_filename"]))

            row_start = int(tmp_tile["tmp_Y_STS"] - tile_size_y / 2 / conversion_factor_sts)
            row_end = int(min(tmp_tile["tmp_Y_STS"] + tile_size_y / 2 / conversion_factor_sts,
                               scene_mask_foreground.shape[0]))
            col_start = int(tmp_tile["tmp_X_STS"] - tile_size_x / 2 / conversion_factor_sts)
            col_end = int(min(tmp_tile["tmp_X_STS"] + tile_size_x / 2 / conversion_factor_sts,
                               scene_mask_foreground.shape[1]))
            tile_foreground_mask = scene_mask_foreground[row_start:row_end, col_start:col_end]

            row_start_qc = int(tmp_tile["tmp_Y_QC"] - tile_size_y / 2 / conversion_factor_qc)
            row_end_qc = int(tmp_tile["tmp_Y_QC"] + tile_size_y / 2 / conversion_factor_qc)
            col_start_qc = int(tmp_tile["tmp_X_QC"] - tile_size_x / 2 / conversion_factor_qc)
            col_end_qc = int(tmp_tile["tmp_X_QC"] + tile_size_x / 2 / conversion_factor_qc)
            tile_qc_mask = scene_mask_qualifai[row_start_qc:row_end_qc, col_start_qc:col_end_qc]

            tile_foreground_mask = resize_nearest(tile_foreground_mask, tmp_image.shape)
            tile_qc_mask = resize_nearest(tile_qc_mask, tmp_image.shape)

            tmp_image[tile_foreground_mask == 0] = 0
            tmp_image[tile_qc_mask > 0] = 0

            tifffile.imwrite(os.path.join(new_folder_name, tmp_tile["new_filename"]),
                              tmp_image.astype(np.uint16), compression="lzw")

    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Split slides into scenes.")
    parser.add_argument("--input_path_tiles", type=str, help="Path to input tiles (path).")
    parser.add_argument("--input_path_meta", type=str, help="Path to input metadata file (.csv).")
    parser.add_argument("--input_path_bb", type=str, help="Path to input bounding boxes (.csv).")
    parser.add_argument("--input_path_masks_foreground", type=str, help="Path to input foreground mask (.tiff).")
    parser.add_argument("--input_path_masks_qc", type=str, help="Path to input quality masks directory (path).")
    parser.add_argument("--output_path_folder", type=str, help="Path to output directory (path).")
    parser.add_argument("--conversion_factor_sts", type=str, help="Conversion factor for STS (numeric).")
    parser.add_argument("--conversion_factor_qc", type=str, help="Conversion factor for QC (numeric).")
    parser.add_argument("--channel_id", type=str, help="Channel identifier (character).")
    parser.add_argument("--skip_existing", type=lambda v: str(v).lower() in ("yes", "true", "t", "1"),
                         help="Boolean to skip already existing results (boolean).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    split_scenes(
        input_path_tiles=args.input_path_tiles,
        input_path_meta=args.input_path_meta,
        input_path_bb=args.input_path_bb,
        input_path_masks_foreground=args.input_path_masks_foreground,
        input_path_masks_qc=args.input_path_masks_qc,
        channel_id=args.channel_id,
        conversion_factor_qc=args.conversion_factor_qc,
        conversion_factor_sts=args.conversion_factor_sts,
        output_path_folder=args.output_path_folder,
        skip_existing=args.skip_existing,
    )
