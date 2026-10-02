"""Neighbour-stitching helpers for the SECONDARY rounds, used by step 3.

IMPORTANT - this is NOT an accidental duplicate of the functions in
``step1_stitch.py``. step 1 stitches the tiles of the REFERENCE round only
(it filters to ``reference_round``), computing the intra-round mosaic on DAPI
and reusing those coordinates for every channel. The secondary (moving) rounds
are never stitched by step 1.

These functions provide a secondary-round stitching used by step 3 as a
GAP-FILLING fallback: when the pairwise-registered tiles from step 2 leave a
hole in coverage (``np.min(overlap_matrix) == 0``), step 3 stitches the moving
round's neighbour tiles here to patch the gap and refine the registration.

The two implementations share an ancestor and the same ``imreg`` registration
primitive, but they have intentionally diverged - step 1's ``do_stitching`` is
the more elaborate version (directional-position overlap masking for N=2/5/7,
plus phase-correlation refinement), while this one is the simpler variant.
They are kept separate on purpose; unifying them is an algorithmic decision for
a future version, not a mechanical de-duplication (it would change registration
output). See step1_stitch.py for the reference-round counterpart.

Copied from legacy additional_codes/neighbour_stitching.py (functions only;
the trailing hard-coded test block was removed).
"""
from .. import _compat  # noqa: F401
from ..errors import CollageError, MetadataError, MissingInputError, ConsensusError, ReconstructionError

def do_stitching(central_, image_fixed, image_moving, N_, qc_file, image_fixed_ori_8b, im2_name, do_QC):
    """Secondary-round neighbour stitch (simpler imreg variant). See module docstring;
    the elaborate reference-round counterpart is step1_stitch.do_stitching."""
    # Resize the image using OpenCV's resize function
    scale = 1

    max_value = np.iinfo(image_fixed.dtype).max
    image_fixed_8b = (image_fixed / max_value) * 255;
    image_fixed_8b = image_fixed_8b.astype(np.uint8)

    if scale != 1:
        # Get the current dimensions of the image
        height, width = image_fixed.shape
        # Calculate the new dimensions after reducing the size by a factor of 5
        new_height = height // scale
        new_width = width // scale
        image_fixed_red = cv2.resize(image_fixed, (new_width, new_height))
        image_moving_red = cv2.resize(image_moving, (new_width, new_height))

    transfDict = {}
    method2transl = {}
    try:


        if scale != 1:
            out_reg = imreg_dft.imreg.similarity(image_fixed_red, image_moving_red)
            method2transl['imreg_dft'] = copy.copy(out_reg)

            out_reg_ = imreg_dft.imreg.translation(image_fixed_red, image_moving_red)
            method2transl['imreg_dft_no_angle'] = copy.copy(out_reg_)

            out_reg_['tvec'] = out_reg_['tvec'] * scale
            out_reg['tvec'] = out_reg['tvec'] * scale
        else:
            out_reg = imreg_dft.imreg.similarity(image_fixed, image_moving)
            method2transl['imreg_dft'] = copy.copy(out_reg)

            out_reg_ = imreg_dft.imreg.translation(image_fixed, image_moving)
            method2transl['imreg_dft_no_angle'] = copy.copy(out_reg_)

        err_x = abs(out_reg['tvec'][0] - out_reg_['tvec'][0])
        err_y = abs(out_reg['tvec'][1] - out_reg_['tvec'][1])
    except Exception as e:
        err_x = 99999; err_y = 99999
        print('Error stitching for refining registration::', central_, im2_name, 'Error imreg_dft', e)
        return None, image_fixed

    if err_x > 20 or err_y > 20:
        print('inaccurate stitching for refining registration: ', central_, im2_name)
        return None, image_fixed
    else:
        im2_ori_reg = imreg_dft.imreg.transform_img(image_moving, scale=out_reg['scale'], angle=out_reg['angle'],
                                                    tvec=out_reg['tvec']).astype(image_fixed.dtype)

        transfDict[N_] = {'tile': im2_name, 'scale':out_reg['scale'], 'angle':out_reg['angle'], 'tvec':out_reg['tvec'].tolist()}
        if do_QC == True:
            reg_matrix8b = (im2_ori_reg / max_value) * 255;
            reg_matrix8b = reg_matrix8b.astype(np.uint8)
            qc_pseudotile = np.concatenate((image_fixed_ori_8b[:, :, np.newaxis], image_fixed_8b[:, :, np.newaxis], reg_matrix8b[:, :, np.newaxis]), axis=2)
            imageio.imwrite(qc_file, qc_pseudotile, format='png')
        new_fixed = np.copy(image_fixed)
        #new_fixed[im2_ori_reg>0] = im2_ori_reg[im2_ori_reg>0]
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


def get_tile2coord(df_metadata, input_metadata):
    channel_meta = globals().get('channel_meta', 'DAPI')  # module global if set, else DAPI
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



from scipy import ndimage
import os
import imreg_dft
import json
import  numpy as np
import copy
from skimage import io
import imageio
import tifffile
import pandas as pd
import sys
import cv2
cv2.setNumThreads(1)  # parallelism is at the process level (n_cores workers); an
                      # uncapped per-process OpenCV thread pool oversubscribes the box

def generate_neighbour_stitching(reg_out, dir_central_, central_, p_overlap_, do_QC):
    """Generate secondary-round neighbour-stitching json (gap-filling fallback for
    step 3). Reference-round counterpart: step1_stitch.generate_neighbour_stitching."""
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

    tile2coor = get_tile2coord(df_metadata, input_metadata)
    im2neighbour = get_neigt(df_metadata, tile2coor)


    im2array = {}
    im1 = io.imread(os.path.join(dir_central_, central_))
    if '_codex_' in central_:
        im1 = im1 * 50
    im2array[central_] = zero_inner(im1, p_overlap_)
    for i in im2neighbour[central_]:
        if len(im2neighbour[central_][i]) > 0:
            im_t = io.imread(os.path.join(dir_central_, im2neighbour[central_][i]))
            if '_codex_' in central_:
                im_t = im_t * 50
            im2array[im2neighbour[central_][i]] = zero_inner(im_t, p_overlap_)

    height, width = im1.shape[:2]
    bigger_height = height * 3
    bigger_width = width * 3


    image_fixed = np.zeros((bigger_height, bigger_width), dtype=im1.dtype)
    start_y = int(bigger_height / 2 - height / 2)
    start_x = int(bigger_width / 2 - width / 2)
    image_fixed[start_y:start_y + height, start_x:start_x + width] = im1

    if not os.path.exists(reg_st_out):
        os.makedirs(reg_st_out)
    qc_file = os.path.join(reg_st_out, central_ + '.png')
    json_file = os.path.join(reg_st_out, central_ + '.json')

    max_value = np.iinfo(im1.dtype).max
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
        t_, image_fixed = do_stitching(central_, image_fixed, image_moving, N_, qc_file, image_fixed_ori_8b, im2_name, do_QC)
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
        t_, image_fixed = do_stitching(central_, image_fixed, image_moving, N_, qc_file, image_fixed_ori_8b, im2_name, do_QC)
        if type(t_) != type(None):
            transfDict[N_] = t_[N_]

    im2_name = im2neighbour[central_]['r_n']
    if len(im2_name) > 0:
        im2 = im2array[im2_name]
        start_y2 = int(bigger_height / 2 - height / 2)
        start_x2 = 0
        image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
        image_moving[start_y2:start_y2 + height, start_x2:start_x2 + width] = im2
        N_ = 5
        t_, image_fixed = do_stitching(central_, image_fixed, image_moving, N_, qc_file, image_fixed_ori_8b, im2_name, do_QC)
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
        t_, image_fixed = do_stitching(central_, image_fixed, image_moving, N_, qc_file, image_fixed_ori_8b, im2_name, do_QC)
        if type(t_) != type(None):
            transfDict[N_] = t_[N_]


    im2_name = im2neighbour[central_]['l_n']
    im3_name = im2neighbour[central_]['d_n']
    if len(im2_name) > 0 and len(im3_name) > 0 and False:
        im2_1 = im2neighbour[im2_name]['d_n']
        im2_2 = im2neighbour[im3_name]['l_n']
        if im2_1 != im2_2:
            print('Not matching neigh for refining registration:', im2_name, 'u_n', im3_name, 'l_n')
        elif len(im2_1) > 0:
            im_t = io.imread(os.path.join(dir_central_, im2_1))
            if '_codex_' in central_:
                im_t = im_t * 50
            im2 = zero_inner(im_t, p_overlap_)
            start_y2 = int(bigger_height - height)
            start_x5 = int(bigger_width - width)
            image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
            image_moving[start_y2:start_y2 + height, start_x5:start_x5 + width] = im2
            N_ = 8
            t_, image_fixed = do_stitching(central_, image_fixed, image_moving, N_, qc_file, image_fixed_ori_8b, im2_2, do_QC)
            if type(t_) != type(None):
                transfDict[N_] = t_[N_]

    im2_name = im2neighbour[central_]['l_n']
    im3_name = im2neighbour[central_]['u_n']
    if len(im2_name) > 0 and len(im3_name) > 0 and False:
        im2_1 = im2neighbour[im2_name]['u_n']
        im2_2 = im2neighbour[im3_name]['l_n']

        if im2_1 != im2_2:
            print('Not matching neigh for refining registration:', im2_name, 'u_n', im3_name, 'l_n')
        elif len(im2_1) > 0:
            im_t = io.imread(os.path.join(dir_central_, im2_1))
            if '_codex_' in central_:
                im_t = im_t * 50
            im2 = zero_inner(im_t, p_overlap_)
            start_y2 = 0
            start_x5 = int(bigger_width - width)
            image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
            image_moving[start_y2:start_y2 + height, start_x5:start_x5 + width] = im2
            N_ = 3
            t_, image_fixed = do_stitching(central_, image_fixed, image_moving, N_, qc_file, image_fixed_ori_8b, im2_2, do_QC)
            if type(t_) != type(None):
                transfDict[N_] = t_[N_]


    im2_name = im2neighbour[central_]['r_n']
    im3_name = im2neighbour[central_]['u_n']
    if len(im2_name) > 0 and len(im3_name) > 0 and False:
        im2_1 = im2neighbour[im2_name]['u_n']
        im2_2 = im2neighbour[im3_name]['r_n']
        if im2_1 != im2_2:
            print('Not matching neigh for refining registration:', im2_name, 'u_n', im3_name, 'l_n')
        elif len(im2_1) > 0:
            im_t = io.imread(os.path.join(dir_central_, im2_1))
            if '_codex_' in central_:
                im_t = im_t * 50
            im2 = zero_inner(im_t, p_overlap_)
            start_y2 = 0
            start_x5 = 0
            image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
            image_moving[start_y2:start_y2 + height, start_x5:start_x5 + width] = im2
            N_ = 1
            t_, image_fixed = do_stitching(central_, image_fixed, image_moving, N_, qc_file, image_fixed_ori_8b, im2_2, do_QC)
            if type(t_) != type(None):
                transfDict[N_] = t_[N_]


    im2_name = im2neighbour[central_]['r_n']
    im3_name = im2neighbour[central_]['d_n']
    if len(im2_name) > 0 and len(im3_name) > 0 and False:
        im2_1 = im2neighbour[im2_name]['d_n']
        im2_2 = im2neighbour[im3_name]['r_n']
        if im2_1 != im2_2:
            print('Not matching neigh for refining registration:', im2_name, 'u_n', im3_name, 'l_n')
        elif len(im2_1) > 0:
            im_t = io.imread(os.path.join(dir_central_, im2_1))
            if '_codex_' in central_:
                im_t = im_t * 50
            im2 = zero_inner(im_t, p_overlap_)
            start_y2 = int(bigger_height - height)
            start_x5 = 0
            image_moving = np.zeros((bigger_height, bigger_width), dtype=image_fixed.dtype)
            image_moving[start_y2:start_y2 + height, start_x5:start_x5 + width] = im2
            N_ = 6
            t_, image_fixed = do_stitching(central_, image_fixed, image_moving, N_, qc_file, image_fixed_ori_8b, im2_2, do_QC)
            if type(t_) != type(None):
                transfDict[N_] = t_[N_]

    image_fixed_8b = (image_fixed / max_value) * 255;
    image_fixed_8b = image_fixed_8b.astype(np.uint8)
    qc_pseudotile = np.concatenate((image_fixed_ori_8b[:, :, np.newaxis], image_fixed_8b[:, :, np.newaxis], image_fixed_8b[:, :, np.newaxis]*0), axis=2)
    imageio.imwrite(qc_file, qc_pseudotile, format='png')

    json.dump(transfDict, open(json_file,'w'))


    '''
    tifffile.imwrite('image_moving.tiff', image_moving)
    tifffile.imwrite('image_fixed.tiff', image_fixed)
    '''


