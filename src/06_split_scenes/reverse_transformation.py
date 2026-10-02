#!/usr/bin/env python
"""Project a slide's reference-round foreground mask + bounding boxes onto another round, by inverting the stored coarse-registration transform (scale, angle, tvec) -- see undo_transform below for the correct inversion approach (two other approaches were tried and are wrong)."""
import argparse
import os
import sys

import imreg_dft as ird
import numpy as np
import pandas as pd
import tifffile
from skimage.measure import label, regionprops

def filter_small_regions(mask, threshold=0.001):
    """Matches STS_generate_BB.py's filter_small_annotations: drop regions under 0.1% of image area."""
    labeled = label(mask)
    regions = regionprops(labeled)
    min_area = threshold * mask.shape[0] * mask.shape[1]
    keep = np.isin(labeled, [r.label for r in regions if r.area >= min_area])
    return keep

def center_pad_or_crop(moving, target_shape):
    """Center pad/crop `moving` to `target_shape`, matching STS_coarse_registration_imreg.py."""
    height_diff = target_shape[0] - moving.shape[0]
    width_diff = target_shape[1] - moving.shape[1]

    if height_diff > 0:
        moving = np.pad(moving, ((height_diff // 2, height_diff - height_diff // 2), (0, 0)), "constant", constant_values=0)
    elif height_diff < 0:
        crop_top = -height_diff // 2
        crop_bottom = moving.shape[0] + height_diff // 2
        moving = moving[crop_top:crop_bottom, :]

    if width_diff > 0:
        moving = np.pad(moving, ((0, 0), (width_diff // 2, width_diff - width_diff // 2)), "constant", constant_values=0)
    elif width_diff < 0:
        crop_left = -width_diff // 2
        crop_right = moving.shape[1] + width_diff // 2
        moving = moving[:, crop_left:crop_right]

    return moving

# Two other "undo" approaches were tried and are WRONG -- do not revert to either:
# 1. Hand-negating scale/angle/translation via three cv2.warpAffine calls in forward order --
#    wrong because the operations don't commute; inverting a composition requires reversing order.
# 2. Composing the forward transform into one 3x3 matrix and inverting it as a whole -- wrong
#    because ird.transform_img's actual pixel processing isn't equivalent to a fixed-canvas affine matrix.
# Both looked correct against a same-frame mask (deceptively "no transform" ground truth); the real
# check is whether undoing recovers the round's actual native DAPI image from its registered one --
# validated on real MVM data with the three-call fixed-order inversion below.
def undo_transform(img, scale, angle, tvec, order=0):
    """Invert a forward (zoom, rotate, shift) transform via three separate transform_img calls
    in reverse order -- ird.transform_img's own internal order can't be reversed by negating
    parameters in a single call."""
    step1 = ird.transform_img(img, scale=1.0, angle=0.0, tvec=(-tvec[0], -tvec[1]), order=order)
    step2 = ird.transform_img(step1, scale=1.0, angle=-angle, tvec=(0, 0), order=order)
    step3 = ird.transform_img(step2, scale=1.0 / scale, angle=0.0, tvec=(0, 0), order=order)
    return step3

def reverse_transformation(input_path_tm, input_path_masks, input_path_bb, query_native_shape_path,
                            output_path_masks, output_path_bb):
    os.makedirs(os.path.dirname(output_path_masks), exist_ok=True)
    os.makedirs(os.path.dirname(output_path_bb), exist_ok=True)

    tmp_mask = tifffile.imread(input_path_masks) > 0
    tmp_bb = pd.read_csv(input_path_bb)
    query_native_shape = tifffile.imread(query_native_shape_path).shape[:2]

    print(f"loading transform: {input_path_tm}")
    trans = np.load(input_path_tm)
    scale, angle, t0, t1 = trans[0], trans[1], trans[2], trans[3]

    tmp_mask = filter_small_regions(tmp_mask)
    labeled_mask = label(tmp_mask)
    regions = regionprops(labeled_mask)
    if len(regions) != len(tmp_bb):
        print(f"  warning: {len(regions)} connected regions in mask but {len(tmp_bb)} BB rows -- "
              f"mask/BB may already be out of sync upstream")

    # relabel each connected region to its 1-based scan_region index so identity survives the warp
    identity_img = np.zeros(tmp_mask.shape, dtype=np.float64)
    for i, region in enumerate(regions):
        for coord in region.coords:
            identity_img[coord[0], coord[1]] = i + 1

    # undo_transform's intermediate steps stay confined to its input's own canvas size; if the
    # target round's native frame is bigger than the reference mask's own shape, content that
    # should land near the edges gets clipped mid-way, before any pad/crop at the very end could
    # save it. Pad to a canvas big enough in both directions *before* undoing, so nothing is lost,
    # then crop down to the exact native shape only at the very end.
    working_shape = (
        max(identity_img.shape[0], query_native_shape[0]),
        max(identity_img.shape[1], query_native_shape[1]),
    )
    identity_img = center_pad_or_crop(identity_img, working_shape)

    transformed_identity = undo_transform(identity_img, scale, angle, (t0, t1), order=0)
    # undo the center pad/crop applied to the query during forward registration
    transformed_identity = center_pad_or_crop(transformed_identity, query_native_shape)

    transformed_mask = (transformed_identity > 0).astype(np.uint8) * 255
    tifffile.imwrite(output_path_masks, transformed_mask, compression="lzma")

    new_bb = []
    for i in range(len(regions)):
        label_value = i + 1
        region_mask = np.isclose(transformed_identity, label_value)
        if not region_mask.any():
            print(f"  scan_region S{i} lost entirely after transform, dropping")
            continue
        transformed_regions = regionprops(region_mask.astype(np.uint8))
        min_row, min_col, max_row, max_col = transformed_regions[0].bbox
        new_bb.append({
            "minr": min_row, "minc": min_col, "maxr": max_row, "maxc": max_col,
            "scan_region": tmp_bb.iloc[i]["scan_region"] if i < len(tmp_bb) else f"S{i}",
        })

    pd.DataFrame(new_bb).to_csv(output_path_bb, index=False)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Project a reference-round mask/BB onto another round by inverting the stored coarse-registration transform.")
    parser.add_argument("--input_path_tm", type=str, help="Transformation matrix (.npy): [scale, angle, t0, t1].")
    parser.add_argument("--input_path_masks", type=str, help="Foreground mask of the reference round (.tiff).")
    parser.add_argument("--input_path_bb", type=str, help="Bounding boxes of the reference round (.csv).")
    parser.add_argument("--query_native_shape_path", type=str, help="Target round's own hard-stitched DAPI image (.tiff), used only for its native shape.")
    parser.add_argument("--output_path_masks", type=str, help="Output projected mask (.tiff).")
    parser.add_argument("--output_path_bb", type=str, help="Output projected bounding boxes (.csv).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    reverse_transformation(
        input_path_tm=args.input_path_tm,
        input_path_masks=args.input_path_masks,
        input_path_bb=args.input_path_bb,
        query_native_shape_path=args.query_native_shape_path,
        output_path_masks=args.output_path_masks,
        output_path_bb=args.output_path_bb,
    )
