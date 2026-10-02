"""Step 1 - Coarse stitching (migrated).

Coarsely stitches the tiles of each round into a per-round reconstruction using
the recorded stage positions, and writes per-tile neighbour-stitching transforms
to <output_reg>/neighbour_stitching/.

This module preserves the original stitching MATH verbatim (the functions below
are copied unchanged from the legacy stitching_function.py). Only the driver was
rewritten: it now reads parameters from the config + manifest instead of
prompting interactively or using hard-coded paths.

Folded-in improvements (agreed scope): deterministic RANSAC seed (1), overlap
derived from the manifest rather than hard-coded (2), failures surfaced not
swallowed (3), explicit 8-bit toggle (7), configurable registration channel (9),
and a run_manifest.json written next to the outputs (5).
"""
from __future__ import annotations

import os
import sys
import json
import time
import copy
import shutil
import platform
from datetime import datetime, timezone

import numpy as np
from .. import _compat  # noqa: F401  -- numpy alias shim for legacy libs
import pandas as pd
import cv2
cv2.setNumThreads(1)  # parallelism is at the process level (n_cores workers); an
                      # uncapped per-process OpenCV thread pool oversubscribes the box
import imageio
import imreg_dft
import networkx as nx
from scipy import ndimage
from scipy.optimize import linprog
from skimage import io
from image_registration import chi2_shift
from PIL import Image
from multiprocessing import Process

Image.MAX_IMAGE_PIXELS = None

from ..config import CollageConfig
from ..errors import CollageError, MetadataError, MissingInputError, ConsensusError, ReconstructionError
from ..ingest import manifest as manifest_mod

# --- module-level parameters read as globals by the math functions -----------
# (set per-run inside run(); defaults keep the functions importable/testable)
scale = 1            # spatial compression factor for registration (1 = none)
p_overlap_ = 0.1     # fractional tile overlap (DERIVED from the manifest in run())
channel_meta = "DAPI"
do_QC = False
do_progress = False  # legacy websocket progress reporting is disabled in the OSS tool
_DO_8BIT = True      # item 7: downcast to 8-bit before registration






def compress_grayscale_image(image, reduction_factor):

    """
    Compresses the input grayscale image by the specified compression factor.

    Parameters:
        image (numpy array): The input grayscale image as a numpy array.
        reduction_factor (int): The factor by which the image should be reduced.

    Returns:
        numpy array: The reduced grayscale image as a numpy array.
    """
    pil_image = Image.fromarray(image)

    # Convert the grayscale image to 'L' mode (8-bit grayscale) explicitly
    pil_image = pil_image.convert('L')

    reduced_width = pil_image.width // reduction_factor
    reduced_height = pil_image.height // reduction_factor

    reduced_image = pil_image.resize((reduced_width, reduced_height), Image.LANCZOS)

    return np.array(reduced_image)

def do_stitching(central_, image_fixed, image_moving, N_, qc_file, image_fixed_ori_8b, im2_name, do_QC, im2_core):
    """Reference-round neighbour stitch (elaborate variant: directional N=2/5/7 overlap
    masking + phase-correlation refinement). Secondary-round counterpart:
    _neighbour_stitching.do_stitching. Computed on DAPI; coords reused for all channels."""
    bigger_height, bigger_width = image_fixed.shape
    height, width = im2_core.shape
    # Resize the image using OpenCV's resize function

    #if 'KID1_R01_V1_KIDNEY_YVH_S0M17_DAPI.tiff' != im2_name:
        #return None, image_fixed


    try:
        max_value = np.iinfo(image_fixed.dtype).max
    except:
        max_value = 2**16-1
    image_fixed_8b = (image_fixed / max_value) * 255;
    image_fixed_8b = image_fixed_8b.astype(np.uint8)

    im1 = np.copy(image_fixed)
    im2 = np.copy(image_moving)


    if scale != 1:
        im1 = compress_grayscale_image(im1, scale)
        im2 = compress_grayscale_image(im2, scale)

    do_8bit = _DO_8BIT
    if im1.dtype != np.dtype('uint8') and do_8bit == True:
        im1 = im1 / (2 ** 16 - 1) * (2 ** 8 - 1)
        im1 = im1.astype(np.uint8)
    if im2.dtype != np.dtype('uint8') and do_8bit == True:
        im2 = im2 / (2 ** 16 - 1) * (2 ** 8 - 1)
        im2 = im2.astype(np.uint8)


    start_y_c = int(bigger_height / 2 - height / 2)
    start_x_c = int(bigger_width / 2 - width / 2)
    if str(N_) == '7':
        start_y2 = int(bigger_height - height)
        start_x2 = int(bigger_width / 2 - width / 2)
        s_1 = int(start_y2)
        s_2 = int(start_y2 + height*(p_overlap_))
        to_set_to_zero = np.ones(bigger_height, dtype=bool)
        to_set_to_zero[s_1:s_2] = False
        im2[to_set_to_zero] = 0

        s_1 = int(2*start_y_c-height*(p_overlap_))
        s_2 = int(2*start_y_c)
        to_set_to_zero = np.ones(bigger_height, dtype=bool)
        to_set_to_zero[s_1:s_2] = False
        im1[to_set_to_zero] = 0
    elif str(N_) == '2':
        start_y2 = 0
        start_x2 = int(bigger_width / 2 - width / 2)
        s_1 = int(start_y2 + (height*(1-p_overlap_)))
        s_2 = int(start_y2 + height)
        to_set_to_zero = np.ones(bigger_height, dtype=bool)
        to_set_to_zero[s_1:s_2] = False
        im2[to_set_to_zero] = 0

        s_1 = int(start_y_c)
        s_2 = int(start_y_c+height*(p_overlap_))
        to_set_to_zero = np.ones(bigger_height, dtype=bool)
        to_set_to_zero[s_1:s_2] = False
        im1[to_set_to_zero] = 0
    elif str(N_) == '5':
        start_y2 = int(bigger_height / 2 - height / 2)
        start_x2 = 0
        s_1 = int(start_x2 + width * (1-p_overlap_))
        s_2 = int(start_x2 + width )
        to_set_to_zero = np.ones(bigger_width, dtype=bool)
        to_set_to_zero[s_1:s_2] = False
        im2[:, to_set_to_zero] = 0


        s_1 = int(start_x_c )
        s_2 = int(start_x_c + width * (p_overlap_))
        to_set_to_zero = np.ones(bigger_width, dtype=bool)
        to_set_to_zero[s_1:s_2] = False
        im1[:, to_set_to_zero] = 0
    elif str(N_) == '4':
        start_y2 = int(bigger_height / 2 - height / 2)
        start_x2 = int(bigger_width - width)
        s_1 = int(start_x2)
        s_2 = int(start_x2 + width * (p_overlap_))
        to_set_to_zero = np.ones(bigger_width, dtype=bool)
        to_set_to_zero[s_1:s_2] = False
        im2[:, to_set_to_zero] = 0

        s_1 = int(2 * start_x_c - width * (p_overlap_))
        s_2 = int(2 * start_x_c)
        to_set_to_zero = np.ones(bigger_width, dtype=bool)
        to_set_to_zero[s_1:s_2] = False
        im1[:, to_set_to_zero] = 0

    # Calculate the number of rows and columns to keep
    num_rows_to_keep = int(im1.shape[0] * 0.05)
    num_cols_to_keep = int(im1.shape[1] * 0.05)

    # Create boolean masks for rows and columns where either im1 or im2 are not all zeros
    row_mask = ((im1 != 0).any(axis=1) | (im2 != 0).any(axis=1))
    col_mask = ((im1 != 0).any(axis=0) | (im2 != 0).any(axis=0))

    # Add adjacent rows and columns to the masks
    for i in range(1, num_rows_to_keep + 1):
        row_mask[i] = True
        row_mask[-i] = True

    for i in range(1, num_cols_to_keep + 1):
        col_mask[i] = True
        col_mask[-i] = True

    # Filter out rows and columns using the masks
    im1 = im1[row_mask][:, col_mask]
    im2 = im2[row_mask][:, col_mask]

    transfDict = {}
    clusters_registr = dict()
    method2transl = {}
    try:

        try:
            out_reg = imreg_dft.imreg.similarity(im1, im2)
            method2transl['imreg_dft'] = copy.copy(out_reg)
            method2transl['imreg_dft'].pop('timg')
        except Exception as e:
            print('Error stitching imreg_dft')
            print(e)
        try:
            out_reg_ = imreg_dft.imreg.translation(im1, im2)
            method2transl['imreg_dft_no_angle'] = copy.copy(out_reg_)
        except Exception as e:
            print('Error stitching imreg_dft no angle')
            print(e)

        # shift, error, diffphase = phase_cross_correlation(im1, im2,upsample_factor=100) #Fourier, DFT upsampling method
        # out_reg_skimage = imreg_dft.imreg.similarity(corrected_image2, im2)
        try:
            xoff, yoff, exoff, eyoff = chi2_shift(im1, im2)  # Fourier, DFT upsampling method

            method2transl['chi2_no_angle'] = {'tvec': np.asarray((-yoff, -xoff))}
        except Exception as e:
           pass

        '''
        try:
            shift_, error, diffphase = phase_cross_correlation(im1, im2)
            method2transl['phase_cross_correlation_no_angle'] = {'tvec': np.asarray(shift_)}
        except Exception as e:
            pass
        '''

        '''
        ####
        done_aa = False
        try:
            registered_image, footprint = aa.register(im2, im1)
            out_reg_aa = imreg_dft.imreg.similarity(registered_image, im2)
            method2transl['aa'] = copy.copy(out_reg_aa)
            done_aa = True
        except Exception as e:
            pass
        '''

        try:
            corrected_image_cv = cv_registration(im1, im2)
            out_reg_cv = imreg_dft.imreg.translation(im2, corrected_image_cv)
            method2transl['cv2'] = copy.copy(out_reg_cv)
        except Exception as e:
            pass

        '''
        import imageio
        imageio.imwrite('/home/jon/Documents/temp_data/im1.tiff', im1)
        imageio.imwrite('/home/jon/Documents/temp_data/im2.tiff', im2)
        
        '''

        '''
        try:
            register = CrossCorr()
            model = register.fit(im1, reference=im2)
            method2transl['thunder_no_angle'] = {'tvec': np.asarray(model.toarray().tolist()[0])}
        except Exception as e:
            pass
        '''
    except Exception as e:
        err_x = 99999; err_y = 99999
        print('Error stitching for refining registration::', central_, im2_name, 'Error imreg_dft', e)
        return None, image_fixed

    remove_m = set()
    for m1 in method2transl:
        coor_ = method2transl[m1]['tvec']
        if str(N_) == '2':
            if coor_[0] / height > 1.5 * p_overlap_:
                remove_m.add(m1)
            if coor_[0] / height < 0.5 * p_overlap_:
                remove_m.add(m1)
            if abs(coor_[1]) > height * 0.01:
                remove_m.add(m1)
        if str(N_) == '5':
            if coor_[1] / width > 1.5 * p_overlap_:
                remove_m.add(m1)
            if coor_[1] / width < 0.5 * p_overlap_:
                remove_m.add(m1)
            if abs(coor_[0]) > height * 0.01:
                remove_m.add(m1)
        if str(N_) == '4':
            if coor_[1] / width < -1.5 * p_overlap_:
                remove_m.add(m1)
            if coor_[1] / width > -0.5 * p_overlap_:
                remove_m.add(m1)
            if abs(coor_[0]) > height * 0.01:
                remove_m.add(m1)
        if str(N_) == '7':
            if coor_[0] / height < -1.5 * p_overlap_:
                remove_m.add(m1)
            if coor_[0] / height > -0.5 * p_overlap_:
                remove_m.add(m1)
            if abs(coor_[1]) > height * 0.01:
                remove_m.add(m1)

    for key in remove_m:
        if key in method2transl:
            del method2transl[key]

    for m1 in method2transl:
        if len(clusters_registr) == 0:
            clusters_registr[m1] = [m1]
            continue
        d_s_min = 10e99
        c_min = ''
        for c in clusters_registr:
            d_s = []
            for m2 in clusters_registr[c]:
                d_s.append(np.linalg.norm(method2transl[m1]['tvec'] - method2transl[m2]['tvec']))
            d_m = np.mean(d_s)
            if d_m < d_s_min:
                d_s_min = d_m + 0
                c_min = c[:]
        if d_s_min > 10:
            clusters_registr[m1] = [m1]
            continue
        if m1 in ['imreg_dft','cv2']:
            clusters_registr[c_min] += [m1]*2
        else:
            clusters_registr[c_min] += [m1]

    priority_order = ['imreg_dft', 'cv2', 'chi2_no_angle', 'phase_cross_correlation_no_angle',
                      'imreg_dft_no_angle']
    l_clust_v = -1
    for c in clusters_registr:
        if len(clusters_registr[c]) > l_clust_v:
            l_clust_v = len(clusters_registr[c]) + 0

    final_method = None
    for m in priority_order:
        for j in [c for c in clusters_registr if len(clusters_registr[c]) == l_clust_v]:
            if m in clusters_registr[j] and l_clust_v >= 2:
                final_method = m[:]
                break
        if type(final_method) != type(None):
            break


    if type(final_method) == type(None):
        print('inaccurate stitching for refining registration: ', central_, im2_name)
        return None, image_fixed
    else:
        out_reg = method2transl[final_method]
        im2_ori_reg = imreg_dft.imreg.transform_img(image_moving,
                                                    tvec=out_reg['tvec'] * scale).astype(image_fixed.dtype)

        transfDict[N_] = {'tile': im2_name, 'tvec':(out_reg['tvec']*scale).tolist()}
        if do_QC == True:
            reg_matrix8b = (im2_ori_reg / max_value) * 255;
            reg_matrix8b = reg_matrix8b.astype(np.uint8)
            qc_pseudotile = np.concatenate((image_fixed_ori_8b[:, :, np.newaxis], image_fixed_8b[:, :, np.newaxis], reg_matrix8b[:, :, np.newaxis]), axis=2)
            imageio.imwrite(qc_file, qc_pseudotile, format='png')

        new_fixed = np.maximum(image_fixed, im2_ori_reg)

    return transfDict, new_fixed

def cv_registration(img1,img2):
    height, width = img2.shape
    # Create ORB detector with 5000 features.
    orb_detector = cv2.ORB_create(5000)

    # Find keypoints and descriptors.
    # The first arg is the image, second arg is the mask
    #  (which is not required in this case).
    kp1, d1 = orb_detector.detectAndCompute(img1, None)
    kp2, d2 = orb_detector.detectAndCompute(img2, None)

    # Match features between the two images.
    # We create a Brute Force matcher with
    # Hamming distance as measurement mode.
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

    matches = matcher.match(d1, d2)

    # Match the two sets of descriptors.
    # Sort matches on the basis of their Hamming distance.
    #matches.sort(key=lambda x: x.distance)
    d_ = sorted([i.distance for i in matches])[int(len(matches) * 0.9)]
    matches = [i for i in matches if i.distance <= d_]

    # Take the top 90 % matches forward.
    matches = matches[:int(len(matches) * 0.9)]
    no_of_matches = len(matches)

    # Define empty matrices of shape no_of_matches * 2.
    p1 = np.zeros((no_of_matches, 2))
    p2 = np.zeros((no_of_matches, 2))

    for i in range(len(matches)):
        p1[i, :] = kp1[matches[i].queryIdx].pt
        p2[i, :] = kp2[matches[i].trainIdx].pt

    # Find the homography matrix.
    homography, mask = cv2.findHomography(p1, p2, cv2.RANSAC)

    # Use this matrix to transform the
    # colored image wrt the reference image.
    transformed_img = cv2.warpPerspective(img2,
                                          homography, (width, height))
    return transformed_img


def get_tile2coord(df_metadata, input_metadata, channel_meta):

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
                                                tvec=out_reg['tvec']+(r1,r2))
    if np.max(im2_ori_reg[coor_im1_int[0]:coor_im1_int[1], coor_im1_int[2]:coor_im1_int[3]])>0:
        im2_ori_reg = imreg_dft.imreg.transform_img(im2_ori, scale=out_reg['scale'], angle=out_reg['angle'],
                                                    tvec=out_reg['tvec'] + (r1, r2))
        return im2_ori_reg, out_reg['tvec']+(r1,r2), False

    # option 1 for reconstruction
    im2_ori_reg = ndimage.rotate(im2_ori, out_reg['angle'], reshape=False, cval=0)
    im2_ori_reg = ndimage.zoom(im2_ori_reg, (out_reg['scale'], out_reg['scale']))
    im2_ori_reg = ndimage.shift(im2_ori_reg, (int(out_reg['tvec'][0]), int(out_reg['tvec'][1])), mode='wrap')

    return im2_ori_reg, (0,0), True


def zero_inner(image, border_size):
    height, width = image.shape[:2]
    border_height = int(height * border_size)
    border_width = int(width * border_size)

    image[border_height:-border_height, border_width:-border_width] = 0

    return image




def generate_neighbour_stitching(reg_out, dir_central_, central_, p_overlap_, do_QC, channel):
    """Generate reference-round neighbour-stitching json (DAPI; coords applied to all
    channels downstream). Secondary-round counterpart in _neighbour_stitching.py."""
    reg_st_out = os.path.join(reg_out, 'neighbour_stitching')
    input_metadata = [os.path.join(dir_central_, i) for i in os.listdir(dir_central_) if i.endswith('.csv') == True and i.replace('.csv', '') in central_][0]

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

    tile2coor = get_tile2coord(df_metadata, input_metadata, channel)
    im2neighbour = get_neigt(df_metadata, tile2coor)


    im2array = {}
    im1 = io.imread(os.path.join(dir_central_, central_))
    #if '_codex_' in central_:
    #    im1 = im1 * 50
    im2array[central_] = zero_inner(im1, p_overlap_)
    for i in im2neighbour[central_]:
        if len(im2neighbour[central_][i]) > 0:
            im_t = io.imread(os.path.join(dir_central_, im2neighbour[central_][i]))
            #if '_codex_' in central_:
            #    im_t = im_t * 50
            im2array[im2neighbour[central_][i]] = zero_inner(im_t, p_overlap_)

    height, width = im1.shape[:2]
    bigger_height = height * 3
    bigger_width = width * 3


    image_fixed = np.zeros((bigger_height, bigger_width), dtype=im1.dtype)
    start_y = int(bigger_height / 2 - height / 2)
    start_x = int(bigger_width / 2 - width / 2)
    image_fixed[start_y:start_y + height, start_x:start_x + width] = im1

    if not os.path.exists(reg_st_out):
        try:
            os.makedirs(reg_st_out)
        except:
            pass
    qc_file = os.path.join(reg_st_out, central_ + '.png')
    json_file = os.path.join(reg_st_out, central_ + '.json')

    try:
        max_value = np.iinfo(im1.dtype).max
    except:
        max_value = 2**16-1
    image_fixed_ori_8b = (image_fixed / max_value) * 255;
    image_fixed_ori_8b = image_fixed_ori_8b.astype(np.uint8)

    #1-2-3
    #4-*-5
    #6-7-8
    transfDict = {}

    image_fixed_ori = np.copy(image_fixed)
    im2_name = im2neighbour[central_]['d_n']
    if len(im2_name) > 0:
        im2 = im2array[im2_name]
        start_y2 = int(bigger_height - height)
        start_x2 = int(bigger_width / 2 - width / 2)
        image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
        image_moving[start_y2:start_y2 + height, start_x2:start_x2 + width] = im2
        N_ = 7
        t_, image_fixed = do_stitching(central_, image_fixed, image_moving, N_, qc_file, image_fixed_ori_8b, im2_name, do_QC, im2)
        if type(t_) != type(None):
            transfDict[N_] = t_[N_]

    im2_name = im2neighbour[central_]['u_n']
    if len(im2_name) > 0:
        im2 = im2array[im2_name]
        start_y2 = 0
        start_x2 = int(bigger_width / 2 - width / 2)
        image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
        image_moving[start_y2:start_y2 + height, start_x2:start_x2 + width] = im2
        N_ = 2
        t_, image_fixed = do_stitching(central_, image_fixed, image_moving, N_, qc_file, image_fixed_ori_8b, im2_name, do_QC, im2)
        if type(t_) != type(None):
            transfDict[N_] = t_[N_]

    image_fixed_mid = np.copy(image_fixed)
    im2_name = im2neighbour[central_]['r_n']
    if len(im2_name) > 0:
        im2 = im2array[im2_name]
        start_y2 = int(bigger_height / 2 - height / 2)
        start_x2 = 0
        image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
        image_moving[start_y2:start_y2 + height, start_x2:start_x2 + width] = im2
        N_ = 5
        t_, image_fixed = do_stitching(central_, image_fixed, image_moving, N_, qc_file, image_fixed_ori_8b, im2_name, do_QC, im2)
        if type(t_) != type(None):
            transfDict[N_] = t_[N_]

    im2_name = im2neighbour[central_]['l_n']
    if len(im2_name) > 0:
        im2 = im2array[im2_name]
        start_y5 = int(bigger_height / 2 - height / 2)
        start_x5 = int(bigger_width - width)
        image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
        image_moving[start_y5:start_y5 + height, start_x5:start_x5 + width] = im2
        N_ = 4
        t_, image_fixed = do_stitching(central_, image_fixed, image_moving, N_, qc_file, image_fixed_ori_8b, im2_name, do_QC, im2)
        if type(t_) != type(None):
            transfDict[N_] = t_[N_]


    image_fixed = np.zeros((bigger_height, bigger_width), dtype=im1.dtype)
    start_y = int(bigger_height / 2 - height / 2)
    start_x = int(bigger_width / 2 - width / 2)
    image_fixed[start_y:start_y + height, start_x:start_x + width] = im1


    image_fixed_8b = (image_fixed / max_value) * 255;
    image_fixed_8b = image_fixed_8b.astype(np.uint8)
    image_fixed_mid_8b = (image_fixed_mid / max_value) * 255;
    image_fixed_mid_8b = image_fixed_mid_8b.astype(np.uint8)
    qc_pseudotile = np.concatenate((image_fixed_ori_8b[:, :, np.newaxis], image_fixed_8b[:, :, np.newaxis], image_fixed_mid_8b[:, :, np.newaxis]), axis=2)
    imageio.imwrite(qc_file, qc_pseudotile, format='png')

    json.dump(transfDict, open(json_file,'w'))


    '''
    tifffile.imwrite('image_moving.tiff', image_moving)
    tifffile.imwrite('image_fixed.tiff', image_fixed)
    '''


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
    global scale, p_overlap_, channel_meta, do_QC, do_progress, _DO_8BIT

    # --- parameters from config --------------------------------------------
    folder_tiles = cfg.input_dir
    output_folder = cfg.output_reg
    reference_round_number = str(cfg.reference_round)
    n_cores = int(cfg.n_cores)
    channel = cfg.channel
    channel_meta = channel
    do_QC = bool(cfg.register.get("do_qc_stitch", False))
    do_progress = False

    st = cfg.__dict__.get("stitch", {}) if hasattr(cfg, "__dict__") else {}
    _DO_8BIT = bool(st.get("eight_bit", True)) if isinstance(st, dict) else True
    seed = int(st.get("seed", 0)) if isinstance(st, dict) else 0

    # Item 1: deterministic RANSAC (OpenCV global RNG) + numpy seed
    cv2.setRNGSeed(seed)
    np.random.seed(seed)

    # Item 2: overlap is auto-derived from stage positions by the driver below
    # (see "p_overlap_ = np.mean([ovlapp_x, ovlapp_y])"). No hard-coded constant.
    p_overlap_ = 0.1  # placeholder; overwritten per-scene from the manifest geometry
    scale = 1
    _t_start = time.time()

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    os.makedirs(os.path.join(output_folder, "neighbour_stitching"), exist_ok=True)

    #df_nei = pd.read_csv(file_nei)
    # Manifest-driven selection (single source of truth). The manifest, built by
    # digest, already: (a) lists only non-empty acquisitions, and (b) marks the
    # ONE resolved reference image per (slide, scene) as is_reference==True
    # (honouring reference_round + reference_version). We restrict step 1's disk
    # scan to manifest folders (eliminating empty-folder errors) and stitch only
    # the reference folders (so the chosen reference VERSION is honoured rather
    # than an arbitrary disk-order winner).
    _mani = manifest_mod.load(cfg.manifest_path)
    _folder_of = lambda p: os.path.basename(os.path.dirname(str(p)))
    mani_folders = {_folder_of(p) for p in _mani["path"]}
    ref_folders = {_folder_of(p) for p in _mani.loc[_mani["is_reference"] == True, "path"]}  # noqa: E712

    tileFolder2metafile = {}
    all_folders = [f for f in os.listdir(folder_tiles)
                   if f in mani_folders
                   and any(p.startswith('R') and len(p) > 1 and p[1:].isdigit()
                           for p in f.split('_'))]
    all_subfolders = list()
    for fx, f in enumerate(all_folders):
        print('Generating metadata structure',fx, len(all_folders))
        cur_folder = os.path.join(folder_tiles, f)
        if os.path.isdir(cur_folder) == False:
            continue
        metafile_ =  [i for i in os.listdir(cur_folder) if i.endswith('.csv')]

        if len(metafile_) != 1:
            csv_file = cur_folder + '.csv'
            if os.path.exists(csv_file):
                shutil.move(csv_file, os.path.join(cur_folder, f + '.csv'))
                metafile_ = [i for i in os.listdir(cur_folder) if i.endswith('.csv')]

        if len(metafile_) != 1:
            print('ERROR finding metafiles')
            print(os.path.basename(cur_folder))
            print('\n***********'*5)
            continue
        tileFolder2metafile[metafile_[0]] = cur_folder
        all_subfolders.append(cur_folder)

    # /mnt/D_DRIVE/CODEX_DATASET/input_data
    # milan@:192.168.10.74/home/milan/Documents/MILAN_data/CODEX_DATASET
    #scp /mnt/D_DRIVE/BETi_data/connectivityMap/level5_beta_trt_cp_n720216x12328.gctx username@remote_server:/home/milan/Downloads/

    ref_slide_scene = {}
    for curr_d in all_subfolders:
        if os.path.isdir(curr_d) == False:
            continue
        # Stitch only the manifest's resolved reference image for each
        # (slide, scene): is_reference==True encodes both the reference round and
        # the reference version, so this honours reference_version and avoids the
        # version-collision where multiple versions of the reference round exist.
        if os.path.basename(curr_d) not in ref_folders:
            continue
        try:
            curr_R = [j for j in curr_d.split('_') if j.startswith('R') and len(j) > 1 and j[1::].isdigit() == True][0]
        except:
            print(curr_d + ', error extracting round')
            continue
        try:
            curr_S = [j for j in curr_d.split('_') if j.startswith('S') and len(j) > 1 and j[1:-1].isdigit() == True and j.endswith('M') == True]
            if len(curr_S) == 0:
                curr_S = [j for j in curr_d.split('_') if
                          j.startswith('S') and len(j) > 1 and j[1::].isdigit() == True]
            curr_S = curr_S[0]
        except Exception as e:
            print(str(e))
            print(curr_d)
            raise CollageError('Failed to parse the scene/round token from a tile name.') from e
        curr_s = curr_d.split(curr_R)[0]
        ref_slide_scene[curr_s + '****' + curr_S] = os.path.join(folder_tiles, curr_d)


    all_centrals = []
    for s in ref_slide_scene:
        for i in os.listdir(ref_slide_scene[s]):
            if i.endswith('tiff') == False:
                continue
            curr_S = [j for j in i.split('_') if j.startswith('S') and len(j) > 1 and j.replace('S','').replace('M','').isdigit() == True and 'M' in j][0]
            chan = i.split(curr_S+'_')[1].split('.tiff')[0]
            if chan != channel:
                continue
            all_centrals.append({'dir_central_': ref_slide_scene[s], 'central_': i})

    for d_ in all_centrals:
        input_metadata = [os.path.join(d_['dir_central_'], i) for i in os.listdir(d_['dir_central_']) if
                          i.endswith('.csv') == True and i.replace('.csv', '') in d_['central_']][0]

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

        tile2coor = get_tile2coord(df_metadata, input_metadata, channel)

        all_x = sorted(list(set([tile2coor[i][0] for i in tile2coor])))
        all_y = sorted(list(set([tile2coor[i][1] for i in tile2coor])))
        ovlapp_x = 1 - abs(all_x[0] - all_x[1]) / np_x
        ovlapp_y = 1 - abs(all_y[0] - all_y[1]) / np_y

        if abs(ovlapp_x - ovlapp_y) > 0.001:
            #not_consistent_overlap
            print('Not consistent overlap!!!!!')
        p_overlap_ = np.mean([ovlapp_x, ovlapp_y])
        break

    failed_elements = []
    c2p = {c: None for c in range(n_cores)}
    c2a_c = {c: None for c in range(n_cores)}
    for input_metadatax, input_metadata in enumerate(all_centrals): #PARALELIZAR ESTE BUCLE!
        #time.sleep(0.2)
        if do_progress == True:
            ws = aux_func.send_task_evolution(ws, int(input_metadatax/len(all_centrals) * 1000) / 10 , ind_, server_id)
        #if 'GC39BT' not in input_metadata['central_'] or 'M102' not in input_metadata['central_']:
        #    continue

        if n_cores == 1:
            print('Generating exhaustive stitching...', input_metadatax, '/', len(all_centrals), input_metadata['central_'])
            generate_neighbour_stitching(output_folder, input_metadata['dir_central_'], input_metadata['central_'], p_overlap_, do_QC, channel)
        else:
            while True:
                time.sleep(0.1)
                c_core = -1
                for c in c2p:
                    if type(c2p[c]) == type(None):
                        c_core = c + 0
                        break
                    elif c2p[c].is_alive() == False:
                        if os.path.isfile(os.path.join(output_folder, 'neighbour_stitching', c2a_c[c]['central_'] + '.json')) == False:
                            failed_elements.append(c2a_c[c])
                        c_core = c + 0
                        break

                if c_core != -1:
                    break

            print('Generating exhaustive stitching...', input_metadatax, '/', len(all_centrals))
            p = Process(target= generate_neighbour_stitching,  args=(output_folder, input_metadata['dir_central_'], input_metadata['central_'], p_overlap_, do_QC , channel), )
            p.start()
            c2p[c_core] = p
            c2a_c[c_core] = input_metadata
            continue

            # iter_data = json.load(open(os.path.join(output_folder, patient+ '.json'), 'r'))

    while True:
        time.sleep(0.1)
        c_core = -1
        do_break = True
        for c in c2p:
            if type(c2p[c]) == type(None):
                continue
            elif c2p[c].is_alive() == True:
                do_break = False
                break
            else:
                c2p[c] = None
                if os.path.isfile(os.path.join(output_folder, 'neighbour_stitching', c2a_c[c]['central_'] + '.json')) == False:
                    failed_elements.append(c2a_c[c])


        if do_break == True:
            print('Done all cores')
            break

    for input_metadatax, input_metadata in enumerate(failed_elements): #PARALELIZAR ESTE BUCLE!
        if do_progress == True:
            ws = aux_func.send_task_evolution(ws, int(input_metadatax/len(failed_elements) * 1000) / 10 , ind_, server_id)
        print('RE-Generating exhaustive stitching...', input_metadatax, '/', len(failed_elements), input_metadata['central_'])
        try:
            generate_neighbour_stitching(output_folder, input_metadata['dir_central_'], input_metadata['central_'], p_overlap_, do_QC, channel)
        except Exception as e:
            print('**********\n*5')
            print('Error in Re-Generating exhaustive stitching')
            print(str(e))
            print('**********\n*5')

    all_json = [os.path.join(output_folder, 'neighbour_stitching',i) for i in os.listdir(os.path.join(output_folder, 'neighbour_stitching')) if i.endswith('.json')]

    # Create an undirected graph


    folder2tiles = dict()
    for c in all_centrals:
        if c['dir_central_'] not in folder2tiles:
            folder2tiles[c['dir_central_']] = []
        folder2tiles[c['dir_central_']].append(c['central_'])

    for folderx, folder in enumerate(folder2tiles):
        #if 'KID1_R01_V1_KIDNEY_YVH_S1M' not in folder:
            #continue

        G = nx.Graph()
        print('Exporting stitching results', folderx, len(folder2tiles))
        input_metadata = [os.path.join(folder, i) for i in os.listdir(folder) if i.endswith('.csv') == True][0]

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

        tile2coor = get_tile2coord(df_metadata, input_metadata, channel)

        central2path = dict()
        for c in all_centrals:
            if os.path.basename(folder) not in c['central_']:
                continue
            for j in all_json:
                if j.endswith('json') == True and c['central_'] in j:
                    central2path[c['central_']] = j
                    break


        #1-2-3
        #4-*-5
        #6-7-8
        central2count = dict()
        central2json = dict()
        for c in all_centrals:
            if os.path.basename(folder) not in c['central_'] :
                continue
            if c['central_'] not in central2path:
                continue
            f_ = central2path[c['central_']]
            json_ = json.load(open(f_,'r'))
            central2json[c['central_']] = json_
            for j in json_:
                t_ = json_[j]['tile']
                if c['central_'] not in central2count:
                    central2count[c['central_']] = 0
                central2count[c['central_']] += 1

        for c in central2path:
            if c not in central2count:
                central2count[c] = 0
            if c not in central2json:
                f_ = central2path[c]
                json_ = json.load(open(f_, 'r'))
                central2json[c] = json_


        central2coor = dict()
        done_central = set()
        all_im = dict()
        for o in sorted(set(list(central2count.values())[::-1])):

            all_o = [i for i in central2count if central2count[i] == o]
            for c in all_o:
                #if 'GC15OT_R01_V01_CODEX_JP_S0M1' not in c:
                    #continue
                if c not in central2json:
                    continue
                nodes_add_this_iter = [c]
                arcs_add_this_iter = []



                central2coor[c] = {}
                central2coor[c][0]= (0,0)

                if c not in all_im:
                    all_im[c] = io.imread(os.path.join(folder, c))


                height, width = all_im[c].shape[:2]
                bigger_height = height * 3
                bigger_width = width * 3

                for n in central2json[c]:
                    im2_name = central2json[c][n]['tile']
                    coor_ = central2json[c][n]['tvec']
                    if n == '2':
                        if coor_[0] / height > 1.5 * p_overlap_:
                            continue
                        if coor_[0] / height < 0.5 * p_overlap_:
                            continue
                        if abs(coor_[1]) > height * 0.01:
                            continue

                        if im2_name not in all_im:
                            all_im[im2_name] = io.imread(os.path.join(folder, im2_name))

                        start_y2 = 0
                        start_x2 = - int(height)

                        m_cols = start_y2 + central2coor[c][0][1] + coor_[1]
                        m_rows = start_x2 + central2coor[c][0][0] + coor_[0]


                        central2coor[c][im2_name] = (int(m_rows), int(m_cols))
                        nodes_add_this_iter.append(im2_name)
                        arcs_add_this_iter.append((c, im2_name))


                    if n == '5':

                        if coor_[1]/width > 1.5*p_overlap_:
                            continue
                        if coor_[1]/width < 0.5*p_overlap_:
                            continue
                        if abs(coor_[0]) > height*0.01:
                            continue

                        if np.max(np.abs(coor_)) > 300:
                            continue
                        if im2_name not in all_im:
                            all_im[im2_name] = io.imread(os.path.join(folder, im2_name))

                        start_y2 = - int(width)
                        start_x2 = 0

                        m_cols = start_y2 + central2coor[c][0][1] + coor_[1]
                        m_rows = start_x2 + central2coor[c][0][0] + coor_[0]


                        central2coor[c][im2_name] = (int(m_rows), int(m_cols))
                        nodes_add_this_iter.append(im2_name)
                        arcs_add_this_iter.append((c, im2_name))


                    if n == '4':

                        if coor_[1]/width < -1.5*p_overlap_:
                            continue
                        if coor_[1]/width > -0.5*p_overlap_:
                            continue
                        if abs(coor_[0]) > height*0.01:
                            continue

                        if np.max(np.abs(coor_)) > 300:
                            continue
                        if im2_name not in all_im:
                            all_im[im2_name] = io.imread(os.path.join(folder, im2_name))

                        start_y2 = + int(width)
                        start_x2 = 0

                        m_cols = start_y2 + central2coor[c][0][1] + coor_[1]
                        m_rows = start_x2 + central2coor[c][0][0] + coor_[0]

                        central2coor[c][im2_name] = (int(m_rows), int(m_cols))
                        nodes_add_this_iter.append(im2_name)
                        arcs_add_this_iter.append((c, im2_name))



                    if n == '7':

                        if coor_[0]/height < -1.5*p_overlap_:
                            continue
                        if coor_[0]/height > -0.5*p_overlap_:
                            continue
                        if abs(coor_[1]) > height*0.01:
                            continue

                        if im2_name not in all_im:
                            all_im[im2_name] = io.imread(os.path.join(folder, im2_name))

                        start_y2 = 0
                        start_x2 = + int(height)

                        m_cols = start_y2 + central2coor[c][0][1] + coor_[1]
                        m_rows = start_x2 + central2coor[c][0][0] + coor_[0]

                        central2coor[c][im2_name] = (int(m_rows), int(m_cols))
                        nodes_add_this_iter.append(im2_name)
                        arcs_add_this_iter.append((c, im2_name))

                G.add_nodes_from(nodes_add_this_iter)
                G.add_edges_from(arcs_add_this_iter)

        connected_components = list(nx.connected_components(G))
        central2coor_final = {}
        cluster_central2coor_final = {}
        is_fixed_pos = set()
        for compx, comp in enumerate(connected_components):
            if len(comp) > 2:
                lol=0

            central = []
            neq = 0
            for c in central2coor:
                if c in comp or len(comp.intersection(set(central2coor[c].values()))) > 0:
                    central.append(c)
                    neq += len(central2coor[c]) - 1
            fixed_c = central[0]
            is_fixed_pos.add(fixed_c)

            var2posi = {}
            for c in central:
                if len(var2posi) == 0:
                    var2posi[c + '_X'] = 0
                    var2posi[c + '_Y'] = 1
                elif c + '_X' not in var2posi:
                    var2posi[c + '_X'] = max(var2posi.values()) + 1
                    var2posi[c + '_Y'] = max(var2posi.values()) + 1
                for n in central2coor[c]:
                    if n == 0:
                        continue
                    if n + '_X' not in var2posi:
                        var2posi[n + '_X'] = max(var2posi.values()) + 1
                        var2posi[n + '_Y'] = max(var2posi.values()) + 1
                    if 'epsilon___' + c + '___'+ n + '_X' not in var2posi:
                        var2posi['epsilon___' + c + '___'+ n + '_X'] = max(var2posi.values()) + 1
                        var2posi['delta___' + c + '___'+ n + '_X'] = max(var2posi.values()) + 1
                        var2posi['epsilon___' + c + '___'+ n + '_Y'] = max(var2posi.values()) + 1
                        var2posi['delta___' + c + '___'+ n + '_Y'] = max(var2posi.values()) + 1


            nvars = len(var2posi)
            neq += 2 #fixing fixed_c coordinates
            c_obj = np.array([0]*nvars)
            bounds = []
            for i in var2posi:
                if i.startswith('epsilon___') == True or i.startswith('delta___') == True:
                    c_obj[var2posi[i]] = 1
                    bounds.append((0, None))
                else:
                    bounds.append((None, None))

            A_eq = []
            b_eq = []
            for c in central:
                for n in central2coor[c]:
                    if n == 0:
                        continue
                    t_ = [0] * nvars
                    t_[var2posi[c + '_X']] = -1
                    t_[var2posi[n + '_X']] = 1
                    t_[var2posi['epsilon___' + c + '___'+ n + '_X']] = 1
                    t_[var2posi['delta___' + c + '___'+ n + '_X']] = -1
                    A_eq.append(t_)
                    b_eq.append(central2coor[c][n][1])
                    t_ = [0] * nvars
                    t_[var2posi[c + '_Y']] = -1
                    t_[var2posi[n + '_Y']] = 1
                    t_[var2posi['epsilon___' + c + '___'+ n + '_Y']] = 1
                    t_[var2posi['delta___' + c + '___'+ n + '_Y']] = -1
                    A_eq.append(t_)
                    b_eq.append(central2coor[c][n][0])

            t_ = [0] * nvars
            t_[var2posi[fixed_c + '_X']] = 1
            A_eq.append(t_)
            b_eq.append(tile2coor[fixed_c][0])
            t_ = [0] * nvars
            t_[var2posi[fixed_c + '_Y']] = 1
            A_eq.append(t_)
            b_eq.append(tile2coor[fixed_c][1])

            result = linprog(c_obj, A_eq=np.array(A_eq), b_eq=np.array(b_eq), bounds=bounds, method='highs')
            error_ = 0
            for i in var2posi:
                if i.startswith('epsilon___') == True or i.startswith('delta___') == True:
                    error_ += result.x[var2posi[i]]
                    continue
                if i.endswith('X') == False and i.endswith('Y') == False:
                    continue
                i_ = i[0:-2]

                if compx not in cluster_central2coor_final:
                    cluster_central2coor_final[compx] = {}
                if i_ not in cluster_central2coor_final[compx]:
                    cluster_central2coor_final[compx][i_] = [[0, 0]]
                if i.endswith('X'):
                    cluster_central2coor_final[compx][i_][0][1] = int(np.round(result.x[var2posi[i]]))
                elif i.endswith('Y'):
                    cluster_central2coor_final[compx][i_][0][0] = int(np.round(result.x[var2posi[i]]))

        cluster_central2coor_final_ = copy.copy(cluster_central2coor_final)
        clu = [xc for xc in cluster_central2coor_final_ if len(cluster_central2coor_final_[xc]) == max(
            [len(cluster_central2coor_final_[cx]) for cx in cluster_central2coor_final_])][0]
        for i in cluster_central2coor_final_[clu]:
            if i in central2coor_final:
                raise ReconstructionError('Invariant violated: tile already assigned a cluster position (should not happen).')
            central2coor_final[i] = cluster_central2coor_final_[clu][i]
        del cluster_central2coor_final_[clu]

        while len(cluster_central2coor_final_) > 0:
            d_ = dict()
            for cl in cluster_central2coor_final_:
                for i in cluster_central2coor_final_[cl]:
                    for j in central2coor_final:
                        d_[(cl,i,j)] = np.linalg.norm(np.array( cluster_central2coor_final_[cl][i][0]) - np.array(central2coor_final[j][0]))
            m_ = [i for i in d_ if min(d_.values()) == d_[i]][0]

            des_basic = np.array(tile2coor[m_[1]][::-1]) - np.array(tile2coor[m_[2]][::-1])
            des_opti = np.array(cluster_central2coor_final_[m_[0]][m_[1]][0]) - np.array(central2coor_final[m_[2]][0])
            correction = des_basic - des_opti
            clu = m_[0]
            for i in cluster_central2coor_final_[clu]:
                if i in central2coor_final:
                    raise ReconstructionError('Invariant violated: tile already assigned a cluster position (should not happen).')
                central2coor_final[i] =[list(np.array(cluster_central2coor_final_[clu][i][0])+correction)]
            del cluster_central2coor_final_[clu]

        max_rows = max([all_im[i].shape[0] for i in all_im])
        max_cols = max([all_im[i].shape[1] for i in all_im])

        max_x = max(coord[0] + max_rows for coords in central2coor_final.values() for coord in coords)
        max_y = max(coord[1] + max_cols for coords in central2coor_final.values() for coord in coords)
        min_x = min(coord[0] - max_rows for coords in central2coor_final.values() for coord in coords)
        min_y = min(coord[1] - max_cols for coords in central2coor_final.values() for coord in coords)

        nr = int(max_x - min_x)
        nc = int(max_y - min_y)
        final_image = np.zeros((nr, nc), dtype=all_im[list(all_im.keys())[0]].dtype)
        final_image_qc = np.zeros((nr, nc, 3),  dtype='uint8')

        im2color = dict()
        coors2color = {(-92999999, 0):'r', (-999919999, 99929999):'g', (-919999999, -999999299):'b'}

        coor2export = {}
        for i in central2coor_final:
            coords = tuple(central2coor_final[i][0])
            dist2color = {(coords[0]-c[0])**2+(coords[0]-c[0])**2:coors2color[c] for c in coors2color}
            color_ = set()
            final_color = -1
            for d in sorted(dist2color.keys()):
                if len(color_) < 2:
                    color_.add(dist2color[d])
                elif dist2color[d] in color_:
                    continue
                else:
                    if dist2color[d] == 'r':
                        im2color[i] = 0
                    if dist2color[d] == 'g':
                        im2color[i] = 1
                    if dist2color[d] == 'b':
                        im2color[i] = 2
                    coors2color[coords] = dist2color[d]
                    break
            row_ini = int(coords[0] - all_im[i].shape[0]/2 - min_x)
            col_ini = int(coords[1] - all_im[i].shape[1]/2 - min_y)
            row_fin = row_ini + int(all_im[i].shape[0])
            col_fin = col_ini + int(all_im[i].shape[1])
            final_image[row_ini:row_fin, col_ini:col_fin] = all_im[i]
            # --- QC rendering -------------------------------------------------
            # Render each tile in its assigned colour channel, with a per-tile
            # contrast stretch so the (typically dim) tissue is visible. Anchor
            # (fixed-position) tiles get a thin, subtle light-grey border instead
            # of a full-brightness coloured outline, so they no longer dominate.
            try:
                mmax = np.iinfo(all_im[i].dtype).max
            except Exception:
                mmax = 2 ** 16 - 1
            if all_im[i].dtype.type != np.uint8:
                im_8b = (all_im[i].astype(np.float64) * 255.0 / mmax).astype(np.uint8)
            else:
                im_8b = np.copy(all_im[i])

            # Per-tile contrast stretch over non-zero (tissue) pixels: map
            # [p_low, p_high] -> [0, 255] so faint tissue becomes visible without
            # the black background dominating the scaling. Near-empty tiles
            # (< 50 signal px) are left untouched to avoid amplifying noise.
            _nz = im_8b[im_8b > 0]
            if _nz.size >= 50:
                _lo = float(np.percentile(_nz, 1.0))
                _hi = float(np.percentile(_nz, 99.5))
                if _hi > _lo:
                    _f = (im_8b.astype(np.float32) - _lo) * (255.0 / (_hi - _lo))
                    im_8b = np.clip(_f, 0, 255).astype(np.uint8)

            final_image_qc[row_ini:row_fin, col_ini:col_fin, im2color[i]] = im_8b

            # Subtle light-grey border for anchor (fixed-position) tiles: thin and
            # written to all three channels (grey) so it marks the anchor without
            # the previous bright single-colour outline.
            if i in is_fixed_pos:
                _h, _w = im_8b.shape
                _bs = max(1, int(min(_h, _w) * 0.01))
                _grey = 90
                final_image_qc[row_ini:row_ini + _bs, col_ini:col_fin, :] = _grey
                final_image_qc[row_fin - _bs:row_fin, col_ini:col_fin, :] = _grey
                final_image_qc[row_ini:row_fin, col_ini:col_ini + _bs, :] = _grey
                final_image_qc[row_ini:row_fin, col_fin - _bs:col_fin, :] = _grey

            coor2export[i] = [(row_ini, row_fin), (col_ini, col_fin)]

        '''
        flattened_image = final_image_qc.flatten()
        percentile_99 = np.percentile(flattened_image, 99)

        # Step 2: Threshold the values above the 99th percentile to 255
        final_image_qc[final_image_qc > percentile_99] =  np.iinfo(im_8b.dtype).max
        '''
        if not os.path.exists(os.path.join(output_folder, 'stitching_QC_plots')):
            try:
                os.makedirs(os.path.join(output_folder, 'stitching_QC_plots'))
            except:
                pass

        qc_file_folder = os.path.join(output_folder, 'stitching_QC_plots', os.path.basename(folder) + '.png')
        imageio.imwrite(qc_file_folder, final_image_qc)


        if not os.path.exists(os.path.join(output_folder, 'stitching_coords')):
            try:
                os.makedirs(os.path.join(output_folder, 'stitching_coords'))
            except:
                pass
        final_file_folder = os.path.join(output_folder, 'stitching_coords')
        if not os.path.exists(final_file_folder):
            try:
                os.makedirs(final_file_folder)
            except:
                pass

        final_file_path = os.path.join(final_file_folder, os.path.basename(folder) + '.json')
        json.dump(coor2export, open(final_file_path, 'w'))




    # Item 5: record what produced these outputs
    _run_manifest = {
        "step": "1_stitch",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "project_dir": cfg.project_dir,
        "input_dir": folder_tiles,
        "reference_round": cfg.reference_round,
        "channel": channel,
        "n_cores": n_cores,
        "overlap_fraction": p_overlap_,
        "eight_bit": _DO_8BIT,
        "seed": seed,
        "duration_sec": round(time.time() - _t_start, 1),
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "opencv": cv2.__version__,
            "pandas": pd.__version__,
        },
    }
    _rm_path = os.path.join(output_folder, "run_manifest_step1.json")
    with open(_rm_path, "w") as _fh:
        json.dump(_run_manifest, _fh, indent=2, default=_json_safe)
    print(f"  run manifest: {_rm_path}")

    # Item 3: surface failures instead of letting tiles silently vanish.
    _nbr = os.path.join(output_folder, "neighbour_stitching")
    _n_ok = len([f for f in os.listdir(_nbr) if f.endswith(".json")]) if os.path.isdir(_nbr) else 0
    try:
        _mani = manifest_mod.load(cfg.manifest_path)
        _expected = _mani[(_mani["round"] == cfg.reference_round) &
                          (_mani["channel"] == channel)][["scene", "tile"]].drop_duplicates().shape[0]
    except Exception:
        _expected = None
    if _n_ok == 0:
        raise RuntimeError(
            "Step 1 produced no stitching transforms. Common cause: tiles could "
            "not be read (e.g. compressed TIFF needing the 'imagecodecs' package). "
            "Check the log above for per-tile errors."
        )
    if _expected is not None and _n_ok < _expected:
        print(f"  WARNING: stitched {_n_ok}/{_expected} reference tiles; "
              f"{_expected - _n_ok} failed (see log above).")
    else:
        print(f"  stitched {_n_ok} reference tiles.")
