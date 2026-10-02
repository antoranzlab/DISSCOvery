"""Step 4 - Slide reconstruction (migrated).

Assembles the pseudotiles into the final registered whole-slide images, written
to <project>/output_registration/<scene>/. This is the most
RAM-intensive step: all tiles of a tissue are held in memory at once, so keep
reconstruct.n_cores low.

Reconstruction/QC math preserved verbatim from legacy
additional_codes/generate_final_registered_images.py; only the driver was
rewritten for config + manifest. The AlignQC model is now loaded lazily inside
run() (the original loaded it at import, forcing a 94 MB dependency on import).

Folded in: failures surfaced (3); run_manifest (5); configurable reference
channel (9); top-percentile clip surfaced as config (7).
"""
from __future__ import annotations

import os, sys, json, time, pickle, platform, warnings
from datetime import datetime, timezone

import numpy as np
from ._model_input import pack_pair
from .. import _compat  # noqa: F401  -- numpy alias shim for legacy libs
import tifffile as tiff
from skimage import io
from scipy.signal import convolve2d
from scipy.ndimage import label, find_objects
from multiprocessing import Process

warnings.filterwarnings("ignore")

from ..config import CollageConfig
from ..errors import CollageError, MetadataError, MissingInputError, ConsensusError, ReconstructionError, require_prior_step
from ..ingest import manifest as manifest_mod

# module-level params (set per-run; defaults keep importable WITHOUT tensorflow/model)
model = None
path_to_model = None
tf = None                 # lazily imported in run() (kept out of module import)
convert_to_tensor = None  # lazily imported in run()
top_percentile = 99
do_progress = False
n_cores = 1
script_dir = os.path.dirname(os.path.realpath(__file__))


def range_x1_q(x, q):
    x = np.asfarray(x)
    tmp_median = np.median(x)
    tmp_q_high = np.percentile(x[(x > 0) & (x != tmp_median)], q)
    tmp_q_min = np.percentile(x[(x > 0) & (x != tmp_median)], 100 - q)
    x = (x - tmp_q_min) / (tmp_q_high - tmp_q_min)
    x[x > 1] = 1
    x[x < 0] = 0
    return x

_EVAL_TIME = 0.0   # Phase-3 profiling: total seconds spent in AlignQC scoring
_EVAL_CALLS = 0    # and number of scoring calls, accumulated across all loops


def evaluate_overlap(im_pairs):
    global _EVAL_TIME, _EVAL_CALLS
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
    _t_eval0 = time.time()
    _EVAL_CALLS += 1
    try:
        return _evaluate_overlap_impl(im_pairs)
    finally:
        _EVAL_TIME += time.time() - _t_eval0


def _evaluate_overlap_impl(im_pairs):
    for im_p in im_pairs:
        ref_image = im_p[0]
        query_image = im_p[1]


        ref_image = np.arcsinh(2 ** 16 * ref_image)
        ref_image = range_x1_q(ref_image, 99)
        ref_image = np.squeeze(ref_image)

        query_image = np.arcsinh(2 ** 16 * query_image)
        query_image = range_x1_q(query_image, 99)
        query_image = np.squeeze(query_image)

        # Padding if necessary
        if ref_image.shape[0] % 256 > 0 or ref_image.shape[1] % 256 > 0:
            ref_image = np.pad(ref_image,
                               ((0, 256 - ref_image.shape[0] % 256), (0, 256 - ref_image.shape[1] % 256)),
                               'constant')
            query_image = np.pad(query_image,
                                 ((0, 256 - query_image.shape[0] % 256), (0, 256 - query_image.shape[1] % 256)),
                                 'constant')

        tmp_scores = []
        # Loop through the image in 256x256 tiles
        for tmp_r in range(0, ref_image.shape[0], 256):
            for tmp_c in range(0, ref_image.shape[1], 256):
                try:
                    tmp_query = query_image[tmp_r:tmp_r + 256, tmp_c:tmp_c + 256]
                    tmp_ref = ref_image[tmp_r:tmp_r + 256, tmp_c:tmp_c + 256]

                    # Apply mask and check foreground percentage
                    tmp_mask = (tmp_ref > 0)
                    foreground_percentage = np.mean(tmp_mask)

                    #if foreground_percentage < 0.1:
                    #   continue

                    if np.mean(tmp_ref) == 0:
                        continue

                    # tmp_ref = tmp_ref * tmp_mask
                    # tmp_query = tmp_query * tmp_mask

                    # Combine images to create an RGB image (tmp_qc)
                    tmp_qc = pack_pair(tmp_ref, tmp_query, model)
                    tmp_score = model.predict(tmp_qc[None, ...], verbose=0)
                    tmp_scores.append(tmp_score[0, 0])
                except Exception as e:
                    print(e)
                    tmp_scores.append(0)
                    continue

        if len(tmp_scores) > 0:
            tmp_score = float(np.mean(tmp_scores))
        else:
            tmp_score = 0


    return tmp_score

def get_ref_round(curr_d, reference_round_number, all_t):
    try:
        curr_R = [j for j in curr_d.split('_') if j.startswith('R') and len(j) > 1 and j[1::].isdigit() == True][0]
        curr_V = [j for j in curr_d.split('_') if j.startswith('V') and len(j) > 1 and j[1::].isdigit() == True][0]
        d2find = curr_d.replace('_' + curr_V + '_', '_').replace('_' + curr_R + '_', '_R' + reference_round_number.zfill(2) + '_')
    except:
        return ''
    i_ = ''
    for i in all_t:
        try:
            curr_V = [j for j in i.split('_') if j.startswith('V') and len(j) > 1 and j[1::].isdigit() == True][0]
        except:
            continue
        d2current = i.replace('_' + curr_V + '_', '_')
        if d2find == d2current:
            i_ = i[:]
            break
    return i_

def get_overlaps(done_areas, area2):
    all_overlapping = []
    for area1 in done_areas:
        # Calculate the overlapping area
        overlap_row_min = max(area1[0][0], area2[0][0])
        overlap_row_max = min(area1[0][1], area2[0][1])
        overlap_col_min = max(area1[1][0], area2[1][0])
        overlap_col_max = min(area1[1][1], area2[1][1])

        # Check if there is an overlap
        if overlap_row_min <= overlap_row_max and overlap_col_min <= overlap_col_max:
            overlapping_area = [(overlap_row_min, overlap_row_max), (overlap_col_min, overlap_col_max)]
            all_overlapping.append(overlapping_area)
    return all_overlapping

def export_im(im2_ori_reg, q = 90):
    import numpy as np
    import cv2

    # Define input matrix (im2_ori_reg)
    # Assuming im2_ori_reg is your numpy matrix

    # Calculate the maximum allowable intensity for the output datatype (float32)
    max_intensity = np.finfo(np.float32).max

    # Calculate the 90th percentile intensity
    percentile_90 = np.percentile(im2_ori_reg, q)

    # Apply dynamic intensity transformation
    im_transformed = np.where(im2_ori_reg > percentile_90, max_intensity, 0)

    # Normalize intensities to the range [0, 255]
    im_normalized = ((im_transformed - im_transformed.min()) * (255 / (im_transformed.max() - im_transformed.min()))).astype(np.uint8)

    # Save the transformed matrix as a grayscale JPEG image
    cv2.imwrite('output_image.jpg', im_normalized)


def save_image(f, v_r, ref_round, is_ref_R):
    all_t = [i for i in tile2coor if (tile2coor[i][0][0], tile2coor[i][0][1], tile2coor[i][0][3], tile2coor[i][0][4], tile2coor[i][0][5], tile2coor[i][0][6]) == f]
    j_ = {i:tile2coor[i][1] for i in sorted(all_t)}

    if is_ref_R == False:
        ref_out_im = io.imread(f2corr_Ref_recons[f])
        M2coor = {}
        M2j = {}
        for j1x, j1 in enumerate(j_):
            curr_P, curr_S, M1, curr_R, curr_V, curr_Sl,curr_C = get_R_S_M_C(j1)
            M2coor[M1] = j_[j1]
            M2j[M1] = j1

    nR_max = max([tile2coor[p_][1][0][1] for p_ in all_t])
    nC_max = max([tile2coor[p_][1][1][1] for p_ in all_t])

    R_im  = {i:io.imread(i) for i in all_t}

    if len(set([R_im[i].dtype for i in R_im])) > 1:
        from collections import Counter
        dtype_counts = Counter([str(R_im[i].dtype) for i in R_im])
        print('Different dtypes in images... Doing uint8 to uint16 (check if fits with the actual dtypes)')
        print(dtype_counts)
        for i in R_im:
            if R_im[i].dtype == np.uint8:
                if np.max(R_im[i]) != 0:
                    raise ReconstructionError('Refusing to upcast a non-empty 8-bit image to 16-bit during reconstruction (unexpected real 8-bit data).')
                print('uint8 to uint16:', i)
                R_im[i] = R_im[i].astype(np.uint16)



    _, _, _, _, _, _, curr_C = get_R_S_M_C(list(j_.keys())[0])

    if is_ref_R == False and curr_C == ref_channel:
        M2coor = {}
        M2j = {}
        all_ov = {}
        for j1x, j1 in enumerate(j_):
            curr_P, curr_S, M1, curr_R, curr_V, curr_Sl,curr_C = get_R_S_M_C(j1)
            M2coor[M1] = j_[j1]
            M2j[M1] = j1
            for j2 in j_:
                if j1 == j2:
                    continue
                curr_P, curr_S, M2, curr_R, curr_V, curr_Sl,curr_C = get_R_S_M_C(j2)
                M2coor[M2] = j_[j2]
                M2j[M2] = j2
                if float(M1) > float(M2):
                    continue
                # Find the intersection
                overlap_temp = get_overlaps([j_[j1]], j_[j2])
                if len(overlap_temp) == 0:
                    continue
                n_ = '___'.join(sorted([M1,M2]))
                all_ov[n_] = overlap_temp[0]

        do_again = True
        while do_again == True:
            do_again = False
            all_ov_ = dict(all_ov)
            for ov1x, ov1 in enumerate(all_ov_):
                for ov2x, ov2 in enumerate(all_ov_):
                    if ov1x >= ov2x:
                        continue
                    n_ = '___'.join(sorted(list(set(ov1.split('___') + ov2.split('___')))))
                    if n_ in all_ov:
                        continue
                    overlap_temp = get_overlaps([all_ov[ov1]], all_ov[ov2])
                    if len(overlap_temp) == 0:
                        continue
                    do_again = True
                    all_ov[n_] = overlap_temp[0]

        ov2all_scores = {}
        ov2ims = {}
        for ovx, ov in enumerate(all_ov):
            if '12___13' in ov:
                lol=0
            #else:
            #    continue
            #print('Doing overlap eval', ovx, len(all_ov))
            #rs = {i:np.zeros_like(ref_out_im) for i in ov.split('___')}
            ovs_score = {}
            for i in ov.split('___'):
                i_ = M2j[i]
                rs = np.zeros_like(ref_out_im)
                rs[j_[i_][0][0]:j_[i_][0][1],j_[i_][1][0]:j_[i_][1][1]] = R_im[M2j[i]]
                r1 = rs[all_ov[ov][0][0]:all_ov[ov][0][1], all_ov[ov][1][0]:all_ov[ov][1][1]]
                r2 = ref_out_im[all_ov[ov][0][0]:all_ov[ov][0][1], all_ov[ov][1][0]:all_ov[ov][1][1]]
                if np.max(r1) == 0:
                    ovs_score[i] = 0
                    continue
                non_black_pixels = np.where(r1 != 0)
                r1_ = r1[np.min(non_black_pixels[0]):np.max(non_black_pixels[0])+1, np.min(non_black_pixels[1]):np.max(non_black_pixels[1])+1]
                r2_ = r2[np.min(non_black_pixels[0]):np.max(non_black_pixels[0])+1, np.min(non_black_pixels[1]):np.max(non_black_pixels[1])+1]

                '''
                from PIL import Image
                # Normalize r1 and r2 to range [0, 255] and convert to uint8
                r1_normalized = (r1 / 65535 * 255).astype(np.uint8)
                r2_normalized = (r2 / 65535 * 255).astype(np.uint8)
                
                # Create an empty array for the blue channel with the same shape as r1 and r2
                blue_channel = np.zeros_like(r1_normalized, dtype=np.uint8)
                
                # Stack the channels together to form an RGB image
                rgb_image = np.stack((r1_normalized, r2_normalized, blue_channel), axis=-1)
                
                # Convert the numpy array to an image
                image = Image.fromarray(rgb_image, mode='RGB')
                
                # Save the image as JPG
                image.save('output_image.jpg')
                '''
                r01_tf = convert_to_tensor(r1_, dtype=tf.float32)
                r_ref_tf = convert_to_tensor(r2_, dtype=tf.float32)
                try:
                    ovs_score[i] = evaluate_overlap([(r_ref_tf, r01_tf)])
                except:
                    ovs_score[i] = 0

            ov2ims[ov] = sorted([i for i in ovs_score if ovs_score[i] == max(ovs_score.values())])[0]
            ov2all_scores[ov] = dict(ovs_score)
            #if max(ovs_score.values()) == 0:
            #    print('AI did not work properly')

        pkl_file = os.path.join(output_folder, 'overlap_results', '___'.join(f[0:-1]) + '.pkl')
        os.makedirs(os.path.dirname(pkl_file), exist_ok=True)  # exist_ok: concurrent ref_channel writers across different rounds share this parent dir

        # Write to a temp path then rename: rename is atomic, so a concurrent reader (see
        # is_ref_R==False below) either sees no file yet (and waits) or a fully-written one --
        # never a partially-written pickle.
        tmp_pkl_file = pkl_file + f'.tmp{os.getpid()}'
        with open(tmp_pkl_file, 'wb') as fff:
            pickle.dump(ov2all_scores, fff)
            pickle.dump(ov2ims, fff)
            pickle.dump(all_ov, fff)
        os.replace(tmp_pkl_file, pkl_file)
            #pickle.dump(M2j, fff)
        # ov2all_scores
        # ov2ims
        # all_ov
        # M2j



    R_im_masks = {}
    for i in R_im:
        mask_dir = os.path.join(os.path.dirname(os.path.dirname(i)), 'masks')
        mask_dir_file = os.path.join(mask_dir, os.path.basename(i))
        if os.path.exists(mask_dir_file) == False:
            if [j for j in i.split('_') if j.startswith('R') and len(j) > 1 and j[1::].isdigit() == True][0] in ref_round:
                R_im_masks[os.path.basename(mask_dir_file)] = np.full(R_im[i].shape, True, dtype=bool)
            continue
        R_im_masks[os.path.basename(mask_dir_file)] = io.imread(mask_dir_file)

    if len(set([R_im_masks[i].dtype for i in R_im_masks])) > 1:
        from collections import Counter
        dtype_counts = Counter([str(R_im_masks[i].dtype) for i in R_im_masks])
        print('Different dtypes in images... Doing uint8 to uint16 (check if fits with the actual dtypes)')
        print(dtype_counts)
        for i in R_im_masks:
            if R_im_masks[i].dtype == np.uint8:
                if np.max(R_im_masks[i]) != 0:
                    raise ReconstructionError('Refusing to upcast a non-empty 8-bit image to 16-bit during reconstruction (unexpected real 8-bit data).')
                print('uint8 to uint16:', i)
                R_im_masks[i] = R_im_masks[i].astype(np.uint16)


    R = np.zeros((nR_max, nC_max), R_im[list(R_im.keys())[0]].dtype)

    # Define the number of adjacent pixels (n)
    n = 3  # You can change this to the desired number of adjacent pixels
    # Create a kernel to sum adjacent pixels
    kernel = np.ones((2 * n + 1, 2 * n + 1))

    done_areas = list()
    for xx, i in enumerate(j_):
        #print(xx, len(j_))
        #if 'M126' not in i and 'M127' not in i and 'M112' not in i and 'M113' not in i and 'M147' not in i and 'M147' not in i:
        #    continue
        #if 'M56' not in i and 'M57' not in i and 'M57' not in i and 'M57' not in i:
        #    continue

        #R[j_[i][0][0]:j_[i][0][1],j_[i][1][0]:j_[i][1][1]] = np.maximum(R_im[i], R[j_[i][0][0]:j_[i][0][1],j_[i][1][0]:j_[i][1][1]])

        #### DANGEROUS ADDITION!!!!!
        '''
        # Use convolution to calculate the maximum values among the n adjacent pixels
        conv_R_im = convolve2d(R_im[i], kernel, mode='same', boundary='wrap')

        R[j_[i][0][0]:j_[i][0][1],j_[i][1][0]:j_[i][1][1]][conv_R_im > 0] = 0
        R[j_[i][0][0]:j_[i][0][1],j_[i][1][0]:j_[i][1][1]] = np.maximum(R_im[i], R[j_[i][0][0]:j_[i][0][1],j_[i][1][0]:j_[i][1][1]])
        '''
        ####/DANGEROUS ADDITION!!!!!


        #### DANGEROUS ADDITION_2!!!!!
        lol=0
        row_min, row_max = j_[i][0][0], j_[i][0][1]
        col_min, col_max = j_[i][1][0], j_[i][1][1]

        # Define the new area
        ov_ar = []
        r = R_im[i]
        if os.path.basename(i) in R_im_masks and False:
            r_m = R_im_masks[os.path.basename(i)]
            R_sub = R[j_[i][0][0]:j_[i][0][1],j_[i][1][0]:j_[i][1][1]]

            # R_overall_mask = np.zeros_like(R, dtype=bool)
            # R_overall_mask[j_[i][0][0]:j_[i][0][1], j_[i][1][0]:j_[i][1][1]] = r_m
            # # Find connected components (clusters) and label them
            # labels, num_clusters = label(R_overall_mask)

            labels, num_clusters = label(r_m)
            # Find the bounding box (minrow, maxrow, mincol, maxcol) for each cluster
            cluster_bounding_boxes = find_objects(labels)

            # Iterate through the clusters and print their bounding boxes
            for cluster_num, cluster_indices in enumerate(cluster_bounding_boxes, start=1):
                rows, cols = cluster_indices
                minrow, maxrow, mincol, maxcol = rows.start, rows.stop - 1, cols.start, cols.stop - 1
                ov_ar += get_overlaps(done_areas, [(minrow + row_min, maxrow), (mincol + col_min, maxcol)])
                done_areas.append([(minrow + row_min, maxrow), (mincol + col_min, maxcol)])

            ####r[r_m == False] = R_sub[r_m == False]
        # (mask handling above is disabled by the `and False` guard; when off,
        # nothing happens here and we fall through to the area assignment below.)

        new_area = [(row_min, row_max), (col_min, col_max)]

        #io.imsave('/mnt/D_DRIVE/borrabl/test.tiff', r.astype(np.uint16))
        #io.imsave('/mnt/D_DRIVE/borrabl/test.tiff', R_sub.astype(np.uint16))
        #tiff.imwrite('/mnt/D_DRIVE/borrabl/test_mask.tiff', r_m)
        #tiff.imwrite('/mnt/D_DRIVE/borrabl/test_mask.tiff', R_sub[r_m == False])
        for ov in ov_ar:
            ovl = [(ov[0][0]-row_min, ov[0][1]-row_min), (ov[1][0]-col_min, ov[1][1]-col_min)]
            mR = np.mean(R[ov[0][0]:ov[0][1], ov[1][0]:ov[1][1]])
            mr = np.mean(r[ovl[0][0]:ovl[0][1], ovl[1][0]:ovl[1][1]])
            if mR > mr:
                r[ovl[0][0]:ovl[0][1], ovl[1][0]:ovl[1][1]] = R[ov[0][0]:ov[0][1], ov[1][0]:ov[1][1]]

        do_convolv = False
        if do_convolv:
            # Define the size of the window
            window_size = (10, 10)

            # Define the kernel for convolution
            kernel = np.ones(window_size) / (window_size[0] * window_size[1])

            A = R[j_[i][0][0]:j_[i][0][1], j_[i][1][0]:j_[i][1][1]]
            B = r + 0
            # Perform convolution for matrices A and B
            conv_A = convolve2d(A, kernel, mode='same', boundary='wrap')
            conv_B = convolve2d(B, kernel, mode='same', boundary='wrap')
            R[j_[i][0][0]:j_[i][0][1], j_[i][1][0]:j_[i][1][1]] = np.where(conv_A > conv_B, A, B)
        elif False:
            if np.max(r) == 0:
                continue
            r__ = R[j_[i][0][0]:j_[i][0][1], j_[i][1][0]:j_[i][1][1]]
            r[(r__ > 0) & (r == 0)] = r__[(r__ > 0) & (r == 0)]
            if np.max(r__[r > 0]) > 0 and is_ref_R == False:
                #if 'S0M6' in i:
                #    lol=0
                r___ = ref_out_im[j_[i][0][0]:j_[i][0][1], j_[i][1][0]:j_[i][1][1]]
                # Initialize r01 and r02 with zeros
                r01 = np.zeros_like(r__)
                r02 = np.zeros_like(r)
                r_ref = np.zeros_like(r)

                # Apply the conditions
                r01[(r__ > 0) & (r > 0)] = r__[(r__ > 0) & (r > 0)]
                r02[(r__ > 0) & (r > 0)] = r[(r__ > 0) & (r > 0)]
                r_ref[(r__ > 0) & (r > 0)] = r___[(r__ > 0) & (r > 0)]

                r01_tf = convert_to_tensor(r01, dtype=tf.float32)
                r02_tf = convert_to_tensor(r02, dtype=tf.float32)
                r_ref_tf = convert_to_tensor(r_ref, dtype=tf.float32)

                score_r01 = evaluate_overlap([(r_ref_tf, r01_tf)])
                score_r02 = evaluate_overlap([(r_ref_tf, r02_tf)])

                if score_r01 > score_r02:
                    r[(r__ > 0) & (r > 0)] = r__[(r__ > 0) & (r > 0)]
                    r[(r__ > 0) & (r == 0)] = r__[(r__ > 0) & (r == 0)]


            R[j_[i][0][0]:j_[i][0][1], j_[i][1][0]:j_[i][1][1]] = r
        else:
            R[j_[i][0][0]:j_[i][0][1], j_[i][1][0]:j_[i][1][1]] = R_im[i]


            '''
            import matplotlib.pyplot as plt
            import mplcursors
                        
            # Create a plot
            fig, ax = plt.subplots()
            cax = ax.imshow(r___*5, cmap='viridis')
            
            # Add a color bar
            fig.colorbar(cax)
            
            # Add mplcursors for interactivity
            cursor = mplcursors.cursor(cax, hover=True)
            
            @cursor.connect("add")
            def on_add(sel):
                i, j = int(sel.target[1]), int(sel.target[0])  # Note: sel.target returns (y, x)
                sel.annotation.set_text(f'({i}, {j})\nValue: {r[i, j]:.2f}')
            
            # Show the plot
            plt.show()
            '''


        ####DANGEROUS ADDITION_2!!!!!

    if is_ref_R == False:
        pkl_file = os.path.join(output_folder, 'overlap_results', '___'.join(f[0:-1]) + '.pkl')
        # This pkl is written by this same (P,S,R,V,Sl) group's ref_channel (DAPI) call, above --
        # concurrent sibling-channel processes (FITC/TRITC/CY5/AF) can reach this read before that
        # write lands, since dispatch order across `unique_recons` is not guaranteed to run the
        # ref_channel entry first. Wait for it rather than fail outright.
        _wait_start = time.time()
        while not os.path.exists(pkl_file):
            if time.time() - _wait_start > 600:
                raise TimeoutError(
                    f"Timed out after 600s waiting for {pkl_file} -- the ref_channel "
                    f"({ref_channel}) reconstruction for this (project, scene, round, version, "
                    f"slide) group never completed it."
                )
            time.sleep(1)
        with open(pkl_file, 'rb') as fff:
            ov2all_scores = pickle.load(fff)
            ov2ims = pickle.load(fff)
            all_ov = pickle.load(fff)
            #M2j = pickle.load(fff)
        n_tile_over = {i:len(i.split('___')) for i in ov2ims}
        for ov in sorted(n_tile_over, key=lambda k: n_tile_over[k], reverse=False):
            f_ov = ov2ims[ov]
            if f_ov not in M2j:
                print('f_ov not found in M2j', f_ov, ov)
                continue
            i_ = M2j[f_ov]
            rs = np.zeros_like(ref_out_im)
            rs[j_[i_][0][0]:j_[i_][0][1], j_[i_][1][0]:j_[i_][1][1]] = R_im[M2j[f_ov]]
            n_ = rs[all_ov[ov][0][0]:all_ov[ov][0][1], all_ov[ov][1][0]:all_ov[ov][1][1]]
            R[all_ov[ov][0][0]:all_ov[ov][0][1], all_ov[ov][1][0]:all_ov[ov][1][1]] = n_

        for ov in sorted(n_tile_over, key=lambda k: n_tile_over[k], reverse=False):
            if np.min(R[all_ov[ov][0][0]:all_ov[ov][0][1], all_ov[ov][1][0]:all_ov[ov][1][1]]) == 0:
                d_ = sorted(ov2all_scores[ov], key=lambda k: ov2all_scores[ov][k], reverse=True)
                for f_ov in d_:
                    if f_ov not in M2j:
                        print('f_ov not found in M2j (2)', f_ov, ov)
                        continue
                    i_ = M2j[f_ov]
                    rs = np.zeros_like(ref_out_im)
                    rs[j_[i_][0][0]:j_[i_][0][1], j_[i_][1][0]:j_[i_][1][1]] = R_im[M2j[f_ov]]
                    n_ = rs[all_ov[ov][0][0]:all_ov[ov][0][1], all_ov[ov][1][0]:all_ov[ov][1][1]]
                    r_posi = R[all_ov[ov][0][0]:all_ov[ov][0][1], all_ov[ov][1][0]:all_ov[ov][1][1]]
                    r_posi[r_posi == 0] = n_[r_posi == 0]
                    R[all_ov[ov][0][0]:all_ov[ov][0][1], all_ov[ov][1][0]:all_ov[ov][1][1]] = r_posi
                    if np.min(R[all_ov[ov][0][0]:all_ov[ov][0][1], all_ov[ov][1][0]:all_ov[ov][1][1]]) > 0:
                        break








    '''
    # Find the coordinates of non-zero elements
    t_ = np.sum(R, 1)
    t__ = np.sum(R, 0)

    # Find the minimum and maximum row and column indices
    min_row, max_row = min(np.where(t_)[0]), max(np.where(t_)[0])
    min_col, max_col = min(np.where(t__)[0]), max(np.where(t__)[0])

    R = R[min_row:max_row + 1, min_col:max_col + 1]
    '''

    folder_ = os.path.join(folder_reg, f[4] + '_' + f[2] + '_' + v_r + '_' + f[0] + '_' + f[1])

    try:
        if not os.path.exists(folder_):
            os.makedirs(folder_)
    except:
        pass

    file_path = os.path.join(folder_, f[4] + '_' + f[2] + '_' + v_r + '_' + f[0] + '_' + f[1] + '_' + f[5] + '.tiff')
    tiff.imwrite(file_path, R)
    #print(file_path)
    #tiff.imwrite(file_path, R.astype(np.uint8))



    '''
    # Find rows and columns with at least one non-zero element
    non_zero_rows = np.any(R != 0, axis=1)
    non_zero_cols = np.any(R != 0, axis=0)
    
    # Filter the matrix to keep only non-zero rows and columns
    filtered_matrix = R[non_zero_rows][:, non_zero_cols]
    io.imsave('/mnt/D_DRIVE/borrabl/test_02.tiff', filtered_matrix)
    '''

def get_R_S_M_C(f):
    curr_S = [j.split('M')[0] for j in f.replace('.json','').split('_') if j.startswith('S') and len(j) > 1 and j.replace('S', '').replace('M', '').isdigit() == True and 'M' in j][0]
    curr_S_raw = [j for j in f.replace('.json','').split('_') if j.startswith('S') and len(j) > 1 and j.replace('S', '').replace('M', '').isdigit() == True and 'M' in j][0]
    curr_M = [j.split('M')[1] for j in f.replace('.json','').split('_') if j.startswith('S') and len(j) > 1 and j.replace('S', '').replace('M', '').isdigit() == True and 'M' in j][0]
    curr_R = [j for j in f.replace('.json','').split('_') if j.startswith('R') and len(j) > 1 and j[1::].isdigit() == True][0]
    curr_V = [j for j in f.replace('.json','').split('_') if j.startswith('V') and len(j) > 1 and j[1::].isdigit() == True][0]
    curr_Sl = f.split('_' + curr_R)[0]
    try:
        curr_C = f.split(curr_S_raw + '_')[1].split('.')[0]
    except:
        curr_C = ''
    curr_P = f.split('_'+ curr_V + '_')[1].split('_' + curr_S)[0]

    return curr_P, curr_S, curr_M, curr_R, curr_V, curr_Sl,curr_C






def _json_safe(o):
    """Coerce run-manifest values JSON can't handle (sets, numpy scalars)."""
    import numpy as _np
    if isinstance(o, set):
        return sorted(o)
    if isinstance(o, _np.integer):
        return int(o)
    if isinstance(o, _np.floating):
        return float(o)
    if isinstance(o, _np.ndarray):
        return o.tolist()
    return str(o)


def run(cfg: CollageConfig) -> None:
    global folder_tiles, output_folder, n_cores, output_pseudotiles
    global project_folder_milan_tool, ref_channel, folder_reg, output_coor_path
    global path_to_model, model, top_percentile, do_progress
    global tf, convert_to_tensor
    # Driver-computed values read as globals by the (module-level) helper
    # functions; must be declared global now that the driver lives in run().
    global f2corr_Ref_recons, tile2coor

    rc = cfg.reconstruct if isinstance(cfg.reconstruct, dict) else {}

    folder_tiles = cfg.input_dir
    output_folder = cfg.output_reg
    output_pseudotiles = cfg.output_pseudotiles
    project_folder_milan_tool = cfg.project_dir
    ref_channel = rc.get("ref_channel", "DAPI")
    n_cores = int(rc.get("n_cores", 1))   # keep LOW: this step is RAM-heavy
    top_percentile = int(rc.get("top_percentile", 99))
    do_progress = False
    path_to_model = cfg.model_path

    # Precondition: step 3 (pseudotiles) must have completed (O(1) manifest check).
    require_prior_step(cfg.step_manifest_path(3),
                       step="4 (reconstruct)", prior="3 (pseudotiles)")

    if not os.path.exists(path_to_model):
        raise FileNotFoundError(
            f"AlignQC model not found at {path_to_model}. Run "
            f"scripts/download_model.py before reconstruction."
        )
    # Lazy model load (kept out of module import on purpose).
    from collage.steps._tf_env import quiet_tf
    quiet_tf()
    from tensorflow.keras.models import load_model
    import tensorflow as tf
    from tensorflow import convert_to_tensor
    global _EVAL_TIME, _EVAL_CALLS
    _EVAL_TIME = 0.0
    _EVAL_CALLS = 0
    _t_load0 = time.time()
    model = load_model(path_to_model)
    _model_load_sec = round(time.time() - _t_load0, 1)

    _t_start = time.time()

    folder_reg = os.path.join(project_folder_milan_tool, 'output_registration')

    script_dir = os.path.dirname(os.path.realpath(__file__))

    all_folders = [f for f in os.listdir(folder_tiles)
                   if any(p.startswith('R') and len(p) > 1 and p[1:].isdigit()
                          for p in f.split('_'))]

    output_coor_path = os.path.join(output_folder, 'stitching_coords')


    all_pseudo = [d for d in os.listdir(output_pseudotiles)
                  if os.path.isdir(os.path.join(output_pseudotiles, d))]

    coor_f = [i for i in os.listdir(output_coor_path) if i.endswith('.json')]

    #/mnt/black_NAS/MILAN/shared/3d_stitching/kidney_project/output_pseudotiles/KID1_R15_V2_KIDNEY_YVH_S1M/final/KID1_R15_V1_KIDNEY_YVH_S1M14_DAPI.tiff
    #/mnt/black_NAS/MILAN/shared/3d_stitching/kidney_project/output_pseudotiles/KID1_R15_V2_KIDNEY_YVH_S1M/final/KID1_R15_V2_KIDNEY_YVH_S1M14_DAPI.tiff
    top_percentile = 99

    c2p = {c: None for c in range(n_cores)}
    c2file = {c: None for c in range(n_cores)}
    generic_coor_dict = dict()
    tile2coor = dict()
    unique_recons = set()
    f2v_r = {}
    for fx, f in enumerate(coor_f):
        j_ = json.load(open(os.path.join(output_coor_path, f)))
        folder_r1 = os.path.join(folder_tiles, f.split('.json')[0])
        for t in j_:
            curr_P, curr_S, curr_M, curr_R, curr_V, curr_Sl,curr_C = get_R_S_M_C(t)
            generic_coor_dict[(curr_P, curr_S, curr_M, curr_Sl )] = j_[t]
            p_ = os.path.join(folder_r1, t)
            tile2coor[p_] = [(curr_P, curr_S, curr_M, curr_R, curr_V, curr_Sl,curr_C), j_[t]]
            unique_recons.add((curr_P, curr_S, curr_R, curr_V, curr_Sl,curr_C))
        for t in os.listdir(folder_r1):
            if t.endswith('tiff') == False:
                continue
            p_ = os.path.join(folder_r1,t)
            curr_P, curr_S, curr_M, curr_R, curr_V, curr_Sl,curr_C = get_R_S_M_C(t)
            tile2coor[p_] = [(curr_P, curr_S, curr_M, curr_R, curr_V, curr_Sl,curr_C), generic_coor_dict[(curr_P, curr_S, curr_M, curr_Sl)]]
            unique_recons.add((curr_P, curr_S, curr_R, curr_V, curr_Sl,curr_C))

            f2v_r[(curr_P, curr_S, curr_R, curr_V, curr_Sl,curr_C)] = curr_V

    ref_round = set()
    for t in coor_f:
        try:
            curr_P, curr_S, curr_M, curr_R, curr_V, curr_Sl, curr_C = get_R_S_M_C(t)
        except:
            continue
        ref_round.add(curr_R)


    for ps in all_pseudo:
        for t in os.listdir(os.path.join(output_pseudotiles, ps, 'final')):
            p_ = os.path.join(output_pseudotiles, ps, 'final',t)
            curr_P, curr_S, curr_M, curr_R, curr_V, curr_Sl,curr_C = get_R_S_M_C(t)

            try:
                tile2coor[p_] = [(curr_P, curr_S, curr_M, curr_R, curr_V, curr_Sl,curr_C), generic_coor_dict[(curr_P, curr_S, curr_M, curr_Sl)]]
            except:
                continue
            unique_recons.add((curr_P, curr_S, curr_R, curr_V, curr_Sl,curr_C))


            if curr_R in ref_round:
                f2v_r[(curr_P, curr_S, curr_R, curr_V, curr_Sl, curr_C)] = curr_V
            elif (curr_P, curr_S, curr_R, curr_V, curr_Sl,curr_C) not in f2v_r:
                # Match the ONE input folder that is this tile's own (round, version)
                # counterpart. Without the curr_V_ == curr_V check, every input folder
                # sharing just (P, S, Sl, R) matches regardless of its OWN version --
                # harmless with a single version per round (at most one match), but
                # with multiple version folders for the same round this walks all of
                # them and raises a spurious "inconsistent version" error even though
                # the reconstruction key already disambiguates by curr_V.
                for f_ in all_folders:
                    try:
                        curr_P_, curr_S_, curr_M_, curr_R_, curr_V_, curr_Sl_, curr_C_ = get_R_S_M_C(f_)
                    except:
                        continue
                    if (curr_P_ == curr_P and curr_S_ == curr_S and curr_Sl_ == curr_Sl
                            and curr_R_ == curr_R and curr_V_ == curr_V):
                        if (curr_P, curr_S, curr_R, curr_V, curr_Sl,curr_C) in f2v_r:
                            if curr_V_ != f2v_r[(curr_P, curr_S, curr_R, curr_V, curr_Sl,curr_C)]:
                                raise ReconstructionError('Inconsistent V (version) token across two tiles of the same reconstruction key.')
                        f2v_r[(curr_P, curr_S, curr_R, curr_V, curr_Sl,curr_C)] = curr_V_

    # Matched by round NUMBER only (f[2] in ref_round), not round+version: a
    # non-reference VERSION of the reference ROUND (e.g. reference is
    # R01_V01, but R01_V02 also exists as its own real, non-reference
    # round/version) would otherwise ALSO be treated as "the" reference here,
    # so every query gets mapped twice -- once per reference-round entry --
    # tripping the duplicate-mapping check below. Skip anything that isn't
    # the actual configured reference version (same fix as step 3's
    # oris_/SEC_ construction; cfg.reference_version is only the global
    # default, not override-aware, matching this function's existing
    # round-only handling elsewhere).
    _reference_version = cfg.reference_version
    f2corr_Ref_recons = {}
    for f in unique_recons:
        if f[2] not in ref_round:
            continue
        if _reference_version is not None and f[3] != _reference_version:
            continue
        v_r = f2v_r[f]
        folder_ = os.path.join(folder_reg, f[4] + '_' + f[2] + '_' + v_r + '_' + f[0] + '_' + f[1])
        file_path = os.path.join(folder_, f[4] + '_' + f[2] + '_' + v_r + '_' + f[0] + '_' + f[1] + '_' + f[5] + '.tiff')
        for f2 in unique_recons:
            if f2[2] in ref_round:
                continue
            if f2[0] == f[0] and f2[1] == f[1] and f2[4] == f[4] and f2[5] == f[5]:
                if f2 in f2corr_Ref_recons:
                    raise ReconstructionError('Duplicate reference-reconstruction mapping (should not exist).')
                f2corr_Ref_recons[f2] = file_path


    unique_recons = sorted(unique_recons, key=lambda x: (x[2], x[5] != ref_channel))

    cont_rec = 0
    for fx, f in enumerate(unique_recons):
        #continue

        #if 'DAPI' not in ' '.join(f):
        #    continue
        if f[2] not in ref_round:
            continue
        cont_rec += 1
        print('Doing reconstruction', f, cont_rec, len(unique_recons))
        if do_progress == True:
            ws = aux_func.send_task_evolution(ws, int(cont_rec / len(unique_recons) * 1000) / 10, ind_, server_id)
        v_r = f2v_r[f]
        save_image(f, v_r, ref_round, True)




    # ref_channel entries first: the ref_channel (DAPI) call for a given (P,S,R,V,Sl) group
    # computes and writes the overlap-scoring pkl that its sibling channels (FITC/TRITC/CY5/AF)
    # read back below -- unique_recons is a set, so its default iteration order doesn't guarantee
    # that, and processing a sibling before its own ref_channel entry would make it wait (n_cores>1)
    # or hang (n_cores==1, nothing else running to ever produce the file) on a file that doesn't exist yet.
    for fx, f in enumerate(sorted(unique_recons, key=lambda x: x[-1] != ref_channel)):
        #if 'R012222' not in f[2]:
        #   continue
        #if 'R09' not in f[2]:
        #    continue
        #if 'WP' not in ' '.join(f):
        #    continue
        #if 'DAPI' not in ' '.join(f):
        #    continue
        #if f[-1] != 'DAPI' or f[2] != 'R02' or f[4] != 'GC16BT' or f[1] != 'S0': #GC15BT_R01_V01_S0_DAPI
        #   continue
        if f[2] in ref_round:
            continue
        cont_rec += 1
        print('Doing reconstruction', f, cont_rec, len(unique_recons))
        if do_progress == True:
            ws = aux_func.send_task_evolution(ws, int(cont_rec / len(unique_recons) * 1000) / 10, ind_, server_id)

        v_r = f2v_r[f]


        if n_cores == 1:
            save_image(f, v_r, ref_round, False)
        else:

            while True:
                time.sleep(0.1)

                c_core = -1
                for c in c2p:
                    if type(c2p[c]) == type(None):
                        c_core = c + 0
                        break
                    elif c2p[c].is_alive() == False:
                        #print('Done ', c2file[c])
                        c_core = c + 0
                        break

                if c_core != -1:
                    break  # GC38BT_R03_V01_CODEX_JP_S0M

            p = Process(target=save_image,
                        args=(f,v_r,ref_round,False,))
            p.start()
            c2p[c_core] = p
            c2file[c_core] = f
            continue


    # Fix: the legacy parallel join loop was dead (commented out), so workers
    # could be left unfinished when n_cores > 1. Join any started workers here.
    try:
        for _c, _p in list(c2p.items()):
            if _p is not None and hasattr(_p, "join"):
                _p.join()
    except NameError:
        pass

    _outdir = os.path.join(project_folder_milan_tool, "output_registration")
    _n = 0
    if os.path.isdir(_outdir):
        for _root, _dirs, _files in os.walk(_outdir):
            _n += len([x for x in _files if x.lower().endswith((".tiff", ".tif"))])
    _rm = {
        "step": "4_reconstruct",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "reference_round": cfg.reference_round, "ref_channel": ref_channel,
        "n_cores": n_cores, "top_percentile": top_percentile,
        "model_profile": {
            "model_load_sec": _model_load_sec,
            "scoring_sec_total": round(_EVAL_TIME, 1),
            "scoring_calls": _EVAL_CALLS,
        },
        "duration_sec": round(time.time() - _t_start, 1),
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
    }
    os.makedirs(output_folder, exist_ok=True)
    with open(os.path.join(output_folder, "run_manifest_step4.json"), "w") as _fh:
        json.dump(_rm, _fh, indent=2, default=_json_safe)
    if _n == 0:
        print("  WARNING: no reconstructed images were written (check the log above).")
    else:
        print(f"  reconstructed images written: {_n}")
    print(f"  run manifest: {os.path.join(output_folder, 'run_manifest_step4.json')}")
    print(f"  model profile: load {_model_load_sec}s, "
          f"scoring {round(_EVAL_TIME, 1)}s over {_EVAL_CALLS} calls")
