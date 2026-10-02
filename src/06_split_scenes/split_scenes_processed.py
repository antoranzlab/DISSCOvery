import argparse
import os
import sys
import numpy as np
import pandas as pd
import tifffile
from PIL import Image
from scipy.ndimage import binary_fill_holes

def split_scenes_processed(input_path_image, input_path_bb, input_path_foreground, input_path_qc, output_path_image, conversion_factor_qc, conversion_factor_hs, skip_existing):
    print(f'### input path tiles: {input_path_image} ###')
    print(f'### input path bounding boxes: {input_path_bb} ###')
    print(f'### input path foreground mask: {input_path_foreground} ###')
    print(f'### input path quality masks directory: {input_path_qc} ###')
    print(f'### output directory: {output_path_image} ###')
    print(f'### conversion factor (quality control): {conversion_factor_qc} ###')
    print(f'### conversion factor (hard stitching): {conversion_factor_hs} ###')
    print(f'### skip existing: {skip_existing} ###')
    
    # Convert conversion factors to float
    conversion_factor_qc = float(conversion_factor_qc)
    conversion_factor_hs = float(conversion_factor_hs)
    
    # Load images and masks
    tmp_image = tifffile.imread(input_path_image)
    tmp_qc = tifffile.imread(input_path_qc)
    tmp_qc[tmp_qc > 0] = 1
    tmp_mask_foreground = tifffile.imread(input_path_foreground)
    tmp_mask_foreground[tmp_mask_foreground > 0] = 1
    # tmp_mask_foreground = binary_fill_holes(tmp_mask_foreground).astype(np.uint8)

    # Load bounding box data and adjust based on conversion factors
    tmp_bb = pd.read_csv(input_path_bb)
    tmp_bb = tmp_bb.assign(
        minr_full=tmp_bb["minr"] * conversion_factor_hs,
        minc_full=tmp_bb["minc"] * conversion_factor_hs,
        maxr_full=tmp_bb["maxr"] * conversion_factor_hs,
        maxc_full=tmp_bb["maxc"] * conversion_factor_hs
    ).assign(
        minr_qc=lambda df: df["minr_full"] / conversion_factor_qc,
        minc_qc=lambda df: df["minc_full"] / conversion_factor_qc,
        maxr_qc=lambda df: df["maxr_full"] / conversion_factor_qc,
        maxc_qc=lambda df: df["maxc_full"] / conversion_factor_qc
    )

    # Process each bounding box
    for j, row in tmp_bb.iterrows():
        print(j)
        
        # Ensure bounding box does not exceed image boundaries
        row['maxr'] = min(row["maxr"], tmp_mask_foreground.shape[0])
        row['maxc'] = min(row["maxc"], tmp_mask_foreground.shape[1])
        row['maxr_full'] = min(row["maxr_full"], tmp_image.shape[0])
        row['maxc_full'] = min(row["maxc_full"], tmp_image.shape[1])
        row['maxr_qc'] = min(row["maxr_qc"], tmp_qc.shape[0])
        row['maxc_qc'] = min(row["maxc_qc"], tmp_qc.shape[1])

        # Construct output path
        output_folder = os.path.dirname(os.path.dirname(output_path_image))
        new_folder_name = os.path.join(output_folder, f"{os.path.basename(os.path.dirname(input_path_image))}_{row['scan_region']}")
        tmp_string = os.path.splitext(os.path.basename(input_path_image))[0].split('_')
        new_file_name = f"{'_'.join(tmp_string[:5])}_{row['scan_region']}_{tmp_string[5]}.tiff"
        
        if skip_existing and os.path.exists(os.path.join(new_folder_name, new_file_name)): continue
        
        os.makedirs(new_folder_name, exist_ok=True)

        # Crop image and masks
        tmp_scene = tmp_image[int(row["minr_full"]):int(row["maxr_full"]), int(row["minc_full"]):int(row["maxc_full"])]
        scene_mask_foreground = tmp_mask_foreground[int(row["minr"]):int(row["maxr"]), int(row["minc"]):int(row["maxc"])]
        
        if isinstance(scene_mask_foreground, np.ndarray): scene_mask_foreground = Image.fromarray(scene_mask_foreground)

        # if scene_mask_foreground.mode == 'L':
        #     scene_mask_foreground = scene_mask_foreground.convert('I')
        
        # Now resize using PIL Image methods
        scene_mask_foreground = scene_mask_foreground.resize((tmp_scene.shape[1], tmp_scene.shape[0]), Image.Resampling.LANCZOS)
        scene_mask_foreground = np.array(scene_mask_foreground)
        
        scene_mask_qc = tmp_qc[int(row["minr_qc"]):int(row["maxr_qc"]), int(row["minc_qc"]):int(row["maxc_qc"])]
        
        if isinstance(scene_mask_qc, np.ndarray): scene_mask_qc = Image.fromarray(scene_mask_qc)

        if scene_mask_qc.mode == 'L':
            scene_mask_qc = scene_mask_qc.convert('I')
        
        # Now resize using PIL Image methods
        scene_mask_qc = scene_mask_qc.resize((tmp_scene.shape[1], tmp_scene.shape[0]), Image.Resampling.LANCZOS)
        scene_mask_qc = np.array(scene_mask_qc)
        
        # Apply masks
        tmp_scene[scene_mask_foreground == 0] = 0
        tmp_scene[scene_mask_qc > 0] = 0

        tmp_scene = tmp_scene.astype('uint16')

        tifffile.imwrite(os.path.join(new_folder_name, new_file_name), tmp_scene, compression='lzma')

        # Global (whole-slide, full-resolution) pixel offset of this scene's
        # crop, so any local (within-scene) pixel/cell coordinate can be
        # converted back to slide-level coordinates via
        # global = local + offset_row/col. Neither this script nor the R
        # original ever persisted this before (verified 2026-09-15) -- only
        # the cropped image was saved, so downstream stages had no way to
        # place a scene's cells (or QC scores, e.g. algnQC) back onto the
        # whole slide without re-deriving it from the upstream STS BB csv.
        coord_csv_path = os.path.join(output_folder, f"{os.path.basename(new_folder_name)}.csv")
        pd.DataFrame([{
            "scan_region": row["scan_region"],
            "offset_row": int(row["minr_full"]),
            "offset_col": int(row["minc_full"]),
            "global_minr": int(row["minr_full"]),
            "global_minc": int(row["minc_full"]),
            "global_maxr": int(row["maxr_full"]),
            "global_maxc": int(row["maxc_full"]),
        }]).to_csv(coord_csv_path, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Splitting slides into scenes (processed).")
    parser.add_argument("--input_path_image", type=str, help="Path to input images (.tiff).")
    parser.add_argument("--input_path_bb", type=str, help="Path to input bounding boxes (.csv).")
    parser.add_argument("--input_path_foreground", type=str, help="Path to input foreground mask (.tiff).")
    parser.add_argument("--input_path_qc", type=str, help="Path to input quality control mask (.tiff).")
    parser.add_argument("--output_path_image", type=str, help="Path to output scene image directory (.tiff).")
    parser.add_argument("--conversion_factor_qc", type=str, help="Conversion factor for quality control images (numeric).")
    parser.add_argument("--conversion_factor_sts", type=float, help="Conversion factor for hard stitched images (numeric).")
    parser.add_argument("--skip_existing", type=str, default="False", help="Boolean to skip already existing results (boolean).")
    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args = parser.parse_args()

input_path_image = args.input_path_image
input_path_bb = args.input_path_bb
input_path_foreground = args.input_path_foreground
input_path_qc = args.input_path_qc
output_path_image = args.output_path_image
conversion_factor_qc = args.conversion_factor_qc
conversion_factor_sts = args.conversion_factor_sts
skip_existing = args.skip_existing.lower() == "true"

split_scenes_processed(input_path_image=input_path_image, input_path_bb=input_path_bb, input_path_foreground=input_path_foreground, input_path_qc=input_path_qc, 
    output_path_image=output_path_image, conversion_factor_qc=conversion_factor_qc, conversion_factor_hs=conversion_factor_sts, skip_existing=skip_existing)
