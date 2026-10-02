#!/usr/bin/env python
"""Merge versions - pixel-level quality-weighted patch selection.

1. Pick the version with the most non-zero pixels as the reference (COLLAGE/split_scenes
   already zero out pixels flagged as problematic, so non-zero count proxies quality).
2. Wherever the reference is 0 but another version is non-zero, recover that pixel from the
   other version(s) (mean of non-zero alternatives if more than one candidate has data).
3. Intensity-match the recovered fill to the reference's local scale first: a linear fit
   (ref ~= a*alt + b) calibrated on the ring of pixels just outside each hole.
4. Feather the patch at the pixel level (alpha ramps 0 at the hole boundary to 1 at
   `feather_px` deep) so the recovered region eases in rather than a hard-edged graft.
   Pixels with no alt data anywhere stay at 0 -- never fabricated.
"""
import argparse
import os
import sys

import numpy as np
import tifffile
from scipy.ndimage import distance_transform_edt

def merge_versions(input_path_registration, input_path_algnqc, output_path_file, feather_px=10):
    print(f"### input path registration: {input_path_registration} ###")
    print(f"### input path algnqc: {input_path_algnqc} ###")
    print(f"### output path merged: {output_path_file} ###")
    print(f"### feather px: {feather_px} ###")

    output_dir = os.path.dirname(output_path_file)
    if not os.path.exists(output_dir):
        print(f"### creating folder: {output_dir} ###")
        os.makedirs(output_dir, exist_ok=True)

    reg_paths = input_path_registration.split(",")

    if len(reg_paths) == 1:
        import shutil
        shutil.copy(reg_paths[0], output_path_file)
        return True

    images = [tifffile.imread(p).astype(np.float64) for p in reg_paths]
    dtype_out = tifffile.imread(reg_paths[0]).dtype

    nonzero_counts = [(img > 0).sum() for img in images]
    ref_idx = int(np.argmax(nonzero_counts))
    ref = images[ref_idx].copy()
    alts = [img for i, img in enumerate(images) if i != ref_idx]

    hole = ref == 0
    if hole.any():
        alt_stack = np.stack(alts)
        alt_zero = alt_stack == 0
        alt_count = (~alt_zero).sum(axis=0)
        recoverable = hole & (alt_count > 0)

        # distance_transform_edt over the full canvas is the dominant cost
        # (~60% of runtime on real MVM tiles) even though feathering only
        # ever uses distances up to feather_px -- and "hole" (ref == 0)
        # typically covers most of the scene as genuine tissue-free
        # background that's never actually recoverable. Restricting both
        # distance transforms to the bounding box of the recoverable region
        # (padded by feather_px, so the true nearest boundary/ring pixels
        # stay inside the crop) skips that wasted work. Deep-hole pixels
        # whose true distance would be truncated by the crop still resolve
        # correctly -- they're far past feather_px either way, so they clip
        # to alpha=1 regardless of the exact (possibly crop-truncated) value.
        if recoverable.any():
            rows = np.where(np.any(recoverable, axis=1))[0]
            cols = np.where(np.any(recoverable, axis=0))[0]
            r0, r1 = max(0, rows[0] - feather_px), min(hole.shape[0], rows[-1] + feather_px + 1)
            c0, c1 = max(0, cols[0] - feather_px), min(hole.shape[1], cols[-1] + feather_px + 1)

            hole_c = hole[r0:r1, c0:c1]
            ref_c = ref[r0:r1, c0:c1]
            alt_stack_c = alt_stack[:, r0:r1, c0:c1]
            alt_zero_c = alt_zero[:, r0:r1, c0:c1]
            alt_count_c = alt_count[r0:r1, c0:c1]
            recoverable_c = recoverable[r0:r1, c0:c1]

            alt_summed_c = np.where(alt_zero_c, 0, alt_stack_c).sum(axis=0)
            alt_fill_c = np.divide(alt_summed_c, alt_count_c, out=np.zeros_like(alt_summed_c), where=alt_count_c > 0)

            dist_outside_c = distance_transform_edt(hole_c)
            dist_from_hole_c = distance_transform_edt(~hole_c)
            outside_ring_c = (~hole_c) & (dist_from_hole_c <= feather_px)

            calib_ref, calib_alt = [], []
            for k in range(alt_stack_c.shape[0]):
                alt_c = alt_stack_c[k]
                m = outside_ring_c & (alt_c > 0)
                calib_ref.append(ref_c[m])
                calib_alt.append(alt_c[m])
            calib_ref = np.concatenate(calib_ref)
            calib_alt = np.concatenate(calib_alt)
            if len(calib_ref) > 200:
                a, b = np.polyfit(calib_alt, calib_ref, 1)
                a = max(a, 0)
            else:
                a, b = 1.0, 0.0
            alt_fill_matched_c = np.clip(a * alt_fill_c + b, 0, np.iinfo(dtype_out).max)

            alpha_c = np.clip(dist_outside_c / feather_px, 0, 1)
            ref_c[recoverable_c] = alpha_c[recoverable_c] * alt_fill_matched_c[recoverable_c]

    tifffile.imwrite(output_path_file, ref.astype(dtype_out), compression="lzw")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge versions.")
    parser.add_argument("--input_path_registration", type=str, help="Comma-separated paths to input registration images (list).")
    parser.add_argument("--input_path_algnqc", type=str, help="Comma-separated paths to input algnqc score csvs (list). Accepted for interface parity, not currently used.")
    parser.add_argument("--output_path_file", type=str, help="Full path to output image (.tiff).")
    parser.add_argument("--feather_px", type=int, default=10, help="Pixel depth over which a recovered patch's intensity ramps in from the hole boundary.")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    merge_versions(
        input_path_registration=args.input_path_registration,
        input_path_algnqc=args.input_path_algnqc,
        output_path_file=args.output_path_file,
        feather_px=args.feather_px,
    )
