"""Step 3 - Pseudotile construction (migrated).

For each reference tile, crops the registered overlapping patches from the moving
rounds and merges them into a "pseudotile" resembling the reference tile but
assembled from pairwise-registered pieces, so every round shares the reference
round's tiling.

Registration/QC math preserved verbatim from legacy
additional_codes/generate_pseudotiles.py; only the driver was rewritten for
config + manifest. The neighbour-stitching helper it calls is vendored in
_neighbour_stitching.py.

Folded in: deterministic seed (1); failures surfaced (3); run_manifest (5);
configurable channels/QC channel (9). Overlap is auto-derived from coordinates.
"""
from __future__ import annotations

import os, sys, copy, json, time, platform, warnings
from datetime import datetime, timezone

import numpy as np
from ._model_input import pack_pair
from .. import _compat  # noqa: F401  -- numpy alias shim for legacy libs
from numpy import array
import pandas as pd
import imreg_dft
import imageio
import tifffile
from scipy import ndimage
from scipy.signal import convolve2d
from skimage import io
from multiprocessing import Process

warnings.filterwarnings("ignore")

from . import _neighbour_stitching as neighbour_stitching
from ._gapfill_service import GapfillPoolService
from ..config import CollageConfig
from ..errors import CollageError, MetadataError, MissingInputError, ConsensusError, ReconstructionError, require_prior_step
from ..ingest import manifest as manifest_mod

# module-level params (set per-run; defaults keep importable)
path_to_model = None
do_QC_Plot = False
do_progress = False  # legacy websocket progress reporting; disabled in the OSS tool
channels = []
channel_meta = "DAPI"
script_dir = os.path.dirname(os.path.realpath(__file__))


def do_basic_reg(central_im_reg, mov_matrix_reg, transform_json):
    out_reg = {'error': True}
    if os.path.isfile(transform_json) == True:
        out_reg = json.load(open(transform_json, 'r'))
        if len(out_reg) == 1:
            flag = False
        else:
            flag = True
        return out_reg, flag

    flag = True
    try:
        out_reg = imreg_dft.imreg.similarity(central_im_reg, mov_matrix_reg)
        out_reg_ = imreg_dft.imreg.translation(central_im_reg, mov_matrix_reg)

        err_x = abs(out_reg['tvec'][0] - out_reg_['tvec'][0])
        err_y = abs(out_reg['tvec'][1] - out_reg_['tvec'][1])
    except Exception as e:
        err_x = 99999;
        err_y = 99999
        print('Error registration for basic_reg', 'Error imreg_dft', e)
        flag = False

    if err_x > 20 or err_y > 20:
        print('inaccurate registration for basic_reg')
        flag = False

    if flag == True:
        del out_reg['timg']
        out_reg['tvec'] = list(out_reg['tvec'])
        json.dump(out_reg, open(transform_json, 'w'))
    else:
        json.dump({'error': True}, open(transform_json, 'w'))

    return out_reg, flag

def zero_inner(image, border_size):
    height, width = image.shape[:2]
    border_height = int(height * border_size)
    border_width = int(width * border_size)

    image[border_height:-border_height, border_width:-border_width] = 0

    return image


def apply_boundary_mask(im2_ori_reg, coor_im2_int):
    min_row, min_col, max_row, max_col = coor_im2_int
    # Create a mask for pixels within the specified boundary
    mask = np.zeros_like(im2_ori_reg)
    mask[min_row:max_row+1, min_col:max_col+1] = 1

    # Apply the mask to the image
    masked_image = im2_ori_reg * mask

    return masked_image

def export_im(im2_ori_reg):
    import numpy as np
    import cv2

    # Define input matrix (im2_ori_reg)
    # Assuming im2_ori_reg is your numpy matrix

    # Calculate the maximum allowable intensity for the output datatype (float32)
    max_intensity = np.finfo(np.float32).max

    # Calculate the 90th percentile intensity
    percentile_90 = np.percentile(im2_ori_reg, 90)

    # Apply dynamic intensity transformation
    im_transformed = np.where(im2_ori_reg > percentile_90, max_intensity, 0)

    # Normalize intensities to the range [0, 255]
    im_normalized = ((im_transformed - im_transformed.min()) * (255 / (im_transformed.max() - im_transformed.min()))).astype(np.uint8)

    # Save the transformed matrix as a grayscale JPEG image
    cv2.imwrite('output_image.jpg', im_normalized)


def generate_pseudotile(t_ori, dir_pseudotile_qc, dir_pseudotile_final, dir_ori, dir_sec, scene2sec_tile, out_json_dir, reg_out, channel, p_overlap_, sec_, channel_QC, gapfill_service=None):
    qc_file = os.path.join(dir_pseudotile_qc, t_ori.replace(R_ori, R_sec).replace(V_ori, V_sec) + '.png')
    final_file = os.path.join(dir_pseudotile_final, t_ori.replace(R_ori, R_sec).replace(V_ori, V_sec))

    im1 = io.imread(os.path.join(dir_ori, t_ori))

    S_ori = [i for i in t_ori.split('_') if i.startswith('S') and 'M' in i and i.replace('S','').replace('M','').isnumeric() == True]
    if len(S_ori) != 1:
        print('Error selecting tile M')
        raise MetadataError('Could not identify a unique S<scene>M<tile> token in the tile filename.')
    S_ori = S_ori[0].split('M')[-1]

    # transdform this in a function. Inputs:
    # - S_ori
    # - out_json_dir

    priority_order = ['imreg_dft', 'cv2', 'aa', 'chi2_no_angle', 'phase_cross_correlation_no_angle',
                      'imreg_dft_no_angle']

    N = 0
    if os.path.exists(out_json_dir) == False:
        print(out_json_dir, 'not found')
        raise MissingInputError('Registration output not found; run step 2 (register) before step 3 (pseudotiles).')

    all_json_involved = [os.path.join(out_json_dir,i) for i in os.listdir(out_json_dir) if i.endswith('.json') and i.startswith('01_'+S_ori + '_')]

    json_2_out_reg = {}
    json_conflict = set()
    json2overlap = {}

    do_AI_consen = True

    if do_AI_consen == True:
        json2score = {}
        base_ = os.path.basename(dir_sec)
        dir_AI = os.path.join(reg_out, 'test_for_consen')
        all_dirs_AI = [i for i in os.listdir(dir_AI) if base_ in i]
        json_2_out_reg = {}
        for j_ in all_json_involved:
            try:
                json_ori = json.load(open(j_,'r'))
            except Exception as e:
                print('Error loading part of pseudotile, could be normal', e)
                continue
            if len(json_ori) == 0:
                continue
            if type(json_ori['method2transl']) == str:
                try:
                    json_ori['method2transl'] = eval(json_ori['method2transl'])
                except:
                    while 'timg' in json_ori['method2transl']:
                        t_t = ", 'timg':" + json_ori['method2transl'].split(", 'timg':")[1].split(')}')[0] + ')'
                        json_ori['method2transl'] = json_ori['method2transl'].replace(t_t, '').replace('dtype=float32', 'dtype=np.float32')

                    json_ori['method2transl'] = eval(json_ori['method2transl'].replace('dtype=float32', 'dtype=np.float32'))


            M = os.path.basename(j_).split('01_')[1].split('_')[0]
            M_ = os.path.basename(j_).split('_02_')[1].split('.json')[0]
            pair = os.path.basename(j_).split('.json')[0]
            curr_AI_dir = []
            for i_ in all_dirs_AI:
                try:
                    M__ = [i for i in i_.split('_') if i.startswith('S') and 'M' in i and i.replace('S', '').replace('M', '').isnumeric() == True][0].split('M')[1]
                    if M__ == M_:
                        curr_AI_dir.append(i_)
                except:
                    continue
            if len(curr_AI_dir) != 1:
                continue
            else:
                dir_AI_final = os.path.join(dir_AI, curr_AI_dir[0])
                for j in os.listdir(dir_AI_final):
                    if j.endswith('.json') == False:
                        continue
                    json_ = json.load(open(os.path.join(dir_AI_final, j),'r'))
                    best_m = ''
                    for m in json_:
                        if m not in json_ori['method2transl']:
                            continue
                        p1 = os.path.basename(json_[m]['path_ref_image'])
                        p2 = os.path.basename(json_[m]['path_query_image'])
                        if '____' + pair + '____' not in p1 or '____' + pair + '____' not in p2:
                            continue
                        if pd.isnull(json_[m]['score']) == True:
                            s_ = 0
                        elif type(json_[m]['score']) == float:
                            s_ = json_[m]['score']
                        else:
                            s_ = 0
                        if j_ not in json2score:
                            best_m = m[:]
                            json2score[j_] = s_
                        elif s_ > json2score[j_]:
                            best_m = m[:]
                            json2score[j_] = s_
                    if len(best_m) == 0:
                        continue
                    json_2_out_reg[j_] = json_ori['method2transl'][best_m]
                    if "timg" in  json_ori['method2transl'][best_m]:
                        del  json_ori['method2transl'][best_m]["timg"]
                    json_2_out_reg[j_]['coor_im1_intersection'] = json_ori['coor_im1_intersection']
                    json_2_out_reg[j_]['coor_im2_intersection'] = json_ori['coor_im2_intersection']
                    json_2_out_reg[j_]['best_method'] = best_m
        sorted_keys_json =  sorted(json2score, key=lambda x: json2score[x], reverse=True)

    if do_AI_consen == False:
        for j_ in all_json_involved:
            json_ = json.load(open(j_,'r'))
            if 'coor_im2_intersection' not in json_:
                continue
            npix = json_['coor_im2_intersection']; npix_ = (npix[1]-npix[0]) * (npix[3]-npix[2])

            json_['method2transl'] = eval(json_['method2transl'])

            mm_final = ''
            mm = 99
            for m1x, m1 in enumerate(priority_order):
                for m2x, m2 in enumerate(priority_order):
                    if m1x >= m2x:
                        continue
                    if m1 not in json_['method2transl'] or m2 not in json_['method2transl']:
                        continue
                    mm12 = min([m1x, m2x])
                    if mm12 > mm:
                        continue
                    if max(json_['method2transl'][m1]['tvec']-json_['method2transl'][m2]['tvec']) < 5:
                        mm = mm12 + 0
                        mm_final = m1[:]
            if mm == 99:
                json_conflict.add(j_)
            else:
                json2overlap[j_] = npix_
                if "timg" in  json_['method2transl'][mm_final]:
                    del  json_['method2transl'][mm_final]["timg"]
                json_2_out_reg[j_] = json_['method2transl'][mm_final]
                json_2_out_reg[j_]['coor_im1_intersection'] = json_['coor_im1_intersection']
                json_2_out_reg[j_]['coor_im2_intersection'] = json_['coor_im2_intersection']

        sorted_keys_json = sorted(json2overlap, key=json2overlap.get, reverse=True)

    if len(json_conflict) > 0:
        print(qc_file)
        print(json_conflict)
        print('Warning: error_pending_to_be_refined_with_stitching')
        for j in json_conflict:
            all_json_involved.remove(j)
        if len(all_json_involved) == 0:
            print('Pseudotile has not a consensus area:', final_file)
            raise ConsensusError('Pseudotile has no consensus registration area: all candidate tile-pairs conflicted.')
    #else:
        #sys.exit()



    if len(sorted_keys_json) == 0:
        print('WARNING: no consensus transforms for', os.path.basename(final_file),
              '- pseudotile will be EMPTY. Check that step 2 wrote consensus JSONs '
              '(test_for_consen/<tile>/method2ia_red_*.json); a missing/failed AlignQC '
              'model in step 2 is the usual cause.')

    j_2coor = dict()
    j_2coor_1 = dict()
    coor_im2_int_all = list()
    coor_im1_int_all = list()
    j_2stich_im = dict()
    j_2stich_im_full = dict()
    j_2rs = dict()
    for j_x, j_ in enumerate(sorted_keys_json):

        s_sec = os.path.basename(j_).split('_')[-1].split('.json')[0]
        im02_name = os.path.join(dir_sec, scene2sec_tile[s_sec])
        im2 = io.imread(im02_name)

        if N > 0:
            im2 = np.pad(im2, pad_width=N, mode='constant', constant_values=0)

        im2_full = im2.copy()

        out_reg = json_2_out_reg[j_]
        coor_im1_int = list(map(int, json_2_out_reg[j_]['coor_im1_intersection']))
        coor_im2_int = list(map(int, json_2_out_reg[j_]['coor_im2_intersection']))

        extend_overlap_xM = min(im2.shape[0] - coor_im1_int[1], im2.shape[0] - coor_im2_int[1])
        coor_im1_int[1] = coor_im1_int[1] + extend_overlap_xM
        coor_im2_int[1] = coor_im2_int[1] + extend_overlap_xM
        extend_overlap_xm = min(coor_im1_int[0], coor_im2_int[0])
        coor_im1_int[0] = coor_im1_int[0] - extend_overlap_xm
        coor_im2_int[0] = coor_im2_int[0] - extend_overlap_xm

        extend_overlap_yM = min(im2.shape[1] - coor_im1_int[3], im2.shape[1] - coor_im2_int[3])
        coor_im1_int[3] = coor_im1_int[3] + extend_overlap_yM
        coor_im2_int[3] = coor_im2_int[3] + extend_overlap_yM
        extend_overlap_ym = min(coor_im1_int[2], coor_im2_int[2])
        coor_im1_int[2] = coor_im1_int[2] - extend_overlap_ym
        coor_im2_int[2] = coor_im2_int[2] - extend_overlap_ym







        im2[:coor_im2_int[0], :] = 0
        im2[coor_im2_int[1]:, :] = 0
        im2[:, :coor_im2_int[2]] = 0
        im2[:, coor_im2_int[3]:] = 0


        ### TRANSFORM IMAGE
        res = [coor_im1_int[0] - coor_im2_int[0], coor_im1_int[2] - coor_im2_int[2]]
        l1 = [-im2.shape[0], 0, im2.shape[0]]
        l2 = [-im2.shape[1], 0, im2.shape[1]]
        r1s = [abs(res[0] - r_) for r_ in l1]
        r1 = l1[r1s.index(min(r1s))]
        r2s = [abs(res[1] - r_) for r_ in l2]
        r2 = l2[r2s.index(min(r2s))]
        j_2rs[j_] = (r1, r2)
        if 'scale' not in out_reg:
            out_reg['scale'] = 0
        if 'angle' not in out_reg:
            out_reg['angle'] = 0

        #if '01_84_02_65' in j_:
        #    lol=0

        im2_ori_reg, d_, is_custom = get_recons_im(im2, out_reg, coor_im1_int, coor_im2_int, im2_full)
        im2_ori_reg[:coor_im1_int[0], :] = 0
        im2_ori_reg[coor_im1_int[1]:, :] = 0
        im2_ori_reg[:, :coor_im1_int[2]] = 0
        im2_ori_reg[:, coor_im1_int[3]:] = 0
        im2_ori_reg_full, d_, is_custom = get_recons_im(im2, out_reg, coor_im1_int, coor_im2_int, im2_full)
        ####im2_ori_reg = imreg_dft.imreg.transform_img(im2, scale=out_reg['scale'], angle=out_reg['angle'], tvec=np.array(out_reg['tvec']) + (r1, r2), bgval=0).astype(im1.dtype)
        ####im2_ori_reg_full = imreg_dft.imreg.transform_img(im2_full, scale=out_reg['scale'], angle=out_reg['angle'], tvec=np.array(out_reg['tvec']) + (r1, r2), bgval=0).astype(im1.dtype)
        #im2_ori_reg = apply_boundary_mask(im2_ori_reg, coor_im2_int)

        do_alpha = True
        if do_alpha == True:
            alpha = 20
            if coor_im1_int[0] + alpha < im2_ori_reg.shape[0]:
                im2_ori_reg[:min(im2_ori_reg.shape[0], coor_im1_int[0] + alpha), :] = 0
            if coor_im1_int[1] - alpha > 0:
                im2_ori_reg[max(0, coor_im1_int[1] - alpha):, :] = 0
            if coor_im1_int[2] + alpha < im2_ori_reg.shape[1]:
                im2_ori_reg[:, :min(im2_ori_reg.shape[1], coor_im1_int[2] + alpha)] = 0
            if coor_im1_int[3] - alpha > 0:
                im2_ori_reg[:, max(0, coor_im1_int[3] - alpha):] = 0


        ###/TRANSFORM IMAGE

        j_2stich_im[j_] = im2_ori_reg
        j_2stich_im_full[j_] = im2_ori_reg_full
        coor_im2_int_all.append(coor_im2_int)
        coor_im1_int_all.append(coor_im1_int)
        j_2coor[j_] = coor_im2_int
        j_2coor_1[j_] = coor_im1_int

        '''
        import matplotlib.pyplot as plt

        # Create a boolean mask where True indicates the element is non-zero
        non_zero_mask = j_2stich_im[j_] > 0
        
        # Create a plot
        plt.figure(figsize=(6, 6))
        plt.imshow(non_zero_mask, cmap='gray', interpolation='none')
        
        # Add color bar for reference
        plt.colorbar(label='Zero (0) and Non-Zero (1)')
        
        # Set the title and labels
        plt.title('Matrix Zero and Non-Zero Elements')
        plt.xlabel('Column Index')
        plt.ylabel('Row Index')
        
        # Show the plot
        plt.show()
        '''


    if 'im2' in locals():
        reg_matrix = np.zeros_like(im2)
        stit_matrix = np.zeros_like(im2)
        overlap_matrix = np.zeros_like(im2)
        mask_reg_matrix = np.zeros_like(im2, dtype=bool)
        tileposi = np.zeros_like(im2).astype(np.uint8) + 99
    else:
        reg_matrix = np.zeros_like(im1)
        stit_matrix = np.zeros_like(im1)
        overlap_matrix = np.zeros_like(im1)
        mask_reg_matrix = np.zeros_like(im1, dtype=bool)
        tileposi = np.zeros_like(im1).astype(np.uint8) + 99

    t_2im = dict()
    for j_x, j_ in enumerate(sorted_keys_json):

        #t_ = j_2stich_im_full[j_].astype(im1.dtype)
        #t_[reg_matrix != 0] = 0
        #reg_matrix[t_!=0] = t_[t_!=0]


        do_convolv = False
        if do_convolv:
            t_ = j_2stich_im[j_].astype(im1.dtype)
            reg_matrix[reg_matrix==0] = t_[reg_matrix == 0]

            # Define the size of the window
            window_size = (5, 5)

            # Define the kernel for convolution
            kernel = np.ones(window_size) / (window_size[0] * window_size[1])

            A = reg_matrix + 0
            B = t_ + 0
            # Perform convolution for matrices A and B
            conv_A = convolve2d(A, kernel, mode='same', boundary='wrap')
            conv_B = convolve2d(B, kernel, mode='same', boundary='wrap')
            reg_matrix = np.where(conv_A > conv_B, A, B)
        elif True:
            t_ = j_2stich_im[j_].astype(im1.dtype)

            if np.max(t_) == 0:
                t_2im[j_] = t_
                continue
            # Find the rows and columns that contain non-zero elements
            non_zero_rows = np.any(t_ != 0, axis=1)
            non_zero_cols = np.any(t_ != 0, axis=0)

            alpha = 20
            # Get the minimum and maximum row indices
            min_row = np.where(non_zero_rows)[0][0] + alpha
            max_row = np.where(non_zero_rows)[0][-1] - alpha

            # Get the minimum and maximum column indices
            min_col = np.where(non_zero_cols)[0][0] + alpha
            max_col = np.where(non_zero_cols)[0][-1] - alpha

            extended_matrix = np.zeros_like(t_)
            extended_matrix[min_row:max_row + 1, min_col:max_col + 1] = t_[min_row:max_row + 1, min_col:max_col + 1]

            t_ = extended_matrix.copy()
            t_2im[j_] = t_
            ##

            #### DANGEROUS ADDITION!!!!!
            try:
                t_[reg_matrix>0] = 0
            except Exception as e:
                print('Error in DANGEROUS ADDITION', e)
                continue
            ###reg_matrix[t_>0] = 0
            mask_reg_matrix[t_>0] = 1
            ####/DANGEROUS ADDITION!!!!!

            reg_matrix = np.maximum(reg_matrix, t_)
            tileposi[t_>0] = j_x
            #tifffile.imwrite(final_file, reg_matrix)

    for j_x, j_ in enumerate(sorted_keys_json):
        #t_ = j_2stich_im[j_].astype(im1.dtype)
        t_ = t_2im[j_]

        # Step 1: Create a boolean mask where reg_matrix is zero
        mask_reg_zero = (reg_matrix == 0)
        # Step 2: Create a boolean mask where t_ is not zero
        mask_t_not_zero = (t_ != 0)
        # Step 3: Combine the masks to find positions where reg_matrix is zero and t_ is not zero
        combined_mask = mask_reg_zero & mask_t_not_zero
        # Step 4: Update reg_matrix at these positions with the corresponding values from t_
        reg_matrix[combined_mask] = t_[combined_mask]

    for t_ in coor_im1_int_all:
        overlap_matrix[t_[0]:t_[1],t_[2]:t_[3]] = 1

    #export_im(reg_matrix)
    #export_im(image_array )


    # for j_x, j_ in enumerate(sorted_keys_json):
    #     t_ = j_2stich_im_full[j_].astype(im1.dtype)
    #     reg_matrix[tileposi == 99] = t_[tileposi == 99]
    #     tileposi[t_>0] = j_x



    ########################################
    ########################################
    ########################################
    ########################################
    # for the sake of precision, only 2-4-5-7 type neighbours will be considered
    #1-2-3
    #4-*-5
    #6-7-8
    done_check_couples = list()
    extraID2data = {}
    if not os.path.exists(os.path.join(reg_out, 'subregistration')):
        try:
            os.makedirs(os.path.join(reg_out, 'subregistration'))
        except:
            pass
    current_virtual = len(sorted_keys_json)

    n_99_prev = 99**99
    while True:
        n_99_curr = np.count_nonzero(tileposi == 99)
        if n_99_prev == n_99_curr or n_99_curr == 0 or True:
            break
        n_99_prev = n_99_curr + 0
        cols_with_99 = np.logical_and(np.any(tileposi == 99, axis=0), np.sum(tileposi != 99, axis=0) > 0)
        indices_col_iter_all = np.where(cols_with_99)[0]
        rows_with_99 = np.logical_and(np.any(tileposi == 99, axis=1), np.sum(tileposi != 99, axis=1) > 0)
        indices_row_iter_all = np.where(rows_with_99)[0]

        for indices_row_iter in indices_row_iter_all:
            unique_seq = np.concatenate(([tileposi[:,indices_row_iter][0]], tileposi[:,indices_row_iter][1:][np.diff(tileposi[:,indices_row_iter]) != 0]))
            if len(unique_seq)>1 and unique_seq[0] == 99 and unique_seq[1]!= 99: #type 4 neighbours
                c_ = unique_seq[1]
                if c_ <= len(sorted_keys_json):
                    s_sec = os.path.basename(sorted_keys_json[c_]).split('_')[-1].split('.json')[0]
                    central_ = scene2sec_tile[s_sec].replace('_' + channel, '_DAPI')
                else:
                    central_ = extraID2data[c_]['central_']
                im2_name = im2neighbour[central_]['l_n'].replace('_' + channel, '_DAPI')
                im2_name_ori = im2neighbour[central_]['l_n']
                curr_json_ID = [t_ori.replace('_' + channel, '_DAPI'), central_, im2_name]

                done_check_couples.append(curr_json_ID)

                if c_ <= len(sorted_keys_json):
                    out_reg_c_ = json_2_out_reg[sorted_keys_json[c_]]
                    central_name = os.path.join(dir_sec, central_)
                    central_im = io.imread(central_name)
                    central_im[:, int(len(central_im[:, 1]) * p_overlap_):] = 0
                    central_im_temp = imreg_dft.imreg.transform_img(central_im, scale=out_reg_c_['scale'], angle=out_reg_c_['angle'],
                                                               tvec=out_reg_c_['tvec'] + j_2rs[sorted_keys_json[c_]]).astype(
                        central_im.dtype)
                    central_im_reg = np.concatenate((np.zeros_like(central_im_temp), central_im_temp), axis=0)
                else:
                    print('Pending to be done...left for V2.0')
                    continue

            continue
        for indices_col_iter in indices_col_iter_all:
            unique_seq = np.concatenate(([tileposi[:,indices_col_iter][0]], tileposi[:,indices_col_iter][1:][np.diff(tileposi[:,indices_col_iter]) != 0]))
            if len(unique_seq)>1 and unique_seq[0] == 99 and unique_seq[1]!= 99: #type 2 neighbours
                c_ = unique_seq[1]
                if c_ <= len(sorted_keys_json):
                    s_sec = os.path.basename(sorted_keys_json[c_]).split('_')[-1].split('.json')[0]
                    central_ = scene2sec_tile[s_sec].replace('_' + channel, '_DAPI')
                else:
                    central_ = extraID2data[c_]['central_']

                im2_name = im2neighbour[central_]['u_n'].replace('_' + channel, '_DAPI')
                im2_name_ori = im2neighbour[central_]['u_n']
                curr_json_ID = [t_ori.replace('_' + channel, '_DAPI'), central_, im2_name]

                if curr_json_ID in done_check_couples:
                    continue

                done_check_couples.append(curr_json_ID)

                if c_ <= len(sorted_keys_json):
                    out_reg_c_ = json_2_out_reg[sorted_keys_json[c_]]
                    central_name = os.path.join(dir_sec, central_)
                    central_im = io.imread(central_name)
                    central_im[int(len(central_im[:, 1]) * p_overlap_):, :] = 0
                    central_im_temp = imreg_dft.imreg.transform_img(central_im, scale=out_reg_c_['scale'], angle=out_reg_c_['angle'],
                                                               tvec=out_reg_c_['tvec'] + j_2rs[sorted_keys_json[c_]]).astype(
                        central_im.dtype)
                    central_im_reg = np.concatenate((np.zeros_like(central_im_temp), central_im_temp), axis=0)
                else:
                    print('Pending to be done...left for V2.0')
                    continue


                if len(im2_name) != 0:
                    mov_matrix = io.imread(os.path.join(dir_sec, im2_name))
                    mov_matrix_ori = io.imread(os.path.join(dir_sec, im2_name_ori))
                    mov_matrix_all = np.copy(mov_matrix)
                    mov_matrix[:-int(len(mov_matrix[:, 1]) * p_overlap_), :] = 0
                    mov_matrix = imreg_dft.imreg.transform_img(mov_matrix, scale=out_reg_c_['scale'], angle=out_reg_c_['angle'],tvec=out_reg_c_['tvec'] + j_2rs[sorted_keys_json[c_]]).astype(central_im.dtype)
                    mov_matrix_all = imreg_dft.imreg.transform_img(mov_matrix_all, scale=out_reg_c_['scale'], angle=out_reg_c_['angle'],tvec=out_reg_c_['tvec'] + j_2rs[sorted_keys_json[c_]]).astype(central_im.dtype)
                    mov_matrix_ori_all = imreg_dft.imreg.transform_img(mov_matrix_ori, scale=out_reg_c_['scale'], angle=out_reg_c_['angle'],tvec=out_reg_c_['tvec'] + j_2rs[sorted_keys_json[c_]]).astype(central_im.dtype)

                    mov_matrix_reg = np.concatenate((mov_matrix,np.zeros_like(mov_matrix)), axis=0)
                    mov_matrix_all_reg = np.concatenate((mov_matrix_all,np.zeros_like(mov_matrix_all)), axis=0)
                    mov_matrix_ori_all_reg = np.concatenate((mov_matrix_ori_all,np.zeros_like(mov_matrix_ori_all)), axis=0)


                transform_json = os.path.join(reg_out, 'subregistration', '_'.join(curr_json_ID) + '.json')
                out_reg, flag = do_basic_reg(central_im_reg, mov_matrix_reg, transform_json)

                if flag == True:
                    mov_matrix_reg_final = imreg_dft.imreg.transform_img(mov_matrix_all_reg, scale=out_reg['scale'], angle=out_reg['angle'],tvec=out_reg['tvec']).astype(mov_matrix.dtype)
                    mov_matrix_ori_all_reg_final = imreg_dft.imreg.transform_img(mov_matrix_ori_all_reg, scale=out_reg['scale'], angle=out_reg['angle'],tvec=out_reg['tvec']).astype(mov_matrix.dtype)
                    mov_matrix_reg_final_red = mov_matrix_reg_final[len(central_im[:,1]):,:]
                    mov_matrix_ori_all_reg_final_red = mov_matrix_ori_all_reg_final[len(central_im[:,1]):,:]

                    rows_with_values = np.where(np.any(mov_matrix_reg_final_red > 0, axis=1))[0]
                    cols_with_values = np.where(np.any(mov_matrix_reg_final_red > 0, axis=0))[0]

                    min_row = np.min(rows_with_values); max_row = np.max(rows_with_values)
                    min_col = np.min(cols_with_values); max_col = np.max(cols_with_values)

                    mov_matrix_reg_final_red_2ref = mov_matrix_reg_final_red[min_row:max_row,min_col:max_col]
                    #mov_matrix_ori_all_reg_final_red_2ref = mov_matrix_ori_all_reg_final_red[min_row:max_row,min_col:max_col]
                    reg_matrix_2ref = reg_matrix[min_row:max_row,min_col:max_col]

                    transform_json = os.path.join(reg_out, 'subregistration','_'.join(curr_json_ID) + '_refined.json')
                    out_reg_ref, flag = do_basic_reg(reg_matrix_2ref, mov_matrix_reg_final_red_2ref, transform_json)

                    #mov_matrix_reg_final = imreg_dft.imreg.transform_img(mov_matrix_reg_final_red_2ref, scale=out_reg_ref['scale'], angle=out_reg_ref['angle'],tvec=out_reg_ref['tvec']).astype(mov_matrix.dtype)
                    mov_matrix_reg_final_ori = imreg_dft.imreg.transform_img(mov_matrix_ori_all_reg_final_red, scale=out_reg_ref['scale'], angle=out_reg_ref['angle'],tvec=out_reg_ref['tvec']).astype(mov_matrix.dtype)

                    stit_matrix[min_row:max_row,min_col:max_col] = mov_matrix_reg_final_ori[min_row:max_row,min_col:max_col]

                    tileposi[min_row:max_row,min_col:max_col] = current_virtual
                    extraID2data[current_virtual] = {'central_': im2_name_ori}
                    extraID2data[current_virtual]['mrMRmcMC'] = [min_row, max_row, min_col, max_col]
                    extraID2data[current_virtual]['out_reg_ref'] = out_reg_ref
                    extraID2data[current_virtual]['out_reg'] = out_reg

                    current_virtual += 1






                #reg_matrix_temp = np.zeros_like(reg_matrix)
                #reg_matrix_temp[tileposi == c_] = reg_matrix[tileposi == c_]


    ########################################
    ########################################
    ########################################
    ########################################




    if 'im2' in locals() and N > 0:
        reg_matrix = reg_matrix[N:-N, N:-N]
        stit_matrix = stit_matrix[N:-N, N:-N]
        overlap_matrix = overlap_matrix[N:-N, N:-N]
        mask_reg_matrix = mask_reg_matrix[N:-N, N:-N]
        tileposi = tileposi[N:-N, N:-N]

    ## we take the best overlap according to the AI model
    all_ov = {}
    for j1x, j1 in enumerate(sorted_keys_json):
        j1_json = json.load(open(j1, 'r'))
        for j2x, j2 in enumerate(sorted_keys_json):
            if j1x >= j2x:
                continue
            j2_json = json.load(open(j2, 'r'))

            t_1 = j1_json['coor_im1_intersection']
            area1 = [(t_1[0], t_1[1]), (t_1[2], t_1[3])]
            t_2 = j2_json['coor_im1_intersection']
            area2 = [(t_2[0], t_2[1]), (t_2[2], t_2[3])]
            overlap_temp = get_overlaps([area2], area1)

            if len(overlap_temp) == 0:
                continue
            n_ = '___'.join(sorted([j1, j2]))
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

    from collage.steps._tf_env import quiet_tf, force_cpu
    quiet_tf()
    import time as _time

    # Model loading: if a persistent gap-fill pool is available (started once,
    # up-front, by the caller before any per-tile worker was forked -- see
    # GapfillPoolService / step 3's run()), scoring jobs go to it instead of
    # loading a fresh model copy in this one-shot per-tile process. Falls back
    # to the original inline load (still gated on all_ov, to skip the ~4.5s
    # load when there's nothing to score) when no pool is available, e.g.
    # n_cores == 1.
    model = None
    _gapfill_load_sec = 0.0
    convert_to_tensor = None
    tf = None
    if gapfill_service is None and all_ov:
        # Step 3 forks many per-tile workers that each load the model; on a GPU
        # they race for device memory (RESOURCE_EXHAUSTED). Step 3's scoring is
        # cheap and not inference-bound, so pin it to CPU and leave the GPU to
        # step 2's single resident worker. Must precede the first TF import here.
        force_cpu()
        from tensorflow.keras.models import load_model
        from tensorflow import convert_to_tensor
        import tensorflow as tf
        _t_load0 = _time.time()
        model = load_model(path_to_model)
        _gapfill_load_sec = _time.time() - _t_load0

    _t_score0 = _time.time()
    _gapfill_score_calls = 0
    ov2all_scores = {}
    ov2ims = {}
    for ovx, ov in enumerate(all_ov):
        ovs_score = {}
        all_ov[ov] = [(int(x), int(y)) for x, y in all_ov[ov]]
        for i in ov.split('___'):
            r1 = j_2stich_im_full[i][all_ov[ov][0][0]:all_ov[ov][0][1], all_ov[ov][1][0]:all_ov[ov][1][1]]
            r2 = im1[all_ov[ov][0][0]:all_ov[ov][0][1], all_ov[ov][1][0]:all_ov[ov][1][1]]
            try:
                np.max(r1) == 0
            except Exception as e:
                print('error_r1_size:', e)
                print(ov)
                ovs_score[i] = 0
                continue

            if np.max(r1) == 0:
                ovs_score[i] = 0
                continue

            non_black_pixels = np.where(r1 != 0)
            r1_ = r1[np.min(non_black_pixels[0]):np.max(non_black_pixels[0]) + 1,
                  np.min(non_black_pixels[1]):np.max(non_black_pixels[1]) + 1]
            r2_ = r2[np.min(non_black_pixels[0]):np.max(non_black_pixels[0]) + 1,
                  np.min(non_black_pixels[1]):np.max(non_black_pixels[1]) + 1]

            try:
                if gapfill_service is not None:
                    # ref=r2_, query=r1_ -- matches the (r_ref_tf, r01_tf) =
                    # (from r2_, from r1_) ordering evaluate_overlap gets below.
                    ovs_score[i] = gapfill_service.submit(r2_, r1_).result()["score"]
                else:
                    r01_tf = convert_to_tensor(r1_, dtype=tf.float32)
                    r_ref_tf = convert_to_tensor(r2_, dtype=tf.float32)
                    ovs_score[i] = evaluate_overlap([(r_ref_tf, r01_tf)], model)
                _gapfill_score_calls += 1
            except:
                ovs_score[i] = 0

        ov2ims[ov] = sorted([i for i in ovs_score if ovs_score[i] == max(ovs_score.values())])[0]
        ov2all_scores[ov] = dict(ovs_score)
    _gapfill_score_sec = _time.time() - _t_score0
    # Phase-3 profiling: how much of step 3 is the gap-fill model work (load +
    # scoring) vs everything else (pseudotile assembly, I/O). Stashed on a module
    # global the manifest writer picks up.
    globals()['_GAPFILL_PROFILE'] = {
        "gapfill_load_sec": round(_gapfill_load_sec, 1),
        "gapfill_score_sec": round(_gapfill_score_sec, 1),
        "gapfill_score_calls": _gapfill_score_calls,
        "gapfill_overlaps": len(all_ov),
    }
    print(f"  gap-fill profile: model load {_gapfill_load_sec:.1f}s, "
          f"scoring {_gapfill_score_sec:.1f}s over {_gapfill_score_calls} calls")

    n_tile_over = {i: len(i.split('___')) for i in ov2ims}
    for ov in sorted(n_tile_over, key=lambda k: n_tile_over[k], reverse=False):
        ov_ = ov2ims[ov]
        rs = j_2stich_im_full[ov_][all_ov[ov][0][0]:all_ov[ov][0][1], all_ov[ov][1][0]:all_ov[ov][1][1]]
        Nx = min(50, (all_ov[ov][0][1]-all_ov[ov][0][0]) / 2)
        Ny = min(50, (all_ov[ov][1][1]-all_ov[ov][1][0]) / 2)
        Nx = int(Nx); Ny = int(Ny);
        rs[0:Nx, :] = 0; rs[-Nx::, :] = 0; rs[:, 0:Ny] = 0; rs[:, -Ny::] = 0;
        reg_matrix[all_ov[ov][0][0]:all_ov[ov][0][1], all_ov[ov][1][0]:all_ov[ov][1][1]][rs>0] = rs[rs>0]
    ##/we take the best overlap according to the AI model

    if reg_matrix.max() == 0:
        print(
            "  WARNING: empty pseudotile %s -- no registration/consensus data "
            "was applied (check that step 2's AlignQC consensus produced "
            "method2ia_red_*.json in test_for_consen/)." % os.path.basename(final_file)
        )
    tifffile.imwrite(final_file, reg_matrix)

    save_mask = False
    if save_mask == True:
        mask_dir = os.path.join(os.path.dirname(os.path.dirname(final_file)), 'masks')
        if not os.path.exists(mask_dir):
            try:
                os.makedirs(mask_dir)
            except:
                pass
        mask_dir_file = os.path.join(mask_dir, os.path.basename(final_file))
        tifffile.imwrite(mask_dir_file, mask_reg_matrix)

    if channel == channel_QC and len(channel_QC) > 0 and do_QC_Plot == True:
        max_value = np.iinfo(reg_matrix.dtype).max
        reg_matrix8b = (reg_matrix / max_value) * 255; reg_matrix8b = reg_matrix8b.astype(np.uint8)
        stit_matrix8b = (stit_matrix / max_value) * 255; stit_matrix8b = stit_matrix8b.astype(np.uint8)
        im18b = (im1 / max_value) * 255; im18b = im18b.astype(np.uint8)

        pc_im18b = np.percentile(im18b, 99)
        pc_reg = np.percentile(reg_matrix8b, 99)
        pc_stit = np.percentile(stit_matrix8b, 99)

        scale_reg = np.mean(im18b[im18b>pc_im18b]) / max(1,np.mean(reg_matrix8b[reg_matrix8b>pc_reg]))
        if np.max(stit_matrix8b) == 0:
            scale_sti = 1
        else:
            scale_sti = np.mean(im18b[im18b>pc_im18b]) / max(1,np.mean(stit_matrix8b[pc_stit>pc_stit]))

        temp_ = np.zeros(reg_matrix8b.shape) + reg_matrix8b
        temp_ = temp_ * scale_reg
        reg_matrix8b[temp_>255] = 255
        reg_matrix8b[temp_<=255] = temp_[temp_<=255].astype(np.uint8)


        temp_ = np.zeros(stit_matrix8b.shape) + stit_matrix8b
        temp_ = temp_ * scale_sti
        stit_matrix8b[temp_>255] = 255
        stit_matrix8b[temp_<=255] = temp_[temp_<=255].astype(np.uint8)


        qc_pseudotile = np.concatenate((im18b[:, :, np.newaxis], reg_matrix8b[:, :, np.newaxis], stit_matrix8b[:, :, np.newaxis]), axis=2)

        if np.max(stit_matrix) > 0:
            qc_file = qc_file[:-4] + '___' + 'stiching_refined.png'
        if np.min(overlap_matrix) == 0:
            qc_file = qc_file[:-4] + '___' + 'incompleted.png'


        if '_codex_' in sec_:
            qc_pseudotile = qc_pseudotile * 50

        imageio.imwrite(qc_file, qc_pseudotile, format='png')


def range_x1_q(x, q):
    x = np.asfarray(x)
    tmp_median = np.median(x)
    tmp_q_high = np.percentile(x[(x > 0) & (x != tmp_median)], q)
    tmp_q_min = np.percentile(x[(x > 0) & (x != tmp_median)], 100 - q)
    x = (x - tmp_q_min) / (tmp_q_high - tmp_q_min)
    x[x > 1] = 1
    x[x < 0] = 0
    return x


def evaluate_overlap(im_pairs, model):
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
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
def get_fixed_megatile(im1):
    height, width = im1.shape[:2]
    bigger_height = height * 3
    bigger_width = width * 3

    image_fixed = np.zeros((bigger_height, bigger_width), dtype=im1.dtype)
    start_y = int(bigger_height / 2 - height / 2)
    start_x = int(bigger_width / 2 - width / 2)
    image_fixed[start_y:start_y + height, start_x:start_x + width] = im1
    return image_fixed

def get_middle_tile(megatile, im1):
    height, width = im1.shape[:2]
    bigger_height = height * 3
    bigger_width = width * 3
    start_y = int(bigger_height / 2 - height / 2)
    start_x = int(bigger_width / 2 - width / 2)
    return megatile[start_y:start_y + height, start_x:start_x + width]

def generate_megatile(out_reg_center, json_, central_, channel):

    im_central = io.imread(os.path.join(dir_sec, central_))

    height, width = im_central.shape[:2]
    bigger_height = height * 3
    bigger_width = width * 3

    image_fixed = np.zeros((bigger_height, bigger_width), dtype=im_central.dtype)
    start_y = int(bigger_height / 2 - height / 2)
    start_x = int(bigger_width / 2 - width / 2)
    image_fixed[start_y:start_y + height, start_x:start_x + width] = im_central



    if '7' in json_:
        im2 = io.imread(os.path.join(dir_sec, json_['7']['tile'].replace('_DAPI.', '_' + channel + '.')))
        out_reg = json_['7']
        start_y2 = int(bigger_height - height)
        start_x2 = int(bigger_width / 2 - width / 2)
        image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
        image_moving[start_y2:start_y2 + height, start_x2:start_x2 + width] = im2
        image_moving = imreg_dft.imreg.transform_img(image_moving, scale=out_reg['scale'], angle=out_reg['angle'],
                                                    tvec=out_reg['tvec']).astype(image_fixed.dtype)
        image_fixed[image_fixed==0] = image_moving[image_fixed==0]



    if '2' in json_:
        im2 = io.imread(os.path.join(dir_sec, json_['2']['tile'].replace('_DAPI.', '_' + channel + '.')))
        out_reg = json_['2']
        start_y2 = 0
        start_x2 = int(bigger_width / 2 - width / 2)
        image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
        image_moving[start_y2:start_y2 + height, start_x2:start_x2 + width] = im2
        image_moving = imreg_dft.imreg.transform_img(image_moving, scale=out_reg['scale'], angle=out_reg['angle'],
                                                    tvec=out_reg['tvec']).astype(image_fixed.dtype)
        image_fixed[image_fixed==0] = image_moving[image_fixed==0]


    if '5' in json_:
        im2 = io.imread(os.path.join(dir_sec, json_['5']['tile'].replace('_DAPI.', '_' + channel + '.')))
        out_reg = json_['5']
        start_y2 = int(bigger_height / 2 - height / 2)
        start_x2 = 0
        image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
        image_moving[start_y2:start_y2 + height, start_x2:start_x2 + width] = im2
        image_moving = imreg_dft.imreg.transform_img(image_moving, scale=out_reg['scale'], angle=out_reg['angle'],
                                                    tvec=out_reg['tvec']).astype(image_fixed.dtype)
        image_fixed[image_fixed==0] = image_moving[image_fixed==0]

    if '4' in json_:
        im2 = io.imread(os.path.join(dir_sec, json_['4']['tile'].replace('_DAPI.', '_' + channel + '.')))
        out_reg = json_['4']
        start_y5 = int(bigger_height / 2 - height / 2)
        start_x5 = int(bigger_width - width)
        image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
        image_moving[start_y5:start_y5 + height, start_x5:start_x5 + width] = im2
        image_moving = imreg_dft.imreg.transform_img(image_moving, scale=out_reg['scale'], angle=out_reg['angle'],
                                                    tvec=out_reg['tvec']).astype(image_fixed.dtype)
        image_fixed[image_fixed==0] = image_moving[image_fixed==0]


    if '8' in json_:
        im2 = io.imread(os.path.join(dir_sec, json_['8']['tile'].replace('_DAPI.', '_' + channel + '.')))
        out_reg = json_['8']
        start_y2 = int(bigger_height - height)
        start_x5 = int(bigger_width - width)
        image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
        image_moving[start_y2:start_y2 + height, start_x5:start_x5 + width] = im2
        image_moving = imreg_dft.imreg.transform_img(image_moving, scale=out_reg['scale'], angle=out_reg['angle'],
                                                     tvec=out_reg['tvec']).astype(image_fixed.dtype)
        image_fixed[image_fixed == 0] = image_moving[image_fixed == 0]

    if '3' in json_:
        im2 = io.imread(os.path.join(dir_sec, json_['3']['tile'].replace('_DAPI.', '_' + channel + '.')))
        out_reg = json_['3']
        start_y2 = 0
        start_x5 = int(bigger_width - width)
        image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
        image_moving[start_y2:start_y2 + height, start_x5:start_x5 + width] = im2
        image_moving = imreg_dft.imreg.transform_img(image_moving, scale=out_reg['scale'], angle=out_reg['angle'],
                                                     tvec=out_reg['tvec']).astype(image_fixed.dtype)
        image_fixed[image_fixed == 0] = image_moving[image_fixed == 0]

    if '1' in json_:
        im2 = io.imread(os.path.join(dir_sec, json_['1']['tile'].replace('_DAPI.', '_' + channel + '.')))
        out_reg = json_['1']
        start_y2 = 0
        start_x5 = 0
        image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
        image_moving[start_y2:start_y2 + height, start_x5:start_x5 + width] = im2
        image_moving = imreg_dft.imreg.transform_img(image_moving, scale=out_reg['scale'], angle=out_reg['angle'],
                                                     tvec=out_reg['tvec']).astype(image_fixed.dtype)
        image_fixed[image_fixed == 0] = image_moving[image_fixed == 0]

    if '6' in json_:
        im2 = io.imread(os.path.join(dir_sec, json_['6']['tile'].replace('_DAPI.', '_' + channel + '.')))
        out_reg = json_['6']
        start_y2 = int(bigger_height - height)
        start_x5 = 0
        image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
        image_moving[start_y2:start_y2 + height, start_x5:start_x5 + width] = im2
        image_moving = imreg_dft.imreg.transform_img(image_moving, scale=out_reg['scale'], angle=out_reg['angle'],
                                                 tvec=out_reg['tvec']).astype(image_fixed.dtype)
        image_fixed[image_fixed == 0] = image_moving[image_fixed == 0]

    image_fixed = imreg_dft.imreg.transform_img(image_fixed, scale=out_reg_center['scale'], angle=out_reg_center['angle'],
                                                 tvec=out_reg_center['tvec']).astype(im_central.dtype)
    return image_fixed


def get_tile2coord(input_metadata):
    tile2coor = dict()
    try:
        pd_metadata = pd.read_csv(input_metadata, sep=',')
        pd_metadata['StageYPosition']
    except:
        pd_metadata = pd.read_csv(input_metadata, sep=';')
        pd_metadata['StageYPosition']

    # Creating DAPI neighbour

    for x, i in enumerate(df_metadata['tile_filename']):
        s = ''
        for k in i.split('_'):
            if k.startswith('S') == True and k.replace('S', '').replace('M', '').isdigit() == True and 'M' in k and \
                    k.split('M')[-1].isdigit() == True:
                s = k.split('M')[0]

        if ',' in str(df_metadata['ImagePixelSize'][x]):
            scalex, scaley = map(float, df_metadata['ImagePixelSize'][x].split(','))
        else:
            scalex = float(df_metadata['ImagePixelSize'][x]) + 0
            scaley = float(df_metadata['ImagePixelSize'][x]) + 0

        scalex = scalex / 10
        scaley = scaley / 10
        if scalex != scaley:
            raise Exception('Scales are not consistent!!')

    if ',' in str(df_metadata['ImagePixelSize'][x]):
        scalex, scaley = map(float, df_metadata['ImagePixelSize'][x].split(','))
    else:
        scalex = float(df_metadata['ImagePixelSize'][x]) + 0
        scaley = float(df_metadata['ImagePixelSize'][x]) + 0
    scale = scalex / 10

    pd_metadata['StageXPosition'] = pd_metadata['StageXPosition'] / scale
    pd_metadata['StageYPosition'] = pd_metadata['StageYPosition'] / scale

    all_y_lev = sorted(list(set(pd_metadata['StageYPosition'])))
    all_x_lev = sorted(list(set(pd_metadata['StageXPosition'])))

    sX = int(pd_metadata['Frame'][0].split(',')[2])
    sY = int(pd_metadata['Frame'][0].split(',')[3])

    shift_x = min(all_x_lev) - sX
    shift_y = min(all_y_lev) - sY

    for x, i in enumerate(pd_metadata['tile_filename']):
        s = ''
        for k in i.split('_'):
            if k.startswith('S') == True and k.replace('S', '').replace('M', '').isdigit() == True and 'M' in k and \
                    k.split('M')[-1].isdigit() == True:
                s = k.split('M')[0]
        if '_' + channel_meta + '.' not in i:
            continue

        tile2coor[i] = (pd_metadata['StageXPosition'][x] - shift_x, pd_metadata['StageYPosition'][x] - shift_y)  # x,y

    min_x_re = min([tile2coor[i][0] for i in tile2coor])
    min_y_re = min([tile2coor[i][1] for i in tile2coor])
    tile2coor_ = {i: (tile2coor[i][0] - min_x_re, tile2coor[i][1] - min_y_re) for i in tile2coor}
    return tile2coor_



def get_neigt(df_metadata, tile2coor):
    im2neighbour = {}
    for x, i in enumerate(df_metadata['tile_filename']):
        u_n, d_n, l_n, r_n = '', '', '', ''
        c_x, c_y = df_metadata['StageXPosition'][x], df_metadata['StageYPosition'][x]
        for y, j in enumerate(df_metadata['tile_filename']):
            if i == j:
                continue
            if i not in tile2coor or j not in tile2coor:
                continue
            elif abs(tile2coor[i][0] - tile2coor[j][0]) < 0.1 * df_metadata['Width'][y]:
                if abs(tile2coor[i][1] - tile2coor[j][1]) > 1.3 * df_metadata['Height'][y]:
                    continue
                if tile2coor[i][1] - tile2coor[j][1] < 0:
                    d_n = j[:]
                else:
                    u_n = j[:]
            elif abs(tile2coor[i][1] - tile2coor[j][1]) < 0.1 * df_metadata['Height'][y]:
                if abs(tile2coor[i][0] - tile2coor[j][0]) > 1.3 * df_metadata['Width'][y]:
                    continue
                if tile2coor[i][0] - tile2coor[j][0] < 0:
                    l_n = j[:]
                else:
                    r_n = j[:]
        im2neighbour[i] = {'r_n': r_n, 'l_n': l_n, 'u_n': u_n, 'd_n': d_n}
    return im2neighbour
def get_recons_im(im2, out_reg, coor_im1_int, coor_im2_int, im2_ori):
    do_8bit = False
    if im2.dtype == np.dtype('uint16') and do_8bit == True:
        im2 = im2 / (2 ** 16 - 1) * (2 ** 8 - 1)
        im2 = im2.astype(np.uint8)
    if im2_ori.dtype == np.dtype('uint16') and do_8bit == True:
        im2_ori = im2_ori / (2 ** 16 - 1) * (2 ** 8 - 1)
        im2_ori = im2_ori.astype(np.uint8)

    if im2.dtype == np.dtype('float16'):
        im2 = im2.astype(np.float64)
    if im2_ori.dtype == np.dtype('float16'):
        im2_ori = im2_ori.astype(np.float64)

    res = [coor_im1_int[0] - coor_im2_int[0], coor_im1_int[2] - coor_im2_int[2]]
    l1 =  [-im2.shape[0], 0, im2.shape[0]]
    l2 =  [-im2.shape[1], 0, im2.shape[1]]
    r1s = [abs(res[0]- r_) for r_ in l1]
    r1 = l1[r1s.index(min(r1s))]
    r2s = [abs(res[1]- r_) for r_ in l2]
    r2 = l2[r2s.index(min(r2s))]

    if 'scale' not in out_reg:
        out_reg['scale'] = 0
    if 'angle' not in out_reg:
        out_reg['angle'] = 0

    im2_ori_reg = imreg_dft.imreg.transform_img(im2, scale=out_reg['scale'], angle=out_reg['angle'],
                                                tvec=np.array(out_reg['tvec'])+(r1,r2), bgval=0)

    if np.max(im2_ori_reg[coor_im1_int[0]:coor_im1_int[1], coor_im1_int[2]:coor_im1_int[3]])>0:
        im2_ori_reg = imreg_dft.imreg.transform_img(im2_ori, scale=out_reg['scale'], angle=out_reg['angle'],
                                                    tvec=np.array(out_reg['tvec']) + (r1, r2), bgval=0)
        return im2_ori_reg, np.array(out_reg['tvec'])+(r1,r2), False

    # option 1 for reconstruction
    im2_ori_reg = ndimage.rotate(im2_ori, out_reg['angle'], reshape=False, cval=0)
    ##im2_ori_reg = ndimage.zoom(im2_ori_reg, (out_reg['scale'], out_reg['scale']))
    im2_ori_reg = ndimage.shift(im2_ori_reg, (int(out_reg['tvec'][0]), int(out_reg['tvec'][1])), mode='wrap')


    '''
    im2_ori_reg = ndimage.rotate(im2, out_reg['angle'], reshape=False, cval=0)
    im2_ori_reg = ndimage.zoom(im2_ori_reg, (out_reg['scale'], out_reg['scale']))
    im2_ori_reg = ndimage.shift(im2_ori_reg, (int(out_reg['tvec'][0]), int(out_reg['tvec'][1])), mode='wrap')
    '''
    im2_ori_reg = im2_ori_reg.astype(im2.dtype)
    return im2_ori_reg, (0,0), True







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
    global tile_input, reg_out, dir_pseudotile, reference_round_number, n_cores
    global channel_QC, channels, channel_meta, path_to_model, do_QC_Plot
    # Driver-computed values read as globals by the (module-level) helper
    # functions; must be declared global now that the driver lives in run().
    global R_ori, R_sec, V_ori, V_sec, df_metadata, dir_sec, im2neighbour, k

    ps = cfg.pseudotiles if isinstance(cfg.pseudotiles, dict) else {}

    tile_input = cfg.input_dir
    reg_out = cfg.output_reg
    dir_pseudotile = cfg.output_pseudotiles
    reference_round_number = str(cfg.reference_round)
    n_cores = int(ps.get("n_cores", cfg.n_cores))
    channel_QC = ps.get("channel_qc", "DAPI")     # "" disables AI QC during pseudotiling
    channels = list(ps.get("channels", []))        # [] = all channels
    channel_meta = channel_QC if channel_QC else cfg.channel
    do_QC_Plot = bool(ps.get("qc_plot", False))

    # Precondition: step 2 (register) must have completed (O(1) manifest check).
    require_prior_step(cfg.step_manifest_path(2),
                       step="3 (pseudotiles)", prior="2 (register)")
    # Diagnostic: count how often the secondary-round gap-filling stitching
    # fallback fires (i.e. step 2's registered tiles left a coverage hole). 0 on
    # the benchmark means the _neighbour_stitching path is never exercised here;
    # a non-zero value flags it as a real (and Phase-3-optimizable) cost.
    _gap_fill_fires = 0
    path_to_model = cfg.model_path

    seed = int(ps.get("seed", 0))
    import cv2 as _cv2
    _cv2.setRNGSeed(seed); np.random.seed(seed)

    if channel_QC and not os.path.exists(path_to_model):
        raise FileNotFoundError(
            f"AlignQC model not found at {path_to_model} (needed because pseudotiles."
            f"channel_qc is set). Run scripts/download_model.py, or set "
            f"pseudotiles.channel_qc: '' to skip QC during pseudotiling."
        )

    _t_start = time.time()
    if not os.path.exists(reg_out):
        os.makedirs(reg_out)
    if not os.path.exists(dir_pseudotile):
        os.makedirs(dir_pseudotile)

    if not os.path.exists(reg_out):
        try:
            os.makedirs(reg_out)
        except:
            pass

    # Matched by round NUMBER only, not round+version: a non-reference VERSION
    # of the reference ROUND (e.g. reference is R01_V01, but R01_V02 also
    # exists) would otherwise match here too. Since cfg.reference_version is
    # only the global default (not override-aware -- matching this file's
    # existing round-only handling elsewhere), skip the version check only
    # when it's unset (auto-selected single-version case), where round alone
    # is already unambiguous.
    reference_version_number = cfg.reference_version

    oris_ = []
    for i in os.listdir(reg_out):
        try:
            curr_R = [j for j in i.split('_') if j.startswith('R') and len(j) > 1 and j[1::].isdigit() == True][0]
        except:
            # non-round entry (helper folder, run_manifest json, ...) -> skip quietly
            continue
        if int(curr_R[1::]) != int(reference_round_number):
            continue
        if reference_version_number is not None:
            curr_V = [j for j in i.split('_') if j.startswith('V') and j[1:].isnumeric()]
            if not curr_V or curr_V[0] != reference_version_number:
                continue
        oris_.append(i[:])

    # Persistent gap-fill scoring pool, started once before any per-tile
    # worker is forked (see GapfillPoolService) -- avoids reloading the model
    # in every one of the potentially thousands of generate_pseudotile calls
    # below. None if the model isn't present; generate_pseudotile() falls
    # back to its original per-call inline load in that case (matching prior
    # behaviour, which only actually loaded/failed when overlaps existed).
    _gapfill_pool = None
    if os.path.exists(path_to_model):
        # output_root = reg_out (output_reg), NOT dir_pseudotile: step 4 lists
        # every directory directly under output_pseudotiles and assumes each
        # one is a real pseudotile group (expects a 'final' subfolder inside).
        # A _gapfill_pool_results dir placed there would get swept into that
        # listing and break step 4. output_reg is never scanned that way
        # (mirrors where step 2's own CPUPoolService puts _pool_results).
        _gapfill_pool = GapfillPoolService(path_to_model, n_cores, reg_out).start()

    for ori_x, ori_ in enumerate(oris_):
        '''
        /mnt/BMS_temporal_data/CABALA/testMaite/CODEX_DATASET_02/output_registration/output_pseudotiles/GC19BT_R09_V01_CODEX_JP_S0M/QC/GC19BT_R09_V01_CODEX_JP_S0M39_DAPI.tiff.png
        /mnt/BMS_temporal_data/CABALA/testMaite/CODEX_DATASET_02/output_registration/output_pseudotiles/GC32OT_R11_V01_CODEX_JP_S0M/QC/GC32OT_R11_V01_CODEX_JP_S0M18_DAPI.tiff.png
        '''

        #if 'WP' not in ori_:
        #    continue

        t_ = '_' + [i for i in ori_.split('_') if i.startswith('V') and i[1::].isnumeric() == True][0] + '_'
        ori_2filter_post = ori_.split(t_)[1]
        curr_R_ori = [j for j in ori_.split('_') if j.startswith('R') and len(j) > 1 and j[1::].isdigit() == True][0]
        ori_2filter_pre = ori_.split(curr_R_ori)[0]

        # Exclude by round+version together, not round alone: excluding on
        # curr_R_ori alone (e.g. "_R01_") would also drop a non-reference
        # VERSION of the reference ROUND (e.g. reference is R01_V01, but
        # R01_V02 exists too) -- that's a real, non-reference round/version
        # that still needs a pseudotile, not the reference itself.
        _ref_round_version_token = '_' + curr_R_ori + t_
        SEC_ = [i for i in os.listdir(reg_out) if _ref_round_version_token not in i and ori_2filter_post in i and ori_2filter_pre in i]
        temp_total = 0
        for sec_x, sec_ in enumerate(SEC_):
            print('DOING element', sec_, sec_x,len(SEC_))
            #if 'R012222' not in sec_:
            #    continue
            #if 'R13' not in sec_ or 'WP3.I' not in sec_:
            #    continue
            dir_pseudotile_qc = os.path.join(dir_pseudotile, sec_, 'QC')
            dir_pseudotile_final = os.path.join(dir_pseudotile, sec_, 'final')
            dir_ori = os.path.join(tile_input, ori_)
            dir_sec = os.path.join(tile_input, sec_)

            if not os.path.exists(dir_pseudotile_qc):
                os.makedirs(dir_pseudotile_qc)
            if not os.path.exists(dir_pseudotile_final):
                os.makedirs(dir_pseudotile_final)

            input_metadata = [os.path.join(dir_sec, i) for i in os.listdir(dir_sec) if i.endswith('.csv') == True and (sec_ in i or i.split('.csv')[0] in i)][0]

            df_metadata = pd.read_csv(input_metadata)
            if 'Width' in df_metadata:
                np_x = df_metadata['Width'][0]
                np_y = df_metadata['Height'][0]
            elif 'Frame' in df_metadata:
                np_x = int(df_metadata['Frame'][0].split(',')[-2])
                np_y = int(df_metadata['Frame'][0].split(',')[-1])
                df_metadata['Width'] = [np_x] * len(df_metadata['Frame'])
                df_metadata['Height'] = [np_y] * len(df_metadata['Frame'])
            else:
                raise MetadataError("Could not determine pixel size: tile metadata has neither a 'Width' nor a 'Frame' column.")


            tile2coor = get_tile2coord(input_metadata)
            im2neighbour = get_neigt(df_metadata, tile2coor)

            all_x = sorted(list(set([tile2coor[i][0] for i in tile2coor])))
            all_y = sorted(list(set([tile2coor[i][1] for i in tile2coor])))
            ovlapp_x = 1 - abs(all_x[0]- all_x[1]) / np_x
            ovlapp_y = 1 - abs(all_y[0]- all_y[1]) / np_y

            if abs(ovlapp_x - ovlapp_y) > 0.001:
                # not_consistent_overlap
                print('Not consistent overlap!!!!!', ovlapp_x, ovlapp_y)
            p_overlap_ = np.mean([ovlapp_x, ovlapp_y])



            R_ori = [i for i in ori_.split('_') if i.startswith('R') == True and i[1::].isnumeric() == True][0]
            R_sec = [i for i in sec_.split('_') if i.startswith('R') == True and i[1::].isnumeric() == True][0]
            # Output tile names are derived from the REFERENCE tile's own filename
            # (t_ori), so the round token alone isn't enough to disambiguate: without
            # also swapping the version token, every query VERSION of a round writes
            # its pseudotiles under a correctly-versioned FOLDER but with the
            # REFERENCE's version baked into the FILENAME -- e.g. R02_V02's and
            # R02_V03's output files both end up misnamed "..._V01_..." (matching
            # a real-slide legacy trace in the comment near line 1391). That collapses
            # all versions of a round onto one reconstruction key in step 4. Single
            # version per round (the benchmark): V_ori == V_sec, so this is a no-op.
            V_ori = [i for i in ori_.split('_') if i.startswith('V') == True and i[1::].isnumeric() == True][0]
            V_sec = [i for i in sec_.split('_') if i.startswith('V') == True and i[1::].isnumeric() == True][0]

            os.listdir(dir_ori)

            out_json_dir = os.path.join(reg_out, sec_, 'QC')

            if len(channels) == 0:
                channels = set()
                for t_sec in os.listdir(dir_ori):
                    if t_sec.endswith('.tiff') == False:
                        continue
                    S_sec = [i for i in t_sec.split('_') if i.startswith('S') and 'M' in i and i.replace('S', '').replace('M', '').isnumeric() == True][0]
                    channels.add(t_sec.split(S_sec)[1].split('.tiff')[0][1::])


            for channelx, channel in enumerate(channels):
                #if 'DAPI' != channel:
                #    continue

                all_tiles_ori_ = [i for i in os.listdir(dir_ori) if i.endswith(channel + '.tiff')]
                all_tiles_sec_ = [i for i in os.listdir(dir_sec) if i.endswith(channel + '.tiff')]

                #/mnt/NAS01/testMaite/KID_DATASET/output_reg/output_pseudotiles/KID2_R21_V1_KIDNEY_YVH_S3M/final/KID2_R21_V3_KIDNEY_YVH_S3M14_DAPI.tiff

                all_tiles_ori, all_tiles_sec = [], []
                for i in all_tiles_ori_:
                    S_sec = [k for k in i.split('_') if k.startswith('S') and 'M' in k and k.replace('S', '').replace('M', '').isnumeric() == True][0]
                    c_ = i.split(S_sec)[1].split('.tiff')[0][1::]
                    if c_ != channel:
                        continue
                    if len([j for j in channels if j == c_]) != 1:
                        continue
                    all_tiles_ori.append(i)
                for i in all_tiles_sec_:
                    S_sec = [k for k in i.split('_') if k.startswith('S') and 'M' in k and k.replace('S', '').replace('M', '').isnumeric() == True][0]
                    c_ = i.split(S_sec)[1].split('.tiff')[0][1::]
                    if c_ != channel:
                        continue
                    if len([j for j in channels if j == c_]) != 1:
                        continue
                    all_tiles_sec.append(i)

                scene2sec_tile = {}
                for t_sec in all_tiles_sec:
                    S_sec = [i for i in t_sec.split('_') if
                             i.startswith('S') and 'M' in i and i.replace('S', '').replace('M', '').isnumeric() == True]
                    if len(S_sec) != 1:
                        print('Error selecting tile M')
                        raise MetadataError('Could not identify a unique S<scene>M<tile> token in the secondary-round tile filename.')
                    scene2sec_tile[S_sec[0].split('M')[-1]] = t_sec

                n_total = len(SEC_) * len(channels) * len(all_tiles_ori)

                c2p = {c: None for c in range(n_cores)}
                c2file = {c: None for c in range(n_cores)}
                failed_elements = []
                for t_orix, t_ori in enumerate(all_tiles_ori):

                    #if 'DAPI' not in t_ori:
                    #    continue
                    #if 'M84_' not in t_ori or 'DAPI' not in t_ori or '_R09_' not in dir_sec:
                    #    continue
                    #time.sleep(0.1)

                    #if 'M171' not in t_ori or 'DAPI' not in t_ori:
                        #continue
                    #if 'M13' not in t_ori:
                    #    continue
                    if do_progress == True:
                        ws = aux_func.send_task_evolution(ws, int(temp_total / n_total * (1+ori_x)) / len(oris_) , ind_,
                                                     server_id)

                    if n_cores == 1:
                        temp_total += 1
                        print('Pseudotiles..', 'Slide',ori_x+1,'/',len(oris_) ,'Rounds',sec_x+1,'/',len(SEC_) , 'Channel',channelx+1,'/',len(channels) , 'Tiles',t_orix+1,'/',len(all_tiles_ori))
                        generate_pseudotile(t_ori, dir_pseudotile_qc, dir_pseudotile_final, dir_ori, dir_sec, scene2sec_tile,
                                            out_json_dir, reg_out, channel, p_overlap_, sec_, channel_QC, _gapfill_pool)
                    else:
                        while True:
                            time.sleep(0.1)
                            c_core = -1
                            for c in c2p:
                                if type(c2p[c]) == type(None):
                                    c_core = c + 0
                                    break
                                elif c2p[c].is_alive() == False:
                                    f_temp = os.path.join(dir_pseudotile_final, c2file[c].replace(R_ori, R_sec).replace(V_ori, V_sec))
                                    if os.path.isfile(f_temp) == False:
                                        failed_elements.append(c2file[c])
                                    c_core = c + 0
                                    break

                            if c_core != -1:
                                break
                        temp_total += 1
                        print('Pseudotiles..', 'Slide',ori_x+1,'/',len(oris_) ,'Rounds',sec_x+1,'/',len(SEC_) , 'Channel',channelx+1,'/',len(channels) , 'Tiles',t_orix+1,'/',len(all_tiles_ori), c_core)
                        p = Process(target=generate_pseudotile,
                                    args=(t_ori, dir_pseudotile_qc, dir_pseudotile_final, dir_ori, dir_sec, scene2sec_tile,
                                            out_json_dir, reg_out, channel, p_overlap_, sec_, channel_QC, _gapfill_pool,))
                        p.start()
                        c2p[c_core] = p
                        c2file[c_core] = t_ori
                        continue
                counter_ = 0  # retained: reserved loop counter
                while True:
                    time.sleep(0.1)
                    c_core = -1
                    do_break = True
                    counter_ += 1
                    for c in c2p:
                        if type(c2p[c]) == type(None):
                            continue
                        elif c2p[c].is_alive() == True:
                            do_break = False
                            break
                        else:
                            f_temp = os.path.join(dir_pseudotile_final, c2file[c].replace(R_ori, R_sec).replace(V_ori, V_sec))
                            if os.path.isfile(f_temp) == False:
                                failed_elements.append(c2file[c])
                            c2p[c] = None

                    if do_break == True:
                        print('Done all cores')
                        break

                for t_orix, t_ori in enumerate(failed_elements):  # PARALELIZAR ESTE BUCLE!
                    if do_progress == True:
                        ws = aux_func.send_task_evolution(ws, int(temp_total / n_total * (1 + ori_x)) / len(oris_), ind_,
                                                          server_id)
                    print('RE-Pseudotiles...', t_ori, t_orix, '/', len(failed_elements))
                    try:
                        generate_pseudotile(t_ori, dir_pseudotile_qc, dir_pseudotile_final, dir_ori, dir_sec,
                                            scene2sec_tile,
                                            out_json_dir, reg_out, channel, p_overlap_, sec_, channel_QC, _gapfill_pool)
                    except Exception as e:
                        print('**********\n'*5)
                        print('Error in Re-Pseudotiles..')
                        print(str(e))
                        print('**********\n'*5)

                    '''
                    qc_file = os.path.join(dir_pseudotile_qc, t_ori.replace(R_ori, R_sec) + '.png')
                    final_file = os.path.join(dir_pseudotile_final, t_ori.replace(R_ori, R_sec))
    
                    im1 = io.imread(os.path.join(dir_ori, t_ori))
    
                    S_ori = [i for i in t_ori.split('_') if i.startswith('S') and 'M' in i and i.replace('S','').replace('M','').isnumeric() == True]
                    if len(S_ori) != 1:
                        print('Error selecting tile M')
                        raise MetadataError('Could not identify a unique S<scene>M<tile> token in the tile filename.')
                    S_ori = S_ori[0].split('M')[-1]
    
                    # transdform this in a function. Inputs:
                    # - S_ori
                    # - out_json_dir
    
                    priority_order = ['imreg_dft', 'cv2', 'aa', 'chi2_no_angle', 'phase_cross_correlation_no_angle',
                                      'imreg_dft_no_angle']
                    all_json_involved = [os.path.join(out_json_dir,i) for i in os.listdir(out_json_dir) if i.endswith('.json') and i.startswith('01_'+S_ori + '_')]
    
                    json_2_out_reg = {}
                    json_conflict = set()
                    json2overlap = {}
                    for j_ in all_json_involved:
                        json_ = json.load(open(j_,'r'))
                        if 'coor_im2_intersection' not in json_:
                            continue
                        npix = json_['coor_im2_intersection']; npix_ = (npix[1]-npix[0]) * (npix[3]-npix[2])
                        json2overlap[j_] = npix_
                        json_['method2transl'] = eval(json_['method2transl'])
    
                        mm_final = ''
                        mm = 99
                        for m1x, m1 in enumerate(priority_order):
                            for m2x, m2 in enumerate(priority_order):
                                if m1 >= m2:
                                    continue
                                if m1 not in json_['method2transl'] or m2 not in json_['method2transl']:
                                    continue
                                mm12 = min([m1x, m2x])
                                if mm12 > mm:
                                    continue
                                if max(json_['method2transl'][m1]['tvec']-json_['method2transl'][m2]['tvec']) < 5:
                                    mm = mm12 + 0
                                    mm_final = m1[:]
                        if mm == 99:
                            json_conflict.add(j_)
                        else:
                            if "timg" in  json_['method2transl'][mm_final]:
                                del  json_['method2transl'][mm_final]["timg"]
                            json_2_out_reg[j_] = json_['method2transl'][mm_final]
                            json_2_out_reg[j_]['coor_im1_intersection'] = json_['coor_im1_intersection']
                            json_2_out_reg[j_]['coor_im2_intersection'] = json_['coor_im2_intersection']
    
    
                    #if len(json_conflict) > 0:
                        3error_pending_to_be_refined_with_sttitching
    
                    j_2coor = dict()
                    sorted_keys_json = sorted(json2overlap, key=json2overlap.get, reverse=True)
                    coor_im2_int_all = list()
                    j_2stich_im = dict()
                    for j_ in sorted_keys_json:
    
                        out_reg = json_2_out_reg[j_]
                        coor_im1_int = list(map(int, json_2_out_reg[j_]['coor_im1_intersection']))
                        coor_im2_int = list(map(int, json_2_out_reg[j_]['coor_im2_intersection']))
    
                        extend_overlap_xM = min(im1.shape[0] - coor_im1_int[1], im1.shape[0] - coor_im2_int[1])
                        coor_im1_int[1] = coor_im1_int[1] + extend_overlap_xM
                        coor_im2_int[1] = coor_im2_int[1] + extend_overlap_xM
                        extend_overlap_xm = min(coor_im1_int[0], coor_im2_int[0])
                        coor_im1_int[0] = coor_im1_int[0] - extend_overlap_xm
                        coor_im2_int[0] = coor_im2_int[0] - extend_overlap_xm
    
                        extend_overlap_yM = min(im1.shape[1] - coor_im1_int[3], im1.shape[1] - coor_im2_int[3])
                        coor_im1_int[3] = coor_im1_int[3] + extend_overlap_yM
                        coor_im2_int[3] = coor_im2_int[3] + extend_overlap_yM
                        extend_overlap_ym = min(coor_im1_int[2], coor_im2_int[2])
                        coor_im1_int[2] = coor_im1_int[2] - extend_overlap_ym
                        coor_im2_int[2] = coor_im2_int[2] - extend_overlap_ym
    
    
    
                        s_sec = os.path.basename(j_).split('_')[-1].split('.json')[0]
                        im02_name = os.path.join(dir_sec, scene2sec_tile[s_sec])
                        im2 = io.imread(im02_name)
                        im2_ori = im2.copy()
    
                        im2[:coor_im2_int[0], :] = 0
                        im2[coor_im2_int[1]:, :] = 0
                        im2[:, :coor_im2_int[2]] = 0
                        im2[:, coor_im2_int[3]:] = 0
    
    
                        ### TRANSFORM IMAGE
                        res = [coor_im1_int[0] - coor_im2_int[0], coor_im1_int[2] - coor_im2_int[2]]
                        l1 = [-im2.shape[0], 0, im2.shape[0]]
                        l2 = [-im2.shape[1], 0, im2.shape[1]]
                        r1s = [abs(res[0] - r_) for r_ in l1]
                        r1 = l1[r1s.index(min(r1s))]
                        r2s = [abs(res[1] - r_) for r_ in l2]
                        r2 = l2[r2s.index(min(r2s))]
    
                        if 'scale' not in out_reg:
                            out_reg['scale'] = 0
                        if 'angle' not in out_reg:
                            out_reg['angle'] = 0
    
                        im2_ori_reg = imreg_dft.imreg.transform_img(im2, scale=out_reg['scale'], angle=out_reg['angle'], tvec=out_reg['tvec'] + (r1, r2))
                        ###/TRANSFORM IMAGE
    
                        j_2stich_im[j_] = im2_ori_reg
                        coor_im2_int_all.append(coor_im2_int)
                        j_2coor[j_] = coor_im2_int
    
                    reg_matrix = np.zeros_like(im1)
                    stit_matrix = np.zeros_like(im1)
                    overlap_matrix = np.zeros_like(im1)
    
                    for j_ in sorted_keys_json:
                        t_ = j_2stich_im[j_].astype(im1.dtype)
                        #t_[reg_matrix != 0] = 0
                        reg_matrix[t_!=0] = t_[t_!=0]
                    for t_ in coor_im2_int_all:
                        overlap_matrix[t_[0]:t_[1],t_[2]:t_[3]] = 1
    
                    if np.min(overlap_matrix) == 0:
                        _gap_fill_fires += 1
                        print(f"  [gap-fill] step-2 registration left a coverage gap; "
                              f"stitching secondary round to refine (fire #{_gap_fill_fires})")
                        for j_ in sorted_keys_json:
                            out_reg = json_2_out_reg[j_]
                            s_sec = os.path.basename(j_).split('_')[-1].split('.json')[0]
                            central_ = os.path.basename(os.path.join(dir_sec, scene2sec_tile[s_sec]))
                            central_DAPI = central_.replace('_' + channel, '_DAPI')
                            json_file = os.path.join(reg_out, 'neighbour_stitching', central_DAPI + '.json')
                            if os.path.exists(json_file) == False:
                                neighbour_stitching.generate_neighbour_stitching(reg_out, dir_sec, central_DAPI, p_overlap_, False)
                            json_ = json.load(open(json_file, 'r'))
                            mega_tile_moving = generate_megatile(out_reg, json_, central_, channel)
                            mega_tile_fixed = get_fixed_megatile(im1)
    
                            sub_mega_tile_moving = get_middle_tile(mega_tile_moving, im1)
                            sub_mega_tile_fixed = get_middle_tile(mega_tile_fixed, im1)
    
                            stit_matrix[sub_mega_tile_moving>0] = sub_mega_tile_moving[sub_mega_tile_moving>0]
    
                            overlap_matrix[overlap_matrix==0] = stit_matrix[overlap_matrix==0]
    
                            if np.min(overlap_matrix) > 0:
                                break
    
    
    
    
                    tifffile.imwrite(final_file, reg_matrix)
                    if channel == channel_QC and len(channel_QC) > 0:
                        max_value = np.iinfo(reg_matrix.dtype).max
                        reg_matrix8b = (reg_matrix / max_value) * 255; reg_matrix8b = reg_matrix8b.astype(np.uint8)
                        stit_matrix8b = (stit_matrix / max_value) * 255; stit_matrix8b = stit_matrix8b.astype(np.uint8)
    
                        qc_pseudotile = np.concatenate((im1[:, :, np.newaxis], reg_matrix[:, :, np.newaxis], stit_matrix[:, :, np.newaxis]), axis=2)
    
                        if np.min(stit_matrix) > 0:
                            qc_file = qc_file[:-4] + '___' + 'stiching_refined.png'
                        if np.min(overlap_matrix) == 0:
                            qc_file = qc_file[:-4] + '___' + 'incompleted.png'
    
    
                        if '_codex_' in sec_:
                            qc_pseudotile = qc_pseudotile * 5
    
                        imageio.imwrite(qc_file, qc_pseudotile, format='png')
    
                    '''







    if _gapfill_pool is not None:
        _gapfill_pool.shutdown()

    _rm = {
        "step": "3_pseudotiles",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "reference_round": cfg.reference_round, "channels": channels or "all",
        "channel_qc": channel_QC, "n_cores": n_cores, "seed": seed,
        "gap_fill_fallback_fires": _gap_fill_fires,
        "gapfill_profile": globals().get("_GAPFILL_PROFILE"),
        "duration_sec": round(time.time() - _t_start, 1),
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
    }
    with open(os.path.join(dir_pseudotile, "run_manifest_step3.json"), "w") as _fh:
        json.dump(_rm, _fh, indent=2, default=_json_safe)
    if _gap_fill_fires:
        print(f"  gap-fill fallback fired {_gap_fill_fires}x (secondary-round stitching used)")
    _n = len([d for d in os.listdir(dir_pseudotile) if os.path.isdir(os.path.join(dir_pseudotile, d))])
    print(f"  pseudotile groups written: {_n}")
    print(f"  run manifest: {os.path.join(dir_pseudotile, 'run_manifest_step3.json')}")
