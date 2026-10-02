"""Step 2 - Consensus registration (migrated).

Builds the tile-pair graph between the reference round and each moving round,
computes a rigid transform per overlapping pair using several registration
backends, filters false positives with AlignQC, and averages the survivors into
a consensus transform. Most compute-intensive step.

The registration MATH is preserved verbatim from the legacy
pipeline/registration_func/3d_stitching.py (the leading-digit filename also made
it unimportable). Only the driver was rewritten to read config + manifest.

Folded-in improvements: deterministic RANSAC seed (1); consensus thresholds
surfaced as documented config (4); worker failures surfaced (3); explicit 8-bit
(7); configurable channel (9); run_manifest written (5). Auto-`pip install` calls
and websocket progress glue were removed.
"""
from __future__ import annotations

import os, sys, copy, json, time, pickle, random, string, shutil, platform, warnings
from collections import Counter, namedtuple
from datetime import datetime, timezone
from multiprocessing import Process

import psutil
import numpy as np
from ._model_input import pack_pair
from .. import _compat  # noqa: F401  -- numpy alias shim for legacy libs
import pandas as pd
import cv2
cv2.setNumThreads(1)  # parallelism is at the process level (n_cores workers); an
                      # uncapped per-process OpenCV thread pool oversubscribes the box
import imreg_dft
import astroalign as aa
from scipy import ndimage
from PIL import Image
from skimage import io
from skimage.registration import phase_cross_correlation
from image_registration import chi2_shift
from image_registration.fft_tools import shift

# Optional backend (thunder-registration); absent -> that method is skipped.
try:
    from registration import CrossCorr
except Exception:
    CrossCorr = None

warnings.filterwarnings("ignore")

from ..config import CollageConfig
from ..errors import CollageError, MetadataError, MissingInputError, ConsensusError, ReconstructionError
from ..ingest import manifest as manifest_mod

# --- module-level parameters (set per-run in run(); defaults keep importable) -
compr_fac = 10
do_8bit = True
do_99_push_condition = False
do_ai_cons = True
export_consen_ima = True
do_overlapping_QC = False
do_progress = False
path_to_model = None
script_dir = os.path.dirname(os.path.realpath(__file__))

# Phase-3 inference pool: when the cpu_pool backend is active, run() assigns the
# live CPUPoolService here so run_process_images_script (called inside forked
# per-pair workers) submits jobs to it instead of spawning a fresh
# model-loading subprocess. None => legacy subprocess_per_pair path. Must be set
# before any per-pair fork so workers inherit the populated global + the queue.
_INFERENCE_SERVICE = None
_SCORER_NAME = "kimianet"

# Consensus parameters (item 4): previously hard-coded magic numbers.
_CONSENSUS_CLUSTER_PX = 10     # methods whose translations agree within this px form a cluster
_ANGLE_THRESHOLD_DEG = 10      # reject imreg_dft rotation estimates beyond this many degrees
_PRIORITY_WEIGHT = 2           # extra vote weight for the imreg_dft / cv2 methods
_MIN_OVERLAP_AREA_FRAC = 0.00005   # min fractional tissue-overlap area to attempt a pair


import copy

def range_x1_q(x, q):
    x = np.asfarray(x)
    tmp_median = np.median(x)
    tmp_q_high = np.percentile(x[(x > 0) & (x != tmp_median)], q)
    tmp_q_min = np.percentile(x[(x > 0) & (x != tmp_median)], 100 - q)
    x = (x - tmp_q_min) / (tmp_q_high - tmp_q_min)
    x[x > 1] = 1
    x[x < 0] = 0
    return x
def evaluate_overlap(im_pairs, export_consen_ima):

    from tensorflow.keras.models import load_model
    from tensorflow.keras.preprocessing.image import img_to_array, load_img
    print(path_to_model)
    model = load_model(path_to_model)

    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

    method2ia_red = dict()
    curr_best = 0
    final_method = None
    for im_p in im_pairs:
        path_ref_image = im_p[0]
        path_query_image = im_p[1]
        method_ = os.path.basename(path_ref_image).split('____')[3]
        try:
            ref_image = img_to_array(load_img(path_ref_image, color_mode='grayscale')) / 255.0
            ref_image = np.arcsinh(2 ** 16 * ref_image)
            ref_image = range_x1_q(ref_image, 99)
            ref_image = np.squeeze(ref_image)

            # query_image = np.array(Image.open(path_query_image).convert('L'))
            query_image = img_to_array(load_img(path_query_image, color_mode='grayscale')) / 255.0
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
                    tmp_query = query_image[tmp_r:tmp_r + 256, tmp_c:tmp_c + 256]
                    tmp_ref = ref_image[tmp_r:tmp_r + 256, tmp_c:tmp_c + 256]

                    # Apply mask and check foreground percentage
                    tmp_mask = (tmp_ref > 0)
                    #foreground_percentage = np.mean(tmp_mask)

                    #if foreground_percentage < 0.1:
                    #    continue

                    if np.mean(tmp_ref) == 0:
                        continue

                    #tmp_ref = tmp_ref * tmp_mask
                    #tmp_query = tmp_query * tmp_mask

                    # Combine images to create an RGB image (tmp_qc)
                    tmp_qc = pack_pair(tmp_ref, tmp_query, model)
                    tmp_score = model.predict(tmp_qc[None, ...], verbose=0)

                    tmp_scores.append(tmp_score[0, 0])

            tmp_score = float(np.mean(tmp_scores))
        except Exception as e:
            # print('Error doing AI evaluation')
            # print(e)
            method2ia_red[method_] = {'score': str(e), 'path_ref_image': path_ref_image,
                                      'path_query_image': path_query_image}
            continue
        method2ia_red[method_] = {'score': tmp_score, 'path_ref_image': path_ref_image,
                                  'path_query_image': path_query_image}
        if export_consen_ima == False:
            os.remove(path_ref_image)
            os.remove(path_query_image)
        if np.isnan(tmp_score) == False and tmp_score > curr_best:
            curr_best = tmp_score + 0
            final_method = method_[:]

        if type(final_method) != type(None):
            print('Best method', final_method, 'Score:', curr_best)
        else:
            print('Not best method found with AI')


    return method2ia_red, final_method

"""
    #print(f'### path ref image: {path_ref_image} ###')
    #print(f'### path query image: {path_query_image} ###')
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

    from tensorflow.keras.models import load_model
    from tensorflow.keras.preprocessing.image import img_to_array, load_img
    '''
    try:
        from tensorflow.keras.models import load_model
        from tensorflow.keras.preprocessing.image import img_to_array, load_img
    except:
        os.system('pip3 install tensorflow')
        os.system('pip3 install tensorrt')
        from tensorflow.keras.models import load_model
        from tensorflow.keras.preprocessing.image import img_to_array, load_img
    '''


    model = load_model(path_to_model)


    ref_image = img_to_array(load_img(path_ref_image, color_mode='grayscale')) / 255.0
    ref_image = np.arcsinh(2 ** 16 * ref_image)
    ref_image = range_x1_q(ref_image, 99)
    ref_image = np.squeeze(ref_image)

    # query_image = np.array(Image.open(path_query_image).convert('L'))
    query_image = img_to_array(load_img(path_query_image, color_mode='grayscale')) / 255.0
    query_image = np.arcsinh(2 ** 16 * query_image)
    query_image = range_x1_q(query_image, 99)
    query_image = np.squeeze(query_image)

    # Padding if necessary
    if ref_image.shape[0] % 256 > 0 or ref_image.shape[1] % 256 > 0:
        ref_image = np.pad(ref_image, ((0, 256 - ref_image.shape[0] % 256), (0, 256 - ref_image.shape[1] % 256)),
                           'constant')
        query_image = np.pad(query_image,
                             ((0, 256 - query_image.shape[0] % 256), (0, 256 - query_image.shape[1] % 256)), 'constant')

    tmp_scores = []
    # Loop through the image in 256x256 tiles
    for tmp_r in range(0, ref_image.shape[0], 256):
        for tmp_c in range(0, ref_image.shape[1], 256):
            tmp_query = query_image[tmp_r:tmp_r + 256, tmp_c:tmp_c + 256]
            tmp_ref = ref_image[tmp_r:tmp_r + 256, tmp_c:tmp_c + 256]

            # Apply mask and check foreground percentage
            tmp_mask = (tmp_ref > 0)
            foreground_percentage = np.mean(tmp_mask)

            if foreground_percentage < 0.1:
                continue

            if np.mean(tmp_ref) == 0:
                continue

            tmp_ref = tmp_ref * tmp_mask
            tmp_query = tmp_query * tmp_mask

            # Combine images to create an RGB image (tmp_qc)
            tmp_qc = np.stack([tmp_ref, tmp_query, np.zeros_like(tmp_ref)], axis=-1)
            tmp_score = model.predict(tmp_qc.reshape(1, 256, 256, 3),verbose = 0)

            tmp_scores.append(tmp_score[0, 0])

    mean_score = np.mean(tmp_scores)
    return mean_score
"""
def get_tile2coord(input_metadata, df_metadata):
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

def do_99_push(im_dict):
    def range_x1_q(x, q):
        # Calculate the high and low quantiles of non-zero values for each slice
        tmp_q_high = np.quantile(x[x > 0], q, axis=0, overwrite_input=False, interpolation='linear', keepdims=True)
        tmp_q_low = np.quantile(x[x > 0], 1 - q, axis=0, overwrite_input=False, interpolation='linear',
                                keepdims=True)

        # Scale each slice to the range [0, 1]
        x_norm = (x - tmp_q_low) / (tmp_q_high - tmp_q_low)
        x_norm[x_norm > 1] = 1
        x_norm[x_norm < 0] = 0

        return x_norm
    q = 0.99
    from sklearn.preprocessing import MinMaxScaler

    images_dict = copy.copy(im_dict)
    # Convert PIL images to numpy arrays
    image_arrays = [np.array(img) for img in images_dict.values()]

    # Concatenate the image arrays into a 3D hypermatrix
    x = np.stack(image_arrays, axis=-1)

    # Normalize the values in the input array between 0 and 1
    scaler = MinMaxScaler(feature_range=(0, 1))
    x_norm = scaler.fit_transform(x.reshape((-1, x.shape[-1])))
    x_norm = x_norm.reshape(x.shape)

    # Apply quantile normalization using range_x1_q
    x_processed = range_x1_q(x_norm, q)

    # Convert the processed hypermatrix back to a list of images
    processed_images = []
    for i in range(x_processed.shape[-1]):
        img = Image.fromarray(np.uint8(x_processed[..., i] * 255))
        processed_images.append(img)

    # Create a dictionary with the same keys as the input dictionary
    # and the values being the processed images
    im_dict = {key: processed_images[i] for i, key in enumerate(images_dict.keys())}
    return im_dict



def extend_overlap(slide, scene, pair, tile2coor, im2neighbour):
    p01 = int(float(pair.split('_')[1]))

    p02_2_pair = {int(float(i.split('_')[3])):i for i in tiles2posis if int(float(i.split('_')[1])) == p01}
    p02s2coorp01 = {}
    p02s2coorp02 = {}
    p02s2area = {}
    im01_name = slide_round_scene_file[slide][scene][r01][p01]
    im1 = io.imread(im01_name)
    for p02 in p02_2_pair:
        pair_ = p02_2_pair[p02]
        area = tiles2posis[pair_]
        p02s2area[p02] = (area[1] - area[0]) * (area[3] - area[2])

        coor_im1 = tiles2extremes['_'.join(pair_.split('_')[0:2])]
        coor_im2 = tiles2extremes['_'.join(pair_.split('_')[2::])]  # [193, 378, 2674, 2859]

        coor_im1_int = [area[0] - coor_im1[0], area[1] - coor_im1[0], area[2] - coor_im1[2], area[3] - coor_im1[2]]
        coor_im2_int = [area[0] - coor_im2[0], area[1] - coor_im2[0], area[2] - coor_im2[2], area[3] - coor_im2[2]]

        coor_im1_int = list(np.array(coor_im1_int) * compr_fac)
        coor_im2_int = list(np.array(coor_im2_int) * compr_fac)

        p02s2coorp01[p02] = coor_im1_int
        p02s2coorp02[p02] = coor_im2_int
    bestp02 = [i for i in p02s2area if p02s2area[i] == max(p02s2area.values())][0]

    im02_name = slide_round_scene_file[slide][scene][r02][bestp02]
    all_neig = im2neighbour[os.path.basename(im02_name)]
    coor_cen = tile2coor[os.path.basename(im02_name)]
    best_pair = '_'.join(pair.split('_')[0:3]) + '_' + str(bestp02)
    for neig in all_neig:
        if len(all_neig[neig]) == 0:
            continue
        M_ = [int(i.split('M')[-1]) for i in all_neig[neig].split('_') if i.startswith('S') and 'M' in i and i.replace('S', '').replace('M','').isdigit() == True][0]
        #if M_ != 17:
        #    continue
        if M_ not in p02s2area or p02s2area[M_] * compr_fac ** 2 < _MIN_OVERLAP_AREA_FRAC * np.shape(im1)[0] * np.shape(im1)[1]:
            pass
        else:
            continue
        M_f = slide_round_scene_file[slide][scene][r02][M_]
        coor_sec = tile2coor[os.path.basename(M_f)]
        Acoor_y = (coor_cen[0] - coor_sec[0]) / compr_fac
        Acoor_x = (coor_cen[1] - coor_sec[1]) / compr_fac

        pair_ = '_'.join(pair.split('_')[0:3]) + '_' + str(M_)
        new_posi = tiles2posis[best_pair]
        new_posi = [new_posi[0] - Acoor_x, new_posi[1] - Acoor_x, new_posi[2] - Acoor_y, new_posi[3] - Acoor_y]
        tiles2posis[pair_] = new_posi[:]
    return tiles2posis

import random, string
def generate_random_folder_name(length=8):
    characters = string.ascii_letters + string.digits
    random_folder_name = ''.join(random.choices(characters, k=length))
    return random_folder_name

import shutil
def do_ai_overlapp(im1, im2):
    method2transl = {}
    im1_ori = copy.copy(im1)
    im2_ori = copy.copy(im2)

    do_arcsinh = True
    if do_arcsinh:
        im1 = np.arcsinh(im1)
        im2 = np.arcsinh(im2)

    if im1.dtype == np.uint16:
        im1 = im1 / (2 ** 16 - 1) * (2 ** 8 - 1)
        im1 = im1.astype(np.uint8)
    if im2.dtype == np.uint16:
        im2 = im2 / (2 ** 16 - 1) * (2 ** 8 - 1)
        im2 = im2.astype(np.uint8)

    if im1.dtype == np.float16:
        # Transform to float32
        im1 = im1.astype(np.float32)
    if im2.dtype == np.float16:
        # Transform to float32
        im2 = im2.astype(np.float32)

    try:
        out_reg = imreg_dft.imreg.similarity(im1, im2)
        method2transl['imreg_dft'] = copy.copy(out_reg)
        del method2transl['imreg_dft']['timg']

        out_reg_ = imreg_dft.imreg.translation(im1, im2)
        method2transl['imreg_dft_no_angle'] = copy.copy(out_reg_)
    except Exception as e:
        pass
        #print('pair:', pair, 'Error imreg_dft', e)


    # shift, error, diffphase = phase_cross_correlation(im1, im2,upsample_factor=100) #Fourier, DFT upsampling method
    # out_reg_skimage = imreg_dft.imreg.similarity(corrected_image2, im2)
    try:
        xoff, yoff, exoff, eyoff = chi2_shift(im1, im2)  # Fourier, DFT upsampling method
        corrected_image2 = shift.shiftnd(im2, (-yoff, -xoff))
        out_reg_chi2 = imreg_dft.imreg.similarity(corrected_image2, im2)
        method2transl['chi2_no_angle'] = copy.copy(out_reg_chi2)
    except Exception as e:
        pass
        #print('pair:', pair, 'Error chi2_shift', e)

    try:
        shift_, error, diffphase = phase_cross_correlation(im1, im2)
        t_s = np.asarray(shift_)
        method2transl['phase_cross_correlation_no_angle'] = {'tvec': (float(t_s[0]), float(t_s[1]))}
    except Exception as e:
        pass
        #print('pair:', pair, 'Error phase_cross_correlation', e)

    ####
    done_aa = False
    try:
        registered_image, footprint = aa.register(im2, im1)
        out_reg_aa = imreg_dft.imreg.similarity(registered_image, im2)
        method2transl['aa'] = copy.copy(out_reg_aa)
        done_aa = True
    except Exception as e:
        pass
        #print('pair:', pair,'Error aa', e)
    ####

    # https://stackoverflow.com/questions/37984709/how-to-use-surf-in-python

    try:
        corrected_image_cv = cv_registration(im1, im2)
        out_reg_cv = imreg_dft.imreg.similarity(im2, corrected_image_cv)
        method2transl['cv2'] = copy.copy(out_reg_cv)
    except Exception as e:
        pass
        #print('pair:', pair,'Error cv2', e)

    try:
        register = CrossCorr()
        model = register.fit(im1, reference=im2)
        method2transl['thunder_no_angle'] = {'tvec': np.asarray(model.toarray().tolist()[0])}
    except Exception as e:
        pass


    im_pairs = list()

    coor_im1_int = [0, im1.shape[0], 0 ,im1.shape[1]]
    coor_im2_int = [0, im2.shape[0], 0 ,im2.shape[1]]

    random_folder = generate_random_folder_name(8)
    for m in method2transl:
        out_reg___ = method2transl[m]

        try:
            im2_ori_reg, d_, is_custom = get_recons_im(im2, out_reg___, coor_im1_int, coor_im2_int, im2)
        except Exception as e:
            print('Error in get_recons_im XXXX', e)
            continue

        d1 = np.min([im1_ori.shape[0], im2_ori_reg.shape[0]])
        d2 = np.min([im1_ori.shape[1], im2_ori_reg.shape[1]])

        if min([d1, d2]) == 0:
            continue

        im2_cons = im2_ori_reg[0:d1, 0:d2].astype(im1_ori.dtype)
        im1_cons = im1[0:d1, 0:d2].astype(im1_ori.dtype)

        name_ = os.path.join(output_folder, 'test_for_consen', random_folder,'____' + 'test' + '____'  + 'test' + '____' + m)

        # Get the directory name from the file path
        directory = os.path.dirname(name_)
        # Check if the directory exists, and create it if it does not
        if not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        im = Image.fromarray(im1_cons)
        im.save(name_ + '____im1.tiff')

        im = Image.fromarray(im2_cons)
        im.save(name_ + '____im2.tiff')

        im_pairs.append((name_ + '____im1.tiff', name_ + '____im2.tiff'))

    method2ia_red, final_method = evaluate_overlap(im_pairs, export_consen_ima)
    shutil.rmtree(os.path.join(output_folder, 'test_for_consen', random_folder))
    return method2transl[final_method], final_method


def run_process_images_script(path_to_model, im_pairs, export_consen_ima):
    # Fast path: if a persistent inference pool is running (cpu_pool backend), send
    # the job to it -- the model is already loaded in the pool workers, so no
    # per-pair reload. Falls through to the legacy per-pair subprocess otherwise.
    if _INFERENCE_SERVICE is not None:
        data = _INFERENCE_SERVICE.submit(im_pairs, export_consen_ima).result()
        # A worker-side scoring failure (e.g. GPU OOM) lands here as
        # data['error'] with method2ia_red={}/final_method=None -- if not
        # raised, the caller's `except Exception` around this call (which
        # prints a "Soft error" and also sets final_method=None) never fires,
        # so the failure is silently indistinguishable from "no consensus
        # transform was good enough" and degrades to an empty pseudotile with
        # no error at all. Raise so it goes through that existing handling.
        if data.get('error'):
            raise RuntimeError(f"inference worker failed to score job: {data['error']}")
        return data.get('method2ia_red'), data.get('final_method')

    import subprocess
    import random
    import string

    hex_chars = string.hexdigits.lower()
    random_hex = ''.join(random.choice(hex_chars) for _ in range(16))

    output_path = os.path.join(output_folder, 'test_for_consen', random_hex + '.pkl')

    # Prepare the command as a list
    command = [
        sys.executable, os.path.join(script_dir, 'evaluate_overlap_function.py'),
        '--model', path_to_model,
        '--scorer', _SCORER_NAME,
        '--image_pairs'
    ]
    # Add all image pairs to the command list
    for pair in im_pairs:
        command.append(pair[0])
        command.append(pair[1])

    # Add the remaining arguments
    command += [
        '--export_consen_ima', str(export_consen_ima),
        '--output_path', output_path
    ]


    # Execute the command and wait for it to complete
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        #print('Output:', result.stdout)
        #print('Error:', result.stderr)
    except subprocess.CalledProcessError as e:
        # Do NOT swallow this: a failed consensus subprocess yields empty
        # pseudotiles two steps downstream. Surface the real error.
        raise RuntimeError(
            "AlignQC consensus subprocess failed (exit %s). stderr:\n%s"
            % (e.returncode, e.stderr)
        )

    if not os.path.exists(output_path):
        raise RuntimeError(
            "AlignQC consensus subprocess produced no output at %s "
            "(it likely crashed before writing results)." % output_path
        )

    # Load the pickle file
    with open(output_path, 'rb') as f:
        data = pickle.load(f)

    # Extract method2ia_red and final_method
    method2ia_red = data.get('method2ia_red')
    final_method = data.get('final_method')

    os.remove(output_path)

    return method2ia_red, final_method
def overlapping_func(slide, scene, pair, r01, r02):

    p01 = int(float(pair.split('_')[1]))
    p02 = int(float(pair.split('_')[3]))

    im01_name = slide_round_scene_file[slide][scene][r01][p01]
    im02_name = slide_round_scene_file[slide][scene][r02][p02]

    im1 = io.imread(im01_name)
    im2 = io.imread(im02_name)

    #do_99_push_overlap_fun = True
    if do_99_push_condition == True:
        max_intensity_ref = slide_scene_round_2max_intensity[slide + '__' + scene + '__' + r01]
        max_intensity_que = slide_scene_round_2max_intensity[slide + '__' + scene + '__' + r02]

        #if 'MEL05' not in im02_name or 'ITALY2' not in im02_name:
        #    return


        # Perform dynamic intensity transformation
        im1 = np.clip(im1.astype(np.float64) * np.iinfo(im1.dtype).max / max_intensity_ref / 255, 0, 255).astype(
            np.uint8)
        im2 = np.clip(im2.astype(np.float64) * np.iinfo(im2.dtype).max / max_intensity_que / 255, 0, 255).astype(
            np.uint8)

    if im1.dtype != np.dtype('uint8') and do_8bit == True:
        im1 = im1 / (2 ** 16 - 1) * (2 ** 8 - 1)
        im1 = im1.astype(np.uint8)
    if im2.dtype != np.dtype('uint8') and do_8bit == True:
        im2 = im2 / (2 ** 16 - 1) * (2 ** 8 - 1)
        im2 = im2.astype(np.uint8)



    area = tiles2posis[pair]

    if (area[1] - area[0]) * (area[3] - area[2]) * compr_fac ** 2 < _MIN_OVERLAP_AREA_FRAC * np.shape(im1)[0] * np.shape(im1)[1]:
        with open(os.path.join(output_folder, f_, 'QC', pair + '.json'), 'w', encoding='utf-8') as f:
            json.dump(dict(), f, ensure_ascii=False, indent=4)
        with open(os.path.join(output_folder, f_, 'QC', pair + '_done.json'), 'w', encoding='utf-8') as f:
            json.dump(dict(), f, ensure_ascii=False, indent=4)
        return
    try:
        coor_im1 = tiles2extremes['_'.join(pair.split('_')[0:2])]
        coor_im2 = tiles2extremes['_'.join(pair.split('_')[2::])]  # [193, 378, 2674, 2859]
    except Exception as e:
        print('Controled error', e)
        print(pair)
        with open(os.path.join(output_folder, f_, 'QC', pair + '.json'), 'w', encoding='utf-8') as f:
            json.dump(dict(), f, ensure_ascii=False, indent=4)
        with open(os.path.join(output_folder, f_, 'QC', pair + '_done.json'), 'w', encoding='utf-8') as f:
            json.dump(dict(), f, ensure_ascii=False, indent=4)
        return

    coor_im1_int = [area[0] - coor_im1[0], area[1] - coor_im1[0], area[2] - coor_im1[2], area[3] - coor_im1[2]]
    coor_im2_int = [area[0] - coor_im2[0], area[1] - coor_im2[0], area[2] - coor_im2[2], area[3] - coor_im2[2]]

    coor_im1_int = list(np.array(coor_im1_int) * compr_fac)
    coor_im2_int = list(np.array(coor_im2_int) * compr_fac)

    if min(coor_im1_int) < 0 or min(coor_im2_int) < 0:
        with open(os.path.join(output_folder, f_, 'QC', pair + '.json'), 'w', encoding='utf-8') as f:
            json.dump(dict(), f, ensure_ascii=False, indent=4)
        with open(os.path.join(output_folder, f_, 'QC', pair + '_done.json'), 'w', encoding='utf-8') as f:
            json.dump(dict(), f, ensure_ascii=False, indent=4)
        return

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

    im1_ori = im1.copy()
    im2_ori = im2.copy()

    coor_im1_int = [int(x) for x in coor_im1_int]
    coor_im2_int = [int(x) for x in coor_im2_int]

    im1[:coor_im1_int[0], :] = 0
    im1[coor_im1_int[1]:, :] = 0
    im1[:, :coor_im1_int[2]] = 0
    im1[:, coor_im1_int[3]:] = 0

    im2[:coor_im2_int[0], :] = 0
    im2[coor_im2_int[1]:, :] = 0
    im2[:, :coor_im2_int[2]] = 0
    im2[:, coor_im2_int[3]:] = 0

    im1_ori_z = im1.copy()
    im2_ori_z = im2.copy()
    '''
    from PIL import Image
    im__ = Image.fromarray(im1)
    im__.save("im1.tiff")
    '''

    # pip install pytest
    # pip install image_registration

    clusters_registr = dict()
    method2transl = {}

    do_arcsinh = True
    if do_arcsinh:
        im1 = np.arcsinh(im1).astype(np.float32)
        im2 = np.arcsinh(im2).astype(np.float32)

    '''
    import ants
    im1_ants = ants.from_numpy(im1)
    im2_ants = ants.from_numpy(im2)
    reg12 = ants.registration(im1_ants, im2_ants,)
    mywarpedimage = ants.apply_transforms(fixed=im1_ants, moving=im2_ants,
                                          transformlist=reg12['fwdtransforms'])
    out_reg_ants = imreg_dft.imreg.similarity(im2, mywarpedimage.numpy())
    '''

    try:
        '''
        try:
            import ants
            im1_ants = ants.from_numpy(im1)
            im2_ants = ants.from_numpy(im2)
            reg12 = ants.registration(im1_ants, im2_ants, )
            mywarpedimage = ants.apply_transforms(fixed=im1_ants, moving=im2_ants,
                                                  transformlist=reg12['fwdtransforms'])
            out_reg_ants = imreg_dft.imreg.similarity(im2, mywarpedimage.numpy())
            method2transl['out_reg_ants'] = copy.copy(out_reg_ants)
        except:
            pass
        '''

        try:
            out_reg = imreg_dft.imreg.similarity(im1, im2)
            method2transl['imreg_dft'] = copy.copy(out_reg)
            del method2transl['imreg_dft']['timg']
            if abs(method2transl['imreg_dft']['angle']) > _ANGLE_THRESHOLD_DEG:
                del method2transl['imreg_dft']


            out_reg_ = imreg_dft.imreg.translation(im1, im2)
            method2transl['imreg_dft_no_angle'] = copy.copy(out_reg_)
            method2transl['imreg_dft_no_angle']['scale'] = 1

        except Exception as e:
            pass
            #print('pair:', pair, 'Error imreg_dft', e)


        # shift, error, diffphase = phase_cross_correlation(im1, im2,upsample_factor=100) #Fourier, DFT upsampling method
        # out_reg_skimage = imreg_dft.imreg.similarity(corrected_image2, im2)
        try:
            xoff, yoff, exoff, eyoff = chi2_shift(im1, im2)  # Fourier, DFT upsampling method
            corrected_image2 = shift.shiftnd(im2, (-yoff, -xoff))
            out_reg_chi2 = imreg_dft.imreg.similarity(corrected_image2, im2)
            del out_reg_chi2['timg']
            method2transl['chi2_no_angle'] = copy.copy(out_reg_chi2)
        except Exception as e:
            pass
            #print('pair:', pair, 'Error chi2_shift', e)

        # from pystackreg import StackReg
        # sr = StackReg(StackReg.RIGID_BODY)
        # out_aff = sr.register_transform(im1, im2)
        # out_reg_StackReg = imreg_dft.imreg.similarity(out_aff, im2)
        try:
            shift_, error, diffphase = phase_cross_correlation(im1, im2)
            d_t = np.asarray(shift_)
            method2transl['phase_cross_correlation_no_angle'] = {'tvec': (float(d_t[0]), float(d_t[1])), 'scale' : 1, 'angle': 0}
        except Exception as e:
            pass
            #print('pair:', pair, 'Error phase_cross_correlation', e)

        ####
        done_aa = False
        try:
            registered_image, footprint = aa.register(im2, im1)
            out_reg_aa = imreg_dft.imreg.similarity(registered_image, im2)
            method2transl['aa'] = copy.copy(out_reg_aa)
            done_aa = True
        except Exception as e:
            pass
            #print('pair:', pair,'Error aa', e)
        ####

        # https://stackoverflow.com/questions/37984709/how-to-use-surf-in-python

        try:
            corrected_image_cv = cv_registration(im1, im2)
            out_reg_cv = imreg_dft.imreg.similarity(im2, corrected_image_cv)
            method2transl['cv2'] = copy.copy(out_reg_cv)
        except Exception as e:
            pass
            #print('pair:', pair,'Error cv2', e)

        try:
            register = CrossCorr()
            model = register.fit(im1, reference=im2)
            method2transl['thunder_no_angle'] = {'tvec': np.asarray(model.toarray().tolist()[0]), 'scale' : 1, 'angle': 0}
        except Exception as e:
            pass
            #print('pair:', pair,'Error thunder', e)


        # out_reg_chi2_ = imreg_dft.imreg.translation(corrected_image2, im2)
    except Exception as e:
        print('Error registration:', e, pair)
        with open(os.path.join(output_folder, f_, 'QC', pair + '_flagged.json'), 'w', encoding='utf-8') as f:
            json.dump({}, f, ensure_ascii=False, indent=4)

    im_pairs = list()
    if export_consen_ima == True or do_ai_cons == True:
        for m in method2transl:
            out_reg___ = method2transl[m]

            if np.max(im2_ori_z) == 0:
                continue

            try:
                im2_ori_reg, d_, is_custom = get_recons_im(im2_ori_z, out_reg___, coor_im1_int, coor_im2_int, im2_ori)
            except Exception as e:
                print('soft Error get_recons_im', str(e))
                continue

            d1 = np.min([im1_ori.shape[0], im2_ori_reg.shape[0]])
            d2 = np.min([im1_ori.shape[1], im2_ori_reg.shape[1]])

            if min([d1, d2]) == 0:
                continue

            im2_ori_reg[0:coor_im1_int[0], :] = 0
            im2_ori_reg[coor_im1_int[1]:, :] = 0
            im2_ori_reg[:, 0:coor_im1_int[2]] = 0
            im2_ori_reg[:, coor_im1_int[3]:] = 0

            im2_cons = im2_ori_reg[0:d1, 0:d2].astype(im1_ori.dtype)
            im1_cons = im1_ori_z[0:d1, 0:d2].astype(im1_ori.dtype)



            name_ = os.path.join(output_folder, 'test_for_consen', os.path.splitext(os.path.basename(im02_name))[0], os.path.splitext(os.path.basename(im01_name))[0] + '____' + os.path.splitext(os.path.basename(im02_name))[0] + '____' + pair + '____' + m)

            # Get the directory name from the file path
            directory = os.path.dirname(name_)
            # Check if the directory exists, and create it if it does not
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)

            im = Image.fromarray(im1_cons)
            im.save(name_ + '____im1.tiff')

            im = Image.fromarray(im2_cons)
            im.save(name_ + '____im2.tiff')

            im_pairs.append((name_ + '____im1.tiff', name_ + '____im2.tiff'))

    final_method = None
    if do_ai_cons == False:
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
            if d_s_min > _CONSENSUS_CLUSTER_PX:
                clusters_registr[m1] = [m1]
                continue
            if m1 in ['imreg_dft','cv2']:
                clusters_registr[c_min] += [m1]*_PRIORITY_WEIGHT
            else:
                clusters_registr[c_min] += [m1]

        priority_order = ['imreg_dft', 'cv2', 'aa', 'chi2_no_angle', 'phase_cross_correlation_no_angle',
                          'imreg_dft_no_angle', 'thunder_no_angle']
        l_clust_v = -1
        for c in clusters_registr:
            if len(clusters_registr[c]) > l_clust_v:
                l_clust_v = len(clusters_registr[c]) + 0

        for m in priority_order:
            for j in [c for c in clusters_registr if len(clusters_registr[c]) == l_clust_v]:
                if m in clusters_registr[j] and l_clust_v >= 3:
                    final_method = m[:]
                    break
            if type(final_method) != type(None):
                break
    else:

        #method2ia_red, final_method = evaluate_overlap(im_pairs, export_consen_ima)

        try:
            method2ia_red, final_method = run_process_images_script(path_to_model, im_pairs, export_consen_ima)
        except Exception as e:
            print('Soft error getting IA overlap evaluation (run_process_images_script)', str(e))
            final_method = None

    if export_consen_ima == True and do_ai_cons == True and type(final_method) != type(None):

        # Get the current date and time
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        # Create a unique filename by appending the current time
        filename = f'method2ia_red_{current_time}.json'

        # Path to save the file
        out_dir_t = os.path.join(output_folder, 'test_for_consen', os.path.splitext(os.path.basename(im02_name))[0])
        file_path = os.path.join(out_dir_t, filename)
        if not os.path.exists(out_dir_t):
            os.makedirs(out_dir_t)

        # Save the results in the JSON file
        with open(file_path, 'w') as json_file:
            json.dump(method2ia_red, json_file, indent=4)

        #out_dir_t = os.path.join(output_folder, 'test_for_consen', os.path.basename(im02_name).split('.')[0])
        #with open(os.path.join(out_dir_t, 'method2ia_red.json'), 'w') as json_file:
        #    json.dump(method2ia_red, json_file, indent=4)
    '''
    err_x = abs(out_reg['tvec'][0]-out_reg_['tvec'][0])
    err_y = abs(out_reg['tvec'][1]-out_reg_['tvec'][1])
    if err_x > 20 or err_y > 20:
        t_vec_d = {'similarity':list(out_reg['tvec']),'translation':list(out_reg_['tvec'])}
        with open(os.path.join(output_folder,f_, 'QC', pair + '_flagged.json'), 'w', encoding='utf-8') as f:
            json.dump(t_vec_d, f, ensure_ascii=False, indent=4)
    '''
    if type(final_method) == type(None):
        try:
            t_vec_d = {'similarity': list(out_reg['tvec']), 'translation': list(out_reg_['tvec']),
                       'method2transl': str(method2transl)}
            with open(os.path.join(output_folder, f_, 'QC', pair + '_flagged.json'), 'w', encoding='utf-8') as f:
                json.dump(t_vec_d, f, ensure_ascii=False, indent=4)
        except:
            t_vec_d = {'similarity': [], 'translation': [],
                       'method2transl': str(method2transl)}
            with open(os.path.join(output_folder, f_, 'QC', pair + '_flagged.json'), 'w', encoding='utf-8') as f:
                json.dump(t_vec_d, f, ensure_ascii=False, indent=4)

        with open(os.path.join(output_folder, f_, 'QC', pair + '.json'), 'w', encoding='utf-8') as f:
            json.dump(dict(), f, ensure_ascii=False, indent=4)
        with open(os.path.join(output_folder, f_, 'QC', pair + '_done.json'), 'w', encoding='utf-8') as f:
            json.dump(dict(), f, ensure_ascii=False, indent=4)
        return
    else:
        out_reg = copy.copy(method2transl[final_method])








    '''
    #option 2 for reconstruction
    im2_ori_reg = imreg_dft.imreg.transform_img(im2_ori, scale=out_reg['scale'], angle=out_reg['angle'],
                                          tvec=out_reg['tvec'],mode = 'wrap')
    '''

    # option 3 for reconstruction
    # im2_ori_reg = imreg_dft.imreg.transform_img_dict(im2_ori,out_reg,mode = 'wrap')

    '''
    im2_ori_reg = imreg_dft.imreg.transform_img(im2, scale=out_reg['scale'], angle=out_reg['angle'],
                                          tvec=out_reg['tvec'],mode = 'wrap')

    im2_ori_reg = im2_ori_reg.astype(np.uint8)
    '''

    try:
        im2_ori_reg, d_, is_custom = get_recons_im(im2, out_reg, coor_im1_int, coor_im2_int, im2_ori)
    except Exception as e:
        print('Error in get_recons_im', e)
        print(slide, scene, pair, r02)
        with open(os.path.join(output_folder, f_, 'QC', pair + '.json'), 'w', encoding='utf-8') as f:
            json.dump(dict(), f, ensure_ascii=False, indent=4)
        with open(os.path.join(output_folder, f_, 'QC', pair + '_done.json'), 'w', encoding='utf-8') as f:
            json.dump(dict(), f, ensure_ascii=False, indent=4)
        return

    # im2_ori_reg_chi2, d_, is_custom = get_recons_im(im2, out_reg_chi2)

    output_dict = dict()
    # output_dict['tvec'] = list(out_reg['tvec'] + d_)
    if 'timg' in out_reg:
        del out_reg['timg']
    try:
        output_dict['tvec'] = list((float(out_reg['tvec'][0]), float(out_reg['tvec'][1])))
    except:
        output_dict['tvec'] = list(out_reg['tvec'])

    output_dict['scale'] = float(out_reg['scale'])
    output_dict['angle'] = float(out_reg['angle'])
    output_dict['method2transl'] = str(method2transl)
    output_dict['coor_im1_intersection'] = [float(i) for i in coor_im1_int]
    output_dict['coor_im2_intersection'] = [float(i) for i in coor_im2_int]

    d1 = np.min([im1_ori.shape[0], im2_ori_reg.shape[0]])
    d2 = np.min([im1_ori.shape[1], im2_ori_reg.shape[1]])

    im2_ori_reg = im2_ori_reg.astype(im1_ori.dtype)

    rgb_comb = np.dstack((cv2.convertScaleAbs(im1_ori[0:d1, 0:d2], alpha=(255.0 / 255.0)),
                          cv2.convertScaleAbs(im2_ori_reg[0:d1, 0:d2], alpha=(255.0 / 255.0)),
                          cv2.convertScaleAbs(im2_ori_reg[0:d1, 0:d2]*0, alpha=(255.0 / 255.0)) ))

    if '_codex_' in im01_name:
        rgb_comb = rgb_comb * 5


    '''
    rgb_comb = np.dstack((im1_ori[0:d1, 0:d2],
                          im2_ori_reg[0:d1, 0:d2].astype(im1_ori.dtype),
                          im2_ori_reg[0:d1, 0:d2].astype(im1_ori.dtype)))
    '''
    if str(rgb_comb.dtype) == 'uint16':
        directory = os.path.join(output_folder, f_, 'QC', '16b')
        if not os.path.exists(directory):
            os.makedirs(directory)
        cv2.imwrite(os.path.join(directory, pair + '.png'), rgb_comb)
        rgb_comb = rgb_comb / (2 ** 16 - 1) * (2 ** 8 - 1)
        rgb_comb = rgb_comb.astype('uint8')

    try:
        im = Image.fromarray(rgb_comb)
        if is_custom == True:
            im.save(os.path.join(output_folder, f_, 'QC', pair + '_custom.png'))
        else:
            im.save(os.path.join(output_folder, f_, 'QC', pair + '.png'))
    except Exception as e:
        print('Error last step generating overlapp', print(e))
        print(rgb_comb.shape)
        print(pair)

    try:
        with open(os.path.join(output_folder, f_, 'QC', pair + '.json'), 'w', encoding='utf-8') as f:
            json.dump(output_dict, f, ensure_ascii=False, indent=4)
        with open(os.path.join(output_folder, f_, 'QC', pair + '_done.json'), 'w', encoding='utf-8') as f:
            json.dump(dict(), f, ensure_ascii=False, indent=4)
    except:
        print('ERRORRRRRR exporting output_dict!!!!')
        print(output_dict)

    #print(f_, pair, 'Consensus results:', final_method, l_clust_v, clusters_registr)


def get_overlapping_tiles(f_, pkl_file):
    from collections import Counter
    r01 = f_.split('______')[0]
    r02 = f_.split('______')[1].replace('.pkl', '')
    #tileFolder2metafile
    this_meta01 = [os.path.join(tileFolder2metafile[j], j) for j in tileFolder2metafile if r01 == os.path.basename(tileFolder2metafile[j])][0]
    this_meta02 = [os.path.join(tileFolder2metafile[j], j) for j in tileFolder2metafile if r02 == os.path.basename(tileFolder2metafile[j])][0]

    tile_templ_01 = generate_templates(this_meta01)
    tile_templ_02 = generate_templates(this_meta02)

    n1 = all_recon['.csv'.join(os.path.basename(this_meta01).split('.csv')[0::-1])]
    n2 = all_recon['.csv'.join(os.path.basename(this_meta02).split('.csv')[0::-1])]

    im1_temp = io.imread(n1)
    im2_temp = io.imread(n2)

    im1x, im1y = np.shape(im1_temp)
    im2x, im2y = np.shape(im2_temp)

    imx = max([im1x, im2x])
    imy = max([im1y, im2y])

    tile_templ_01 = Image.fromarray(add_zero_padding(np.array(tile_templ_01), imx, imy))
    tile_templ_02 = Image.fromarray(add_zero_padding(np.array(tile_templ_02), imx, imy))

    file = open(pkl_file, 'rb')
    reg_output_dict = pickle.load(file)
    file.close()

    tile_templ_01_np = np.array(tile_templ_01)
    tile_templ_02_array = np.array(tile_templ_02)

    all_values = list(np.unique(tile_templ_01_np))
    tile2coor = dict()

    for j01x, j01 in enumerate(all_values):
        #print('Tiles in new coordinates 1/2', j01x, len(all_values))
        #if j01 == 0:
            #continue
        if j01 + 1 not in tile_templ_01_np:
            continue
        #if j01 != 57:
        #    continue

        w_02 = np.where(tile_templ_01_np == j01 + 1)
        extre_pos = [min(w_02[0]), max(w_02[0]), min(w_02[1]), max(w_02[1])]
        tile2coor['01_' + str(int(j01))] = extre_pos

    all_values = list(np.unique(tile_templ_02_array))
    t_ = np.zeros(np.shape(tile_templ_02_array))
    for j02x, j02 in enumerate(all_values): # PARALELIZAR
        #if j02 != 71:
        #    continue
        #'01_3_02_4'
        ###print('Finding overlapping areas in the tiles', j02x, len(all_values))
        #if j02 == 0:
            #continue
        if j02 + 1 not in tile_templ_02_array:
            continue
        w_02 = np.where(tile_templ_02_array == j02 + 1)
        extre_pos_ori = [min(w_02[0]), max(w_02[0]), min(w_02[1]), max(w_02[1])]
        t_[extre_pos_ori[0],extre_pos_ori[2]] = 1000; t_[extre_pos_ori[0],extre_pos_ori[3]] = 1000; t_[extre_pos_ori[1],extre_pos_ori[2]] = 1000; t_[extre_pos_ori[1],extre_pos_ori[3]] = 1000
        t_reg = imreg_dft.imreg.transform_img(t_, scale = reg_output_dict['scale'], angle = reg_output_dict['angle'], tvec = reg_output_dict['tvec'], bgval=0)
        w_02 = np.where(t_reg > 1)
        try:
            extre_pos = [min(w_02[0]), max(w_02[0]), min(w_02[1]), max(w_02[1])]
        except:
            print('Error getting extreme possition', f_, j02)
        ###print(j02,extre_pos_ori,extre_pos)
        t_[:] = 0
        tile2coor['02_' + str(int(j02))] = extre_pos

    with open(os.path.join(os.path.dirname(pkl_file), 'overlapping_template_'+ r01 + '______' + r02 + '.pkl'), 'wb') as f:
        pickle.dump(tile2coor, f)
    #return tiles2posis



def generate_templates(input_metadata):
    tile2coor = dict()
    pictures_folder = os.path.splitext(input_metadata)[0]
    #naive_lump = Image.new('RGB', (3000, 3000))
    try:
        pd_metadata = pd.read_csv(input_metadata, sep=',')
        pd_metadata['StageYPosition']
    except:
        pd_metadata = pd.read_csv(input_metadata, sep=';')
        pd_metadata['StageYPosition']

    # Creating DAPI neighbour
    neig_dict = dict()


    if ',' in str(pd_metadata['ImagePixelSize'][0]):
        scalex, scaley = map(float, pd_metadata['ImagePixelSize'][0].split(','))
    else:
        scalex = float(pd_metadata['ImagePixelSize'][0]) + 0
        scaley = float(pd_metadata['ImagePixelSize'][0]) + 0

    scale = scalex/10

    # if set(pd_metadata['ImagePixelSize']) != set(['6.5,6.5']):
    #     print('Error scaling the pixel, define scaling in terms of the new values')
    #     error_to_be_solved
    # scale = 6.5/10

    pd_metadata['StageXPosition'] = pd_metadata['StageXPosition'] / scale
    pd_metadata['StageYPosition'] = pd_metadata['StageYPosition'] / scale

    all_y_lev = sorted(list(set(pd_metadata['StageYPosition'])))
    all_x_lev = sorted(list(set(pd_metadata['StageXPosition'])))

    sX = int(pd_metadata['Frame'][0].split(',')[2])
    sY = int(pd_metadata['Frame'][0].split(',')[3])

    shift_x = min(all_x_lev) - sX
    shift_y = min(all_y_lev) - sY

    for x, i in enumerate(pd_metadata['tile_filename']):
        if '__CHANNEL_.'.replace('_CHANNEL_',channel) not in i:
            continue
        tile2coor[i] = (pd_metadata['StageXPosition'][x]-shift_x,pd_metadata['StageYPosition'][x]-shift_y) #x,y

    maxX = max([tile2coor[i][0] for i in tile2coor]) + sX
    maxY = max([tile2coor[i][1] for i in tile2coor]) + sY
    index = 0



    new_im_tiles = Image.new('F', (int(maxX/compr_fac), int(maxY/compr_fac)))

    for i in tile2coor:
        tile = int([j for j in i.split('_') if j.startswith('S') == True and j[1:-1].replace('M','').isnumeric() == True and 'M' in j][0].split('M')[1])
        x_tile = np.ones(sX*sY).reshape((sX, sY))*(tile+1)
        try:
            im = Image.fromarray(x_tile)
        except:
            continue
        im.thumbnail((sX/compr_fac, sY/compr_fac))
        new_im_tiles.paste(im, (int(tile2coor[i][0]/compr_fac), int(tile2coor[i][1]/compr_fac)))
        index += 1
    return new_im_tiles

def generate_naive_stitch(input_metadata):

    tile2coor = dict()
    #pictures_folder = os.path.splitext(input_metadata)[0]
    pictures_folder = os.path.dirname(input_metadata)
    output_folder_cur = os.path.join(output_folder, os.path.basename(pictures_folder))
    if os.path.isdir(pictures_folder) == False:
        raise ValueError('Tile folder is not found')
    #naive_lump = Image.new('RGB', (3000, 3000))


    try:
        pd_metadata = pd.read_csv(input_metadata, sep=',')
        pd_metadata['StageYPosition']
    except:
        pd_metadata = pd.read_csv(input_metadata, sep=';')
        pd_metadata['StageYPosition']

    # Creating DAPI neighbour
    neig_dict = dict()



    if ',' in str(pd_metadata['ImagePixelSize'][0]):
        scalex, scaley = map(float, pd_metadata['ImagePixelSize'][0].split(','))
    else:
        scalex = float(pd_metadata['ImagePixelSize'][0]) + 0
        scaley = float(pd_metadata['ImagePixelSize'][0]) + 0

    # if set(pd_metadata['ImagePixelSize']) != set(['6.5,6.5']):
    #     print('Error scaling the pixel, define scaling in terms of the new values')
    #     error_to_be_solved



    scale = scalex/10

    pd_metadata['StageXPosition'] = pd_metadata['StageXPosition'] / scale
    pd_metadata['StageYPosition'] = pd_metadata['StageYPosition'] / scale

    all_y_lev = sorted(list(set(pd_metadata['StageYPosition'])))
    all_x_lev = sorted(list(set(pd_metadata['StageXPosition'])))

    sX = int(pd_metadata['Frame'][0].split(',')[2])
    sY = int(pd_metadata['Frame'][0].split(',')[3])

    shift_x = min(all_x_lev) - sX
    shift_y = min(all_y_lev) - sY


    for x, i in enumerate(pd_metadata['tile_filename']):
        if '_' + channel + '.' not in i:
            continue
        tile2coor[i] = (pd_metadata['StageXPosition'][x]-shift_x,pd_metadata['StageYPosition'][x]-shift_y) #x,y

    maxX = max([tile2coor[i][0] for i in tile2coor]) + sX
    maxY = max([tile2coor[i][1] for i in tile2coor]) + sY
    index = 0


    compr_fac = 10
    new_im = Image.new('L', (int(maxX/compr_fac), int(maxY/compr_fac)))

    im2array = dict()
    for i in tile2coor:
        try:
            im = Image.open(os.path.join(pictures_folder,i))
        except Exception as e:
            print('Error loading tile:', i)
            print(str(e))
            continue

        #im2array[i] = im

        #############
        #############
        #############
        arr_ = np.asarray(im)
        if arr_.dtype != np.dtype('uint8'):
            arr_ = arr_ / (2 ** 16 - 1) * (2 ** 8 - 1)
            arr_ = arr_.astype(np.uint8)
        im = Image.fromarray(arr_)
        im2array[i] = im.resize((int(sX/compr_fac), int(sY/compr_fac)), Image.LANCZOS)
        #############
        #############
        #############

    if do_99_push_condition == True and False:
        try:
            im2array = do_99_push(im2array)
        except Exception as e:
            print('Error doing 99_push', input_metadata,str(e))
            raise CollageError('do_99_push intensity normalisation failed.') from e


    try:
        for i in im2array:
            im = im2array[i]
            arr_ = np.asarray(im)

            if arr_.dtype != np.dtype('uint8'):
                arr_ = arr_ / (2 ** 16 - 1) * (2**8-1)
                arr_ = arr_.astype(np.uint8)
            im = Image.fromarray(arr_)
            #im.thumbnail((sX/compr_fac, sY/compr_fac))
            new_im.paste(im, (int(tile2coor[i][0]/compr_fac), int(tile2coor[i][1]/compr_fac)))
            index += 1
    except Exception as e:
        print('Error constructing the final naive stitching', input_metadata)
        raise CollageError('Failed to construct the final naive stitching.') from e

    try:
        round_ = [i for i in os.path.basename(pictures_folder).split('_') if i.startswith('R') == True and i[1::].isnumeric() == True][0]
    except Exception as e:
        print('Error finding round in the naive stitching', input_metadata)
        raise CollageError('Failed to find the round token in the naive stitching.') from e



    output_file = os.path.join(output_folder_cur,'naive_stitch',round_+'.jpeg')

    if not os.path.exists(os.path.join(output_folder_cur,'naive_stitch')):
        os.makedirs(os.path.join(output_folder_cur,'naive_stitch'))

    new_im.save(output_file)



def get_recons_im(im2, out_reg, coor_im1_int, coor_im2_int, im2_ori):

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
    im2_ori_reg = ndimage.zoom(im2_ori_reg, (out_reg['scale'], out_reg['scale']))
    im2_ori_reg = ndimage.shift(im2_ori_reg, (int(out_reg['tvec'][0]), int(out_reg['tvec'][1])), mode='wrap')

    '''
    im2_ori_reg = ndimage.rotate(im2, out_reg['angle'], reshape=False, cval=0)
    im2_ori_reg = ndimage.zoom(im2_ori_reg, (out_reg['scale'], out_reg['scale']))
    im2_ori_reg = ndimage.shift(im2_ori_reg, (int(out_reg['tvec'][0]), int(out_reg['tvec'][1])), mode='wrap')
    '''

    return im2_ori_reg, (0,0), True

'''

im2_ori_reg[:coor_im2_int[0], :] = 0
im2_ori_reg[coor_im2_int[1]:, :] = 0
im2_ori_reg[:, :coor_im2_int[2]] = 0
im2_ori_reg[:, coor_im2_int[3]:] = 0
    
red_channel = im1[:]
green_channel = im2_ori_reg[:].astype(np.uint8)
# Create a blank blue channel (you can use zeros or any value you want)
blue_channel = np.zeros_like(red_channel)

# Stack the channels to create an RGB image
rgb_image = np.dstack((red_channel, green_channel, blue_channel))

# Create an image from the NumPy array
image = Image.fromarray(rgb_image)

# Save the image to disk
image.save("/home/jon/Downloads/expression_input_data/tem.png")

'''

'''
d1 = np.min([im1_ori.shape[0], im2_ori_reg.shape[0]])
d2 = np.min([im1_ori.shape[1], im2_ori_reg.shape[1]])

rgb_comb = np.dstack((cv2.convertScaleAbs(im1_ori[0:d1, 0:d2], alpha=(255.0 / 255.0)),
                      cv2.convertScaleAbs(im2_ori_reg[0:d1, 0:d2], alpha=(255.0 / 255.0)),
                      cv2.convertScaleAbs(im2_ori_reg[0:d1, 0:d2], alpha=(255.0 / 255.0) * 0)))

im = Image.fromarray(rgb_comb)
if is_custom == True:
    im.save(os.path.join(output_folder, f_, 'QC', pair + '_custom.png'))
else:
    im.save(os.path.join(output_folder, f_, 'QC', pair + '.png'))
'''

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

    # Match the two sets of descriptors.
    matches = matcher.match(d1, d2)

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

def overlap(rec1, rec2):
    dx = min(rec1.x2, rec2.x2) - max(rec1.x1, rec2.x1)
    dy = min(rec1.y2, rec2.y2) - max(rec1.y1, rec2.y1)

    if dx >= 0 and dy >= 0:
        return True
    else:
        return False

# Resolved reference per (slide, scene), populated in run() from the manifest's
# is_reference rows using STEP 2's own naming convention (slide = text before the
# round token, scene = digits between S and M). Maps (slide, scene) -> (R-token,
# V-token), e.g. ("FR3","0") -> ("R17","V01"). Empty => fall back to legacy
# version-blind matching (preserves behaviour when no manifest map is available).
_REF_RV_BY_SLIDE_SCENE: dict = {}


def _parse_srv(name):
    """Parse (slide, scene, round_token, version_token) from a tile/folder name
    using step 2's convention. Returns None if the round or scene can't be found.
    A missing version token yields '' (single-version / no-V data)."""
    base = os.path.basename(str(name))
    toks = base.split('_')
    rtok = next((t for t in toks if t.startswith('R') and len(t) > 1 and t[1:].isdigit()), None)
    if rtok is None:
        return None
    vtok = next((t for t in toks if t.startswith('V') and len(t) > 1 and t[1:].isdigit()), '')
    scene = None
    for t in toks:
        if t.startswith('S') and 'M' in t:
            s_part = t[1:].split('M')[0]
            if s_part.isdigit():
                scene = s_part
                break
    if scene is None:
        return None
    slide = base.split('_' + rtok)[0]
    return slide, scene, rtok, vtok


def _strip_version(name):
    """Remove the _V<NN>_ token from a name (mirrors the legacy version-blind
    matching used as a fallback)."""
    vtok = next((t for t in name.split('_') if t.startswith('V') and len(t) > 1 and t[1:].isdigit()), None)
    return name.replace('_' + vtok + '_', '_') if vtok else name


def _rv_token(name):
    """Composite 'R<NN>_V<NN>' from a version-bearing name; bare round token
    if no version (single-version/legacy => unchanged behaviour)."""
    toks = os.path.basename(str(name)).split('_')
    r = next((t for t in toks if t.startswith('R') and len(t) > 1 and t[1:].isdigit()), None)
    if r is None:
        return None
    v = next((t for t in toks if t.startswith('V') and len(t) > 1 and t[1:].isdigit()), None)
    return r + '_' + v if v else r


def get_ref_round(curr_d, reference_round_number, all_t):
    """Return the element of `all_t` that is the reference-round/version
    counterpart of `curr_d` (same slide, scene, tile, channel).

    Uses the manifest-resolved reference (honouring reference_version) when
    available; otherwise falls back to the legacy version-blind match so behaviour
    is unchanged on data without a resolved map.
    """
    parsed = _parse_srv(curr_d)
    if parsed is None:
        return ''
    slide, scene, curr_R, curr_V = parsed

    ref = _REF_RV_BY_SLIDE_SCENE.get((slide, scene))
    if ref is not None:
        ref_R, ref_V = ref
    else:
        ref_R, ref_V = 'R' + str(reference_round_number).zfill(2), None

    # Swap the round token (and the version token when the reference version is
    # known) to build the target name, then prefer an exact, version-specific
    # match so the configured reference VERSION is honoured.
    d2find = curr_d.replace('_' + curr_R + '_', '_' + ref_R + '_')
    if ref_V:
        d2find = d2find.replace('_' + curr_V + '_', '_' + ref_V + '_') if curr_V else d2find
        for i in all_t:
            if i == d2find:
                return i
        # fall through to version-agnostic match if the exact one isn't in all_t

    # Legacy version-agnostic match (also the fallback when no resolved version).
    d2find_nov = _strip_version(d2find)
    for i in all_t:
        if _strip_version(i) == d2find_nov:
            return i
    return ''


def add_zero_padding(image, target_rows, target_cols):
    """
    Adds zero padding to an image until it reaches the given number of rows and columns.

    Parameters:
    image (np.array): The input image as a numpy array.
    target_rows (int): The desired number of rows.
    target_cols (int): The desired number of columns.

    Returns:
    np.array: The padded image.
    """
    current_rows, current_cols = image.shape[:2]

    # Calculate the padding for rows and columns
    pad_rows = target_rows - current_rows
    pad_cols = target_cols - current_cols

    # Check if padding is necessary
    if pad_rows < 0 or pad_cols < 0:
        raise ValueError("Target dimensions must be greater than or equal to the current dimensions.")

    # Add padding to the image
    # Handle padding for both 2D (grayscale) and 3D (color) images
    if image.ndim == 2:  # Grayscale image
        padded_image = np.pad(image,
                              ((0, pad_rows), (0, pad_cols)),
                              mode='constant',
                              constant_values=0)
    elif image.ndim == 3:  # Color image
        padded_image = np.pad(image,
                              ((0, pad_rows), (0, pad_cols), (0, 0)),
                              mode='constant',
                              constant_values=0)

    return padded_image
def naive_reg(i, reference_round_number, all_recon_f):
    reference_round = get_ref_round(i, reference_round_number, all_recon_f)
    if i == reference_round:
        return
    elif len(reference_round) == 0:
        print('Cant get reference_round for ', i)
        return
    n1 = all_recon[reference_round]
    n2 = all_recon[i]
    im1 = io.imread(n1)
    im2 = io.imread(n2)

    im1x, im1y = np.shape(im1)
    im2x, im2y = np.shape(im2)

    '''
    if im1x != im2x:
        print('Discrepancies in Naive stitching: Xs', im1x, im2x)
    if im1y != im2y:
        print('Discrepancies in Naive stitching: Ys', im1y, im2y)
    '''

    imx = max([im1x, im2x])
    imy = max([im1y, im2y])


    im1 = add_zero_padding(im1, imx, imy)
    im2 = add_zero_padding(im2, imx, imy)

    do_naive_reg_AI = True
    if do_naive_reg_AI == True:
        try:
            out_reg, final_method = do_ai_overlapp(im1, im2)
        except:
            do_naive_reg_AI = False
    if do_naive_reg_AI == False:
        try:
            out_reg = imreg_dft.imreg.similarity(im1[0:imx, 0:imy], im2[0:imx, 0:imy])
            out_reg_ = imreg_dft.imreg.translation(im1[0:imx, 0:imy], im2[0:imx, 0:imy])
        except Exception as e:
            print('Error in naive registration')
            print(e)

        err_x = abs(out_reg['tvec'][0] - out_reg_['tvec'][0])
        err_y = abs(out_reg['tvec'][1] - out_reg_['tvec'][1])
        if err_x > 20 or err_y > 20:
            xoff, yoff, exoff, eyoff = chi2_shift(im1[0:imx, 0:imy], im2[0:imx, 0:imy])  # Fourier, DFT upsampling method
            corrected_image2 = shift.shiftnd(im2, (-yoff, -xoff))
            out_reg_chi2 = imreg_dft.imreg.similarity(corrected_image2, im2)

            err_x = abs(out_reg['tvec'][0] - out_reg_chi2['tvec'][0])
            err_y = abs(out_reg['tvec'][1] - out_reg_chi2['tvec'][1])

            if err_x > 20 or err_y > 20:
                shift_, error, diffphase = phase_cross_correlation(im1, im2)
                out_reg_phase_cross_correlation = {'tvec': np.asarray(shift_)}
                err_x = abs(out_reg['tvec'][0] - out_reg_phase_cross_correlation['tvec'][0])
                err_y = abs(out_reg['tvec'][1] - out_reg_phase_cross_correlation['tvec'][1])
                if err_x > 20 or err_y > 20:
                    err_x_m = min(out_reg_phase_cross_correlation['tvec'][0], out_reg_chi2['tvec'][0], out_reg_['tvec'][0])
                    err_x_M = max(out_reg_phase_cross_correlation['tvec'][0], out_reg_chi2['tvec'][0], out_reg_['tvec'][0])
                    err_x = abs(err_x_M-err_x_m)
                    err_y_m = min(out_reg_phase_cross_correlation['tvec'][1], out_reg_chi2['tvec'][1], out_reg_['tvec'][1])
                    err_y_M = max(out_reg_phase_cross_correlation['tvec'][1], out_reg_chi2['tvec'][1], out_reg_['tvec'][1])
                    err_y = abs(err_y_M-err_y_m)
                    if err_x > 20 or err_y > 20:
                        print('ERROR do_naive_registration:', n1, n2)
                        print('\n***********' * 5)
                        return
                    out_reg = copy.copy(out_reg_)
    #f = os.path.dirname(n2)
    f_ = os.path.join(os.path.dirname(n2), reference_round + '______' + i + '.pkl')
    with open(f_, 'wb') as f:
        pickle.dump(out_reg, f)

    #im = Image.fromarray(out_reg['timg']).convert('L')
    #im.save(os.path.join(os.path.dirname(n2), reference_round + '______' + i + '.tiff'))

# pip install pandas pillow numpy scipy scikit-image imreg_dft opencv-python astroalign matplotlib pytest image-registration thunder-registration




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
    global folder_tiles, output_folder, reference_round_number, n_cores, channel
    global do_99_push_condition, do_naive_stitch, do_naive_registration
    global do_overlapping_tiles, do_tile_registration
    global path_to_model, do_ai_cons, export_consen_ima, do_overlapping_QC
    global do_8bit, do_progress, compr_fac
    global _CONSENSUS_CLUSTER_PX, _ANGLE_THRESHOLD_DEG, _PRIORITY_WEIGHT, _MIN_OVERLAP_AREA_FRAC
    global _INFERENCE_SERVICE, _SCORER_NAME
    # Driver-computed values that the (module-level) helper functions read as
    # globals. In the original these were module-level because the driver ran at
    # module scope; now that the driver lives in run() they must be declared
    # global here, or the forked workers see them as undefined. (Found via AST
    # analysis of which helper free-variables the driver assigns.)
    global all_recon, f_, r01, r02, slide_round_scene_file
    global slide_scene_round_2max_intensity, tileFolder2metafile, tiles2extremes, tiles2posis

    reg = cfg.register if isinstance(cfg.register, dict) else {}

    folder_tiles = cfg.input_dir
    output_folder = cfg.output_reg
    reference_round_number = str(cfg.reference_round)
    n_cores = int(cfg.n_cores)
    channel = cfg.channel
    do_99_push_condition = bool(reg.get("do_99_push", True))

    # Build the resolved-reference map (slide, scene) -> (R-token, V-token) from
    # the manifest's is_reference rows, using step 2's own naming convention. This
    # makes get_ref_round honour the configured reference_version instead of the
    # legacy version-blind, disk-order-arbitrary match. On failure we leave the
    # map empty and get_ref_round falls back to the legacy behaviour.
    global _REF_RV_BY_SLIDE_SCENE
    _REF_RV_BY_SLIDE_SCENE = {}
    try:
        from ..ingest import manifest as _mani_mod
        _mani_df = _mani_mod.load(cfg.manifest_path)
        for _p in _mani_df.loc[_mani_df["is_reference"] == True, "path"]:  # noqa: E712
            _fold = os.path.basename(os.path.dirname(str(_p)))
            _parsed = _parse_srv(_fold)
            if _parsed is not None:
                _sl, _sc, _rt, _vt = _parsed
                _REF_RV_BY_SLIDE_SCENE[(_sl, _sc)] = (_rt, _vt)
        print(f"  reference map: {len(_REF_RV_BY_SLIDE_SCENE)} (slide,scene) group(s) resolved from manifest")
    except Exception as _e:
        print(f"  WARNING: could not build reference map from manifest ({_e}); "
              f"using legacy reference matching.")
        _REF_RV_BY_SLIDE_SCENE = {}
    do_naive_stitch = bool(reg.get("do_naive_stitch", True))
    do_naive_registration = bool(reg.get("do_naive_registration", True))
    do_overlapping_tiles = bool(reg.get("do_overlapping_tiles", True))
    do_tile_registration = bool(reg.get("do_tile_registration", True))

    do_ai_cons = bool(reg.get("do_ai_consensus", True))
    export_consen_ima = bool(reg.get("export_consensus_images", True))
    do_overlapping_QC = False
    do_8bit = bool(reg.get("eight_bit", True))
    do_progress = False
    compr_fac = int(reg.get("compression_factor", 10))
    path_to_model = cfg.model_path

    # Phase-3 inference backend. 'auto' (default) tries the GPU-resident worker
    # first and falls back to the CPU pool if no usable GPU is found -- so the
    # same config runs unchanged on a workstation with a GPU and on a laptop or
    # CI box without one. GPU was unreliable earlier (predict() memory growth
    # under real multi-shape job load, then cuDNN autotune failing to find
    # scratch memory for its candidate algorithms once that was fixed -- see
    # _scorer.py's predict_patches and _gpu_worker_main's TF_CUDNN_USE_AUTOTUNE
    # setting) but both are now root-caused, fixed, and validated: the full
    # 4-step pipeline on GPU passes the tight byte-identical benchmark, and a
    # real-job stress replay (50 jobs, varying shapes) runs 50/50 clean. 'gpu'
    # and 'cpu_pool' force one or the other with no fallback (a missing GPU
    # under 'gpu' is a hard error), for deployments that want to assert which
    # device is actually being used. Both device paths call the identical
    # scoring code (score_job/score_job_batched) -- only the device differs.
    # 'subprocess_per_pair' is the legacy path (one model-loading subprocess
    # per pair) kept as a fallback / for A/B.
    inference_backend = str(reg.get("inference_backend", "auto")).lower()
    consensus_workers = int(reg.get("consensus_workers", n_cores))
    _SCORER_NAME = str(reg.get("scorer", "kimianet"))

    # Item 4: consensus thresholds from config (documented defaults)
    _CONSENSUS_CLUSTER_PX = float(reg.get("consensus_cluster_px", 10))
    _ANGLE_THRESHOLD_DEG = float(reg.get("angle_threshold_deg", 10))
    _PRIORITY_WEIGHT = int(reg.get("priority_weight", 2))
    _MIN_OVERLAP_AREA_FRAC = float(reg.get("min_overlap_area_frac", 0.00005))

    # Item 1: deterministic RANSAC + numpy
    seed = int(reg.get("seed", 0))
    cv2.setRNGSeed(seed); np.random.seed(seed)

    if do_ai_cons and not os.path.exists(path_to_model):
        raise FileNotFoundError(
            f"AlignQC model not found at {path_to_model}. Run "
            f"scripts/download_model.py, or set register.do_ai_consensus: false."
        )
    if CrossCorr is None:
        print("  note: thunder-registration not installed; its method is skipped.")

    # Start the persistent inference pool (cpu_pool backend) before any per-pair
    # worker is forked, so the workers inherit the live service + its queue. The
    # pool workers load TF in their own processes; main stays TF-free, so forking
    # the per-pair workers later remains deadlock-safe.
    if do_ai_cons and inference_backend in ("cpu_pool", "gpu", "auto"):
        from collage.steps._inference_service import CPUPoolService, GPUService
        os.makedirs(os.path.join(output_folder, "_pool_results"), exist_ok=True)
        _t_pool = time.time()

        def _start_cpu_pool():
            print(f"  starting inference pool: {consensus_workers} workers "
                  f"(scorer={_SCORER_NAME})...")
            svc = CPUPoolService(_SCORER_NAME, path_to_model, consensus_workers, output_folder)
            svc.start()
            return svc

        if inference_backend == "cpu_pool":
            _INFERENCE_SERVICE = _start_cpu_pool()
            _resolved_backend = "cpu_pool"
        elif inference_backend == "gpu":
            # Forced GPU: no fallback -- a caller that explicitly asked for GPU
            # wants a hard error if one isn't actually available, not a silent
            # (much slower) drop to CPU.
            print(f"  starting GPU inference worker (scorer={_SCORER_NAME})...")
            _INFERENCE_SERVICE = GPUService(_SCORER_NAME, path_to_model, output_folder)
            _INFERENCE_SERVICE.start()
            _resolved_backend = "gpu"
        else:  # 'auto' -- prefer GPU, fall back to the CPU pool for portability.
            # GPUService.start() spawns its worker with mp.get_context("spawn"),
            # so probing it this way never imports TensorFlow into *this* (main)
            # process -- preserving the fork-safety invariant above for the
            # per-pair workers started later. Any failure (no GPU, no CUDA
            # libs, driver issue, OOM) is caught here rather than propagated,
            # since 'auto' means "best available device", not "GPU or bust".
            try:
                print(f"  starting GPU inference worker (scorer={_SCORER_NAME})...")
                _svc = GPUService(_SCORER_NAME, path_to_model, output_folder)
                _svc.start()
                _INFERENCE_SERVICE = _svc
                _resolved_backend = "gpu"
            except Exception as e:
                print(f"  GPU inference worker unavailable ({e!r}); falling back to CPU pool.")
                _INFERENCE_SERVICE = _start_cpu_pool()
                _resolved_backend = "cpu_pool"
        print(f"  inference service ready in {time.time() - _t_pool:.1f}s")
    else:
        _resolved_backend = inference_backend

    _t_start = time.time()
    # Phase-3 profiling: start each run with a clean consensus-timing log (the
    # spawned AlignQC subprocesses append per-invocation load/inference times to it).
    try:
        _timing_csv = os.path.join(output_folder, 'test_for_consen', '_consensus_timing.csv')
        if os.path.exists(_timing_csv):
            os.remove(_timing_csv)
    except Exception:
        pass
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)



    #df_nei = pd.read_csv(file_nei)
    tileFolder2metafile = {}
    all_folders = [f for f in os.listdir(folder_tiles)
                   if any(p.startswith('R') and len(p) > 1 and p[1:].isdigit()
                          for p in f.split('_'))]
    for fx, f in enumerate(all_folders):
        if fx > 100000000:
            curr_R = [j for j in f.split('_') if j.startswith('R') and len(j) > 1 and j[1::].isdigit() == True][0]
            if int(curr_R[1::]) != int(reference_round_number):
                continue
        #if 'ITALY5_R08_V01_MEL05' not in f and 'ITALY5_R01' not in f:
        #    continue
        print('Generating metadata structure',fx, len(all_folders))
        cur_folder = os.path.join(folder_tiles, f)
        if os.path.isdir(cur_folder) == False:
            continue
        metafile_ =  [i for i in os.listdir(cur_folder) if i.endswith('.csv')]
        if len(metafile_) != 1:
            print('ERROR finding metafiles')
            print('\n***********'*5)
            print(cur_folder)
            print('\n***********'*5)
            continue
        tileFolder2metafile[metafile_[0]] = cur_folder


    if do_naive_stitch == True:
        c2p = {c: None for c in range(n_cores)}
        c2file = {c: None for c in range(n_cores)}
        failed_elements = []
        for input_metadatax, input_metadata in enumerate(tileFolder2metafile): #PARALELIZAR ESTE BUCLE!
            time.sleep(0.07)
            if do_progress == True:
                ws = aux_func.send_task_evolution(ws, int(input_metadatax / len(tileFolder2metafile) * 1000) / 10 / 5 , ind_, server_id)

            if n_cores == 1:
                print('Generating Naive stitching...', input_metadata, input_metadatax, '/', len(tileFolder2metafile))
                generate_naive_stitch(os.path.join(tileFolder2metafile[input_metadata], input_metadata))
            else:
                while True:
                    time.sleep(0.1)
                    c_core = -1
                    for c in c2p:
                        if type(c2p[c]) == type(None):
                            c_core = c + 0
                            break
                        elif c2p[c].is_alive() == False:
                            pictures_folder = os.path.dirname(os.path.join(tileFolder2metafile[c2file[c]], input_metadata))
                            output_folder_cur = os.path.join(output_folder, os.path.basename(pictures_folder))
                            round_ = [i for i in os.path.basename(pictures_folder).split('_') if i.startswith('R') == True and i[1::].isnumeric() == True][0]
                            if os.path.isfile(os.path.join(output_folder_cur, 'naive_stitch', round_ + '.jpeg')) == False:
                                failed_elements.append(c2file[c])

                            print('Done ', c2file[c])
                            c_core = c + 0
                            break

                    if c_core != -1:
                        break #GC38BT_R03_V01_CODEX_JP_S0M

                print('Generating Naive stitching...',input_metadata, input_metadatax, '/', len(tileFolder2metafile))
                p = Process(target= generate_naive_stitch,  args=(os.path.join(tileFolder2metafile[input_metadata], input_metadata),))
                p.start()
                c2p[c_core] = p
                c2file[c_core] = input_metadata
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
                    pictures_folder = os.path.dirname(os.path.join(tileFolder2metafile[c2file[c]], input_metadata))
                    output_folder_cur = os.path.join(output_folder, os.path.basename(pictures_folder))
                    round_ = [i for i in os.path.basename(pictures_folder).split('_') if
                              i.startswith('R') == True and i[1::].isnumeric() == True][0]
                    if os.path.isfile(os.path.join(output_folder_cur, 'naive_stitch', round_ + '.jpeg')) == False:
                        failed_elements.append(c2file[c])
                    c2p[c] = None
            if do_break == True:
                print('Done all cores')
                break
        for input_metadatax, input_metadata in enumerate(failed_elements): #PARALELIZAR ESTE BUCLE!
            if do_progress == True:
                ws = aux_func.send_task_evolution(ws, int(input_metadatax/len(failed_elements) * 1000) / 10 , ind_, server_id)
            print('RE-Generating Naive stitching...', input_metadata, input_metadatax, '/', len(failed_elements))
            try:
                generate_naive_stitch(os.path.join(tileFolder2metafile[input_metadata], input_metadata))
            except Exception as e:
                print('**********\n*5')
                print('Error in Re-Generating Naive stitching')
                print(str(e))
                print('**********\n*5')

    all_recon = {}
    _is_round = lambda name: any(p.startswith('R') and len(p) > 1 and p[1:].isdigit()
                                 for p in name.split('_'))
    for f_ in os.listdir(output_folder):
        f = os.path.join(output_folder,f_)
        if os.path.isdir(f) == False:
            continue
        # Skip COLLAGE's own helper/working folders (neighbour_stitching,
        # stitching_QC_plots, stitching_coords, test_for_consen, ...). Only the
        # round folders carry a naive_stitch reconstruction.
        if not _is_round(f_):
            continue
        try:
            all_recon[os.path.basename(f)] = [os.path.join(f,'naive_stitch',i) for i in os.listdir(os.path.join(f,'naive_stitch')) if i.endswith('.jpeg')][0]
        except Exception as e:
            print('WARNING: round folder', f_, 'has no naive_stitch reconstruction:', e)
    if do_naive_registration == True:

        #all_recon = sorted([i for i in os.listdir(os.path.join(output_folder,'naive_stitch')) if i.endswith('.jpeg') and i.startswith('R')])



        all_recon_f = list(all_recon.keys())
        c2p = {c: None for c in range(n_cores)}
        c2file = {c: None for c in range(n_cores)}
        failed_elements = []
        for x, i in enumerate(all_recon): #PARALELIZAR ESTE BUCLE!
            #if 'ITALY5_R08' not in i:
            #    continue
            time.sleep(1)
            print('Doing naive registration:',x,len(all_recon))

            if do_progress == True:
                ws = aux_func.send_task_evolution(ws, int(x / len(all_recon) * 1000) / 10 / 5 + 5, ind_, server_id)

            reference_round = get_ref_round(i, reference_round_number, all_recon_f)
            if i == reference_round:
                continue
            elif len(reference_round) == 0:
                print('Cant get reference_round for ', i)
                reference_round = get_ref_round(i, reference_round_number, all_recon_f)
                continue


            if n_cores == 1:
                naive_reg(i, reference_round_number, all_recon_f)
            else:
                while True:
                    time.sleep(0.1)
                    c_core = -1
                    for c in c2p:
                        if type(c2p[c]) == type(None):
                            c_core = c + 0
                            break
                        elif c2p[c].is_alive() == False:
                            f_temp = os.path.join(os.path.dirname(all_recon[c2file[c]]),
                                                  get_ref_round(c2file[c], reference_round_number,
                                                                all_recon_f) + '______' + c2file[c] + '.pkl')
                            if os.path.isfile(f_temp) == False:
                                failed_elements.append(c2file[c])
                            c_core = c + 0
                            break

                    if c_core != -1:
                        break

                p = Process(target= naive_reg,  args=(i, reference_round_number, all_recon_f,))
                p.start()
                c2p[c_core] = p
                c2file[c_core] = i
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
                    f_temp = os.path.join(os.path.dirname(all_recon[c2file[c]]),
                                          get_ref_round(c2file[c], reference_round_number,
                                                        all_recon_f) + '______' + c2file[c] + '.pkl')
                    if os.path.isfile(f_temp) == False:
                        failed_elements.append(c2file[c])
                    else:
                        try:
                            with open('data.pkl', 'rb') as file:
                                data = pickle.load(file)

                            #'overlapping_template_' + r01 + '______' + r02 + '.pkl')
                        except Exception as e:
                            failed_elements.append(c2file[c])

                    c2p[c] = None

            if do_break == True:
                print('Done all cores')
                break

        for x, i in enumerate(all_recon):
            f_temp = os.path.join(os.path.dirname(all_recon[i]),
                                  get_ref_round(i, reference_round_number,
                                                all_recon_f) + '______' + i + '.pkl')
            if os.path.isfile(f_temp) == False:
                failed_elements.append(i)

        for x, i in enumerate(failed_elements): #YYYYYZZZZZZZ revsar porque entrea casi siempre aqui
            if do_progress == True:
                ws = aux_func.send_task_evolution(ws, int(x/len(failed_elements) * 1000) / 10 , ind_, server_id)
            print('RE-Doing naive registration...', i, x, '/', len(failed_elements))
            try:
                naive_reg(i, reference_round_number, all_recon_f)
            except Exception as e:
                print('**********\n*5')
                print('Error in Re-Doing naive registration')
                print(str(e))
                print('**********\n*5')

    if do_overlapping_tiles == True:

        all_pks = dict()
        all_t = [os.path.basename(f) for f in os.listdir(output_folder)]
        for f_ in os.listdir(output_folder):
            #if 'ITALY5_R08' not in f_:
            #    continue
            f = os.path.join(output_folder,f_)
            reference_round = get_ref_round( os.path.basename(f) , reference_round_number, all_t)
            if not _is_round(f_):
                continue
            if len(reference_round) == 0:
                print('Cant get reference_round for ', os.path.basename(f) )
                continue
            if os.path.isdir(f) == False or os.path.basename(f) == reference_round:
                continue
            try:
                out_tt = os.listdir(os.path.join(f,'naive_stitch'))
                #print(out_tt)
                # Initialize a list to hold the matching paths
                matching_files = []

                # Iterate through each item in out_tt
                for i in out_tt:
                    # Check if the item ends with '.pkl' and does not start with 'overlapping_template'
                    if i.endswith('.pkl') and not i.startswith('overlapping_template'):
                        # If both conditions are met, construct the full path and add it to the list
                        matching_files.append(os.path.join(f, 'naive_stitch', i))
                        #print('IS OK', i)
                    else:
                        pass
                        #print('IS NOT OK', i)

                # Take the first item from the matching_files list and assign it to the dictionary
                all_pks[os.path.basename(f)] = matching_files[0]


                #all_pks[os.path.basename(f)] = [os.path.join(f,'naive_stitch',i) for i in out_tt if i.endswith('.pkl') and i.startswith('overlapping_template') == False][0]
            except Exception as e:
                print('Cant load naive registration data for case', os.path.basename(f), str(e))
                print('Error:', str(e))
                continue

        '''
        for cur_pair in all_pks:
            f_ = os.path.basename(all_pks[cur_pair])

            r01 = f_.split('______')[0]
            r02 = f_.split('______')[1].replace('.pkl', '')

            #tiles2posis = get_overlapping_tiles(cur_pair)
            get_overlapping_tiles(f_, all_pks[cur_pair])
        '''

        c2p = {c: None for c in range(n_cores)}
        c2file = {c: None for c in range(n_cores)}
        failed_elements = []
        for cur_pairx, cur_pair in enumerate(all_pks):
            time.sleep(1)


            if do_progress == True:
                ws = aux_func.send_task_evolution(ws, int(cur_pairx / len(all_pks) * 1000) / 10 / 30 + 10, ind_, server_id)

            f_ = os.path.basename(all_pks[cur_pair])

            r01 = f_.split('______')[0]
            r02 = f_.split('______')[1].replace('.pkl', '')

            print('Getting final overlap information...', cur_pairx, '/', len(all_pks))

            if n_cores == 1:
                get_overlapping_tiles(f_, all_pks[cur_pair])
            else:

                while True:
                    time.sleep(0.1)

                    c_core = -1
                    for c in c2p:
                        if type(c2p[c]) == type(None):
                            c_core = c + 0
                            break
                        elif c2p[c].is_alive() == False:
                            curr_pair = c2file[c]
                            f_ = os.path.basename(all_pks[cur_pair])
                            r01 = f_.split('______')[0]
                            r02 = f_.split('______')[1].replace('.pkl', '')
                            f_temp = os.path.join(os.path.dirname(all_pks[cur_pair]),
                                                  'overlapping_template_' + r01 + '______' + r02 + '.pkl')
                            time.sleep(0.5)
                            if os.path.isfile(f_temp) == False:
                                failed_elements.append(c2file[c])
                                print('File dont exist', f_temp)
                            else:
                                print('File exist', f_temp)
                            c_core = c + 0
                            break

                    if c_core != -1:
                        break

                p = Process(target= get_overlapping_tiles,  args=(f_, all_pks[cur_pair],))
                p.start()
                c2p[c_core] = p
                c2file[c_core] = cur_pair
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
                    c2p[c].join()
                    # c2p[c].terminate()
                    c2p[c] = None
                    print('ending core ', c)
                    break
                else:
                    print('Process is failed', c)
                    curr_pair = c2file[c]
                    f_ = os.path.basename(all_pks[cur_pair])
                    r01 = f_.split('______')[0]
                    r02 = f_.split('______')[1].replace('.pkl', '')
                    f_temp = os.path.join(os.path.dirname(all_pks[cur_pair]),
                                          'overlapping_template_' + r01 + '______' + r02 + '.pkl')
                    if os.path.isfile(f_temp) == False:
                        failed_elements.append(c2file[c])
                        print('File dont exist 2', f_temp)
                    else:
                        print('File exist 2', f_temp)

                    c2p[c] = None

            if do_break == True:
                print('Done all cores')
                break

        for cur_pairx, cur_pair in enumerate(failed_elements):
            f_ = os.path.basename(all_pks[cur_pair])
            if do_progress == True:
                ws = aux_func.send_task_evolution(ws, int(x/len(failed_elements) * 1000) / 10 , ind_, server_id)
            print('Re-Getting final overlap information...', cur_pairx, '/', len(failed_elements))
            try:
                get_overlapping_tiles(f_, all_pks[cur_pair])
            except Exception as e:
                print('**********\n*5')
                print('Error in Re-Getting final overlap information')
                print(str(e))
                print('**********\n*5')


    if do_tile_registration == True:
        slide_scene_round_2max_intensity = dict()
        all_to_do_tile_reg = {}
        all_t = [os.path.basename(f) for f in os.listdir(output_folder)]
        for f_ in sorted(os.listdir(output_folder)):
            #if 'WP3.I_R13_V02_MVH01_MVH_S4' not in f_:
            #    continue
            f = os.path.join(output_folder,f_)
            if os.path.isdir(f) == False:
                continue
            if not _is_round(f_):
                continue
            reference_round = get_ref_round( f_ , reference_round_number, all_t)
            if len(reference_round) == 0:
                print('Cant get rerefence_round for', f_)
                continue
            if f_ == reference_round:
                continue
            try:
                out_tt = os.listdir(os.path.join(f, 'naive_stitch'))
                #print(out_tt)
                # Initialize a list to hold the matching paths
                matching_files = []

                # Iterate through each item in out_tt
                for i in out_tt:
                    # Check if the item ends with '.pkl' and does not start with 'overlapping_template'
                    if i.endswith('.pkl') and i.startswith('overlapping_template'):
                        # If both conditions are met, construct the full path and add it to the list
                        matching_files.append(os.path.join(f, 'naive_stitch', i))
                        #print('IS OK', i)
                    else:
                        pass
                        #print('IS NOT OK', i)

                # Take the first item from the matching_files list and assign it to the dictionary
                all_to_do_tile_reg[os.path.basename(f)] = matching_files[0]

                #all_to_do_tile_reg[os.path.basename(f)] = [os.path.join(f,'naive_stitch',i) for i in os.listdir(os.path.join(f,'naive_stitch')) if i.endswith('.pkl') and i.startswith('overlapping_template_')][0]
            except Exception as e:
                print('Error:', str(e))
                print('Cant load naive registration data for case', os.path.basename(f))
                continue


        slide_round_scene_file = dict()
        for m in tileFolder2metafile:
            pictures_folder = tileFolder2metafile[m]
            mm = os.path.basename(pictures_folder)
            round_ = [i for i in mm.split('_') if i.startswith('R') == True and i[1::].isnumeric() == True][0]
            scene_ = [i[1:-1] for i in mm.split('_') if i.startswith('S') == True and i.endswith('M') == True and i[1:-1].isnumeric() == True][0]
            slide_ = m.split('_' + round_)[0]
            rv_ = _rv_token(mm)
            if slide_ not in slide_round_scene_file:
                slide_round_scene_file[slide_] = dict()
            if scene_ not in slide_round_scene_file[slide_]:
                slide_round_scene_file[slide_][scene_] = dict()
            if rv_ not in slide_round_scene_file[slide_][scene_]:
                slide_round_scene_file[slide_][scene_][rv_] = dict()
            all_tiles = [i for i in os.listdir(os.path.join(folder_tiles,pictures_folder)) if i.endswith('.tiff')]
            for til in all_tiles:
                if '__CHANNEL_.tif'.replace('_CHANNEL_',channel) not in til:
                    continue

                tile = int([j for j in til.split('_') if
                            j.startswith('S') == True and j[1:-1].replace('M', '').isnumeric() == True and 'M' in j][
                               0].split('M')[1])
                slide_round_scene_file[slide_][scene_][rv_][tile] = os.path.join(folder_tiles,pictures_folder,til)

        for f_x, f_ in enumerate(all_to_do_tile_reg):
            #if f_ != 'BM_R012222_V02_BENCHMARK_ND_S0M':
            #    continue

            file = open(all_to_do_tile_reg[f_], 'rb')
            tiles2extremes = pickle.load(file)
            file.close()

            f__ = os.path.basename(all_to_do_tile_reg[f_])
            r01_ = f__.split('______')[0].split('overlapping_template_')[1]
            r02_ = f__.split('______')[1].replace('.pkl', '')

            r01 = _rv_token(r01_)
            r02 = _rv_token(r02_)

            all_01 = [i for i in tiles2extremes if int(float(i.split('_')[0])) == 1]
            all_02 = [i for i in tiles2extremes if int(float(i.split('_')[0])) == 2]

            tiles2posis = dict()
            RECT_NAMEDTUPLE = namedtuple('RECT_NAMEDTUPLE', 'x1 x2 y1 y2')

            round_ = [i for i in f_.split('_') if i.startswith('R') == True and i[1::].isnumeric() == True][0]
            scene_ = [i[1:-1] for i in f_.split('_') if i.startswith('S') == True and i.endswith('M') == True and i[1:-1].isnumeric() == True][0]
            slide_ = f_.split('_' + round_)[0]

            if do_99_push_condition:
                reference_round = get_ref_round(f_, reference_round_number, all_t)
                round_r = [i for i in reference_round.split('_') if i.startswith('R') == True and i[1::].isnumeric() == True][0]

                try:
                    slide_scene_round_2max_intensity[slide_ + '__' + scene_ + '__' + r01]
                except:
                    d_ = slide_round_scene_file[slide_][scene_][r01]
                    # List to hold all pixel values
                    all_pixels = []

                    # Load images and extract pixel values
                    for key, path in d_.items():
                        image = Image.open(path)
                        image_array = np.array(image)
                        all_pixels.extend(image_array.ravel())

                    # Convert the list of all pixels to a numpy array
                    all_pixels_array = np.array(all_pixels)

                    # Calculate the 99th percentile
                    slide_scene_round_2max_intensity[slide_ + '__' + scene_ + '__' + r01] = np.percentile(all_pixels_array, 99)

                try:
                    slide_scene_round_2max_intensity[slide_ + '__' + scene_ + '__' + r02]
                except:
                    d_ = slide_round_scene_file[slide_][scene_][r02]
                    # List to hold all pixel values
                    all_pixels = []

                    # Load images and extract pixel values
                    for key, path in d_.items():
                        image = Image.open(path)
                        image_array = np.array(image)
                        all_pixels.extend(image_array.ravel())

                    # Convert the list of all pixels to a numpy array
                    all_pixels_array = np.array(all_pixels)

                    # Calculate the 99th percentile
                    slide_scene_round_2max_intensity[slide_ + '__' + scene_ + '__' + r02] = np.percentile(all_pixels_array, 99)



            for e01 in all_01:
                Rect1 = RECT_NAMEDTUPLE(tiles2extremes[e01][0], tiles2extremes[e01][1], tiles2extremes[e01][2], tiles2extremes[e01][3])
                for e02 in all_02:
                    #if e02 != '02_27' or e01 != '01_45':
                    #    continue
                    #if e01 != '01_7':
                    #    continue
                    Rect2 = RECT_NAMEDTUPLE(tiles2extremes[e02][0], tiles2extremes[e02][1], tiles2extremes[e02][2],tiles2extremes[e02][3])
                    if overlap(Rect1, Rect2) == True:
                        x_min = max([tiles2extremes[e01][0],tiles2extremes[e02][0]])
                        x_max = min([tiles2extremes[e01][1],tiles2extremes[e02][1]])
                        y_min = max([tiles2extremes[e01][2],tiles2extremes[e02][2]])
                        y_max = min([tiles2extremes[e01][3],tiles2extremes[e02][3]])
                        tiles2posis[e01+'_'+e02] = [x_min, x_max, y_min, y_max]


            ####################
            ### expanding pairs based on Neighbors
            ####################
            do_refining_overlap = False
            if do_refining_overlap == True:
                from scipy.ndimage import label

                dir_sec = os.path.join(folder_tiles, r02_)
                input_metadata = [os.path.join(dir_sec, i) for i in os.listdir(dir_sec) if i.endswith('.csv') == True and r02_ in i][0]
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

                all_tiles_1 = sorted(list(set([i.split('_')[1] for i in tiles2posis])))
                for t1 in all_tiles_1:
                    covered_area = np.zeros((np_y, np_x), dtype=np.uint8)
                    all_tiles_2 = [i for i in tiles2posis if i.split('_')[1] == t1]
                    c_tiles = []
                    t2x2coor_im2 = {}
                    for t2x, t2 in enumerate(all_tiles_2):

                        c_tile = [i for i in im2neighbour if r02 in i and 'DAPI' in i and 'M' + t2.split('_')[-1] in i][0]
                        c_tiles.append(c_tile)

                        area = tiles2posis[t2]

                        coor_im1 = tiles2extremes['_'.join(t2.split('_')[0:2])]
                        coor_im2 = tiles2extremes['_'.join(t2.split('_')[2::])]  # [193, 378, 2674, 2859]

                        coor_im1_int = [area[0] - coor_im1[0], area[1] - coor_im1[0], area[2] - coor_im1[2],
                                        area[3] - coor_im1[2]]
                        coor_im2_int = [area[0] - coor_im2[0], area[1] - coor_im2[0], area[2] - coor_im2[2],
                                        area[3] - coor_im2[2]]

                        coor_im1_int = list(np.array(coor_im1_int) * compr_fac)
                        coor_im2_int = list(np.array(coor_im2_int) * compr_fac)
                        coor_im1_int_ori = np.copy(coor_im1_int)
                        coor_im2_int_ori = np.copy(coor_im2_int)

                        extend_overlap_xM = min(np_y - coor_im1_int[1], np_y- coor_im2_int[1])
                        coor_im1_int[1] = coor_im1_int[1] + extend_overlap_xM
                        coor_im2_int[1] = coor_im2_int[1] + extend_overlap_xM
                        extend_overlap_xm = min(coor_im1_int[0], coor_im2_int[0])
                        coor_im1_int[0] = coor_im1_int[0] - extend_overlap_xm
                        coor_im2_int[0] = coor_im2_int[0] - extend_overlap_xm

                        extend_overlap_yM = min(np_x- coor_im1_int[3], np_x - coor_im2_int[3])
                        coor_im1_int[3] = coor_im1_int[3] + extend_overlap_yM
                        coor_im2_int[3] = coor_im2_int[3] + extend_overlap_yM
                        extend_overlap_ym = min(coor_im1_int[2], coor_im2_int[2])
                        coor_im1_int[2] = coor_im1_int[2] - extend_overlap_ym
                        coor_im2_int[2] = coor_im2_int[2] - extend_overlap_ym

                        t2x2coor_im2[t2x] = coor_im2_int

                        covered_area[coor_im1_int[0]:coor_im1_int[1], coor_im1_int[2]:coor_im1_int[3]] = t2x + 1

                    if np.min(covered_area) != 0:
                        continue

                    labeled_array, num_clusters = label(covered_area == 0)

                    prev_n = 10**60
                    while True:
                        '''
                
                    #for cluster_label in range(1, num_clusters + 1):
                        ## Get the coordinates where the cluster label is present
                        #cluster_coordinates = np.argwhere(labeled_array == cluster_label)
                        ## Find the minimum and maximum values along each axis
                        '''

                        labeled_array, num_clusters = label(covered_area == 0)
                        if num_clusters == 0:
                            break

                        cluster_coordinates = np.argwhere(labeled_array == 1)

                        if cluster_coordinates.shape[0] == prev_n:
                            break
                        prev_n = cluster_coordinates.shape[0]

                        min_x = np.min(cluster_coordinates[:, 0])
                        max_x = np.max(cluster_coordinates[:, 0])
                        min_y = np.min(cluster_coordinates[:, 1])
                        max_y = np.max(cluster_coordinates[:, 1])

                        # Calculate the corner coordinates
                        top_left = (min_x, min_y)
                        top_right = (min_x, max_y)
                        bottom_left = (max_x, min_y)
                        bottom_right = (max_x, max_y)

                        #print([min_x, max_x, min_y, max_y])

                        all_left = []
                        if min_y > 0:
                            all_left = np.unique(covered_area[:,min_y-1])
                            for t2x_ in all_left:
                                if t2x_ > 100:
                                    continue
                                t2x = t2x_ - 1
                                t2_tile = c_tiles[t2x]
                                coor_im2 = t2x2coor_im2[t2x]
                                coor_im2_glob = tile2coor[t2_tile]
                                if len(im2neighbour[t2_tile]['r_n']) > 0:
                                    im3_ = im2neighbour[t2_tile]['r_n']
                                    tile_3 = [i.split('M')[1] for i in im3_.split('_') if i.startswith('S') == True and 'M' in i and i.replace('S','').replace('M','').isnumeric() == True][0]
                                    coor_im3_glob = tile2coor[im3_]
                                    ovlapp_x = 1 - (coor_im2_glob[0] - coor_im3_glob[0])/np_x
                                    y_min3 = 0; y_max3 = min(np_x, coor_im2[2] + int(ovlapp_x * np_x))
                                    x_min3 = coor_im2[0]; x_max3 = coor_im2[1]
                                    t3 = '01_' + t1 + '_02_' + tile_3
                                    tiles2posis[t3] = [x_min3, x_max3, y_min3, y_max3]
                                    covered_area[x_min3:x_max3, y_min3:y_max3] = (t2x + 1) + 100
                        all_right = []
                        if max_y + 1 < np_x: #pending to check
                            all_right = np.unique(covered_area[:,max_y+1])
                            for t2x_ in all_right:
                                if t2x_ > 100:
                                    continue
                                t2x = t2x_ - 1
                                t2_tile = c_tiles[t2x]
                                coor_im2 = t2x2coor_im2[t2x]
                                coor_im2_glob = tile2coor[t2_tile]
                                if len(im2neighbour[t2_tile]['l_n']) > 0:
                                    im3_ = im2neighbour[t2_tile]['l_n']
                                    tile_3 = [i.split('M')[1] for i in im3_.split('_') if i.startswith('S') == True and 'M' in i and i.replace('S','').replace('M','').isnumeric() == True][0]
                                    coor_im3_glob = tile2coor[im3_]
                                    ovlapp_x = 1 - (coor_im2_glob[0] - coor_im3_glob[0])/np_x
                                    y_min3 = 0; y_max3 = min(np_x, coor_im2[2] + int(ovlapp_x * np_x))
                                    x_min3 = coor_im2[0]; x_max3 = coor_im2[1]
                                    t3 = '01_' + t1 + '_02_' + tile_3
                                    tiles2posis[t3] = [x_min3, x_max3, y_min3, y_max3]
                                    covered_area[x_min3:x_max3, y_min3:y_max3] = (t2x + 1) + 100
                        all_top = []
                        if min_x > 0: #pending to check
                            all_top = np.unique(covered_area[min_x-1, :])
                        all_botton = []
                        if max_x + 1 < np_y: #pending to check
                            all_botton = np.unique(covered_area[max_x+1, :])
                            for t2x_ in all_botton:
                                if t2x_ > 100:
                                    continue
                                t2x = t2x_ - 1
                                t2_tile = c_tiles[t2x]
                                coor_im2 = t2x2coor_im2[t2x]
                                coor_im2_glob = tile2coor[t2_tile]
                                if len(im2neighbour[t2_tile]['d_n']) > 0:
                                    im3_ = im2neighbour[t2_tile]['d_n']
                                    tile_3 = [i.split('M')[1] for i in im3_.split('_') if i.startswith('S') == True and 'M' in i and i.replace('S','').replace('M','').isnumeric() == True][0]
                                    coor_im3_glob = tile2coor[im3_]
                                    ovlapp_x = 1 - abs(coor_im2_glob[1] - coor_im3_glob[1])/np_y
                                    y_min3 = coor_im2[2]; y_max3 = coor_im2[3]
                                    x_min3 = coor_im2[1]; x_max3 = min(np_y, coor_im2[1] + int(ovlapp_x * np_y))
                                    t3 = '01_' + t1 + '_02_' + tile_3
                                    tiles2posis[t3] = [x_min3, x_max3, y_min3, y_max3]
                                    covered_area[x_min3:x_max3, y_min3:y_max3] = (t2x + 1) + 100



                ####################
                ###/expanding pairs based on Neighbors
                ####################
            do_naive_pair_expan = True
            if do_naive_pair_expan == True:
                dir_sec = os.path.join(folder_tiles, r02_)
                input_metadata = \
                [os.path.join(dir_sec, i) for i in os.listdir(dir_sec) if i.endswith('.csv') == True and r02_ in i][0]
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

                tile2coor = get_tile2coord(input_metadata, df_metadata)
                im2neighbour = get_neigt(df_metadata, tile2coor)

                done_p01 = set()
                tiles2posis_freez = copy.copy(tiles2posis)
                for pair in tiles2posis_freez:
                    p01 = '_'.join(pair.split('_')[0:2])
                    if p01 in done_p01:
                        continue
                    done_p01.add(p01)
                    tiles2posis = extend_overlap(slide_, scene_, pair, tile2coor, im2neighbour)

            print(os.path.join(output_folder, f_, 'QC'), os.path.exists(os.path.join(output_folder, f_, 'QC')))
            if not os.path.exists(os.path.join(output_folder, f_, 'QC')):
                os.makedirs(os.path.join(output_folder, f_, 'QC'))

            c2p = {c:None for c in range(n_cores)}
            c2time_nonActive = {c:None for c in range(n_cores)}
            c2file = {c: None for c in range(n_cores)}
            failed_elements = []

            t_progres = time.time()
            for pairx, pair in enumerate(tiles2posis): #PARALELIZAR
                #if '01_4_02_4' not in pair or r02 != 'R06':
                #    continue
                #if '01_57' not in pair:
                #    continue
                #if f_x < 96:
                    #continue
                time.sleep(0.001)

                if do_progress == True and time.time()-t_progres > 10:
                    ws = aux_func.send_task_evolution(ws, int(pairx / len(tiles2posis) * 1000) / 10 / 60 + 40, ind_, server_id)
                    t_progres = time.time()


                #if pair != '01_23_02_23':
                #    continue
                #else:
                    #continue

                #if pair != '01_13_02_13' or '_R02_' not in f_ or 'S1M' not in f_ or 'KID1' not in slide_:
                #if '_R02_' not in f_ or 'S1M' not in f_ or 'KID1' not in slide_:
                    #continue
                #\\Nas-ib\milan\shared\3d_stitching\kidney_project\KidneyProject_output_reg\KID1_R02_V1_KIDNEY_YVH_S1M\QC
                #if 'TESS2_R05_V02_KID03_ND_S0M' not in f_:
                #    continue

                if n_cores == 1:
                    print('Doing sample', f_, f_x, len(all_to_do_tile_reg), 'Starting pair ', pair, pairx, '/',
                          len(tiles2posis))
                    overlapping_func(slide_, scene_, pair, r01, r02)
                else:
                    n_iter = 0
                    while True:

                        all_s = []
                        for c in c2p:
                            if type(c2p[c]) != type(None):
                                try:
                                    all_s.append(psutil.Process(c2p[c].pid).status())
                                except:
                                    continue
                        if n_iter % 100 == 0:
                            counter = Counter(all_s)
                            for element, count in counter.items():
                                print(f"{element}: {count}")


                        n_iter += 1
                        time.sleep(0.01)
                        c_core = -1
                        c_active = -1
                        for c in c2p:
                            if type(c2p[c]) == type(None):
                                c2time_nonActive[c] = time.time()
                                continue
                            try:
                                process = psutil.Process(c2p[c].pid)
                                if process.status() == 'running':
                                    c2time_nonActive[c] = time.time()
                            except:
                                pass


                        for c in c2p:
                            if type(c2p[c]) == type(None):
                                c_core = c + 0
                                break
                            elif c2p[c].is_alive() == False:
                                print('Process not alive', c2p[c])
                                f_temp = os.path.join(output_folder, f_, 'QC', c2file[c] + '_done.json')
                                if os.path.isfile(f_temp) == False:
                                    failed_elements.append(c2file[c])
                                c_core = c + 0
                                break
                            else:
                                f_temp = os.path.join(output_folder, f_, 'QC', c2file[c] + '_done.json')
                                if os.path.isfile(f_temp) == True:
                                    time.sleep(0.1)
                                    try:
                                        json_temp = json.load(open(f_temp,'r'))
                                    except Exception as e:
                                        print('Error loading checker file', f_temp)
                                        print(e)
                                        continue
                                    print('Process alive but to be stoped', c2p[c])
                                    #time.sleep(2)
                                    c_core = c + 0
                                    if n_iter % 100 == 0:
                                        try:
                                            process = psutil.Process(c2p[c].pid)
                                            print(n_iter, f"Process status: {process.status()}")
                                            print(n_iter, f"Process is running: {process.is_running()}")
                                        except psutil.Error:  # NoSuchProcess + AccessDenied + ZombieProcess
                                            print("Process does not exist.")

                                    c2p[c].terminate()
                                    c2time_nonActive[c] = None
                                    c2p[c] = None
                                    continue

                                else:
                                    c_active = c + 0

                        if c_active != -1:
                            if n_iter % 1 == 0:
                                #print('Process alive', c2p[c_active])
                                try:
                                    process = psutil.Process(c2p[c_active].pid)
                                    #print(f"Process status: {process.status()}")
                                    #print(f"Process is running: {process.is_running()}")
                                    if process.status() == 'zombie' or process.status() == 'sleeping':
                                        if time.time() - c2time_nonActive[c_active] > 100:
                                            print('joining Zombie/sleepping process')
                                            ## c2p[c_active].join() #a veces hace que se eternice
                                            c2p[c_active].terminate()
                                            c2p[c_active] = None
                                            failed_elements.append(c2file[c_active])
                                            c2time_nonActive[c_active] = time.time()

                                except psutil.Error:  # NoSuchProcess + AccessDenied + ZombieProcess
                                    print("Process does not exist.")

                        if c_core != -1:
                            break


                    print('Doing sample', f_, f_x, len(all_to_do_tile_reg), 'Starting pair ', pair, pairx, '/',
                          len(tiles2posis), 'In core', c_core)
                    p = Process(target= overlapping_func,  args=(slide_, scene_, pair, r01, r02,))
                    p.start()
                    c2p[c_core] = p
                    c2file[c_core] = pair
                    c2time_nonActive[c_core] = time.time()
                    continue


            while True:
                for c in c2p:
                    if type(c2p[c]) == type(None):
                        c2time_nonActive[c] = time.time()
                        continue
                    try:
                        process = psutil.Process(c2p[c].pid)
                        if process.status() == 'running':
                            c2time_nonActive[c] = time.time()
                    except:
                        pass
                c_core = -1
                do_break = True
                print('Not None processes', len([c for c in c2p if type(c2p[c]) != type(None)]), len(c2p))
                all_s = []
                for c in c2p:
                    if type(c2p[c]) != type(None):
                        try:
                            all_s.append(psutil.Process(c2p[c].pid).status())
                        except:
                            continue

                time.sleep(1)
                counter = Counter(all_s)
                for element, count in counter.items():
                    print(f"{element}: {count}")
                for c in c2p:
                    if type(c2p[c]) == type(None):
                        continue
                    elif c2p[c].is_alive() == True:
                        f_temp = os.path.join(output_folder, f_, 'QC', c2file[c] + '_done.json')
                        if os.path.isfile(f_temp) == True:
                            try:
                                time.sleep(2)
                                json_temp = json.load(open(f_temp, 'r'))
                                print('Process alive but to be stopped', c2p[c])
                                #
                                c_core = c + 0


                                try:
                                    process = psutil.Process(c2p[c].pid)
                                    print(f"Process status: {process.status()}")
                                    print(f"Process is running: {process.is_running()}")
                                except psutil.Error:  # NoSuchProcess + AccessDenied + ZombieProcess
                                    print("Process does not exist.")

                                c2p[c].terminate()
                                c2p[c] = None
                                c2time_nonActive[c] = time.time()
                                continue
                            except Exception as e:
                                print('Error loading checker file', f_temp)
                                print(e)
                                continue
                        else:
                            try:
                                process = psutil.Process(c2p[c].pid)
                                print(f"Process status: {process.status()}")
                                print(f"Process is running: {process.is_running()}")
                                if process.status() == 'zombie' or process.status() == 'sleeping':
                                    if time.time() - c2time_nonActive[c] > 100:
                                        print('Killing Zoombie/sleepping process')
                                        #c2p[c].join()
                                        c2p[c].terminate()
                                        c2p[c] = None
                                        failed_elements.append(c2file[c])
                                        c2time_nonActive[c] = time.time()

                            except psutil.Error:  # NoSuchProcess + AccessDenied + ZombieProcess
                                print("THIS SHOULD NOT HAPPEN!!!! Process does not exist.")
                        do_break = False
                        break
                    else:
                        f_temp = os.path.join(output_folder, f_, 'QC', c2file[c] + '_done.json')
                        if os.path.isfile(f_temp) == False:
                            failed_elements.append(c2file[c])
                        c2p[c] = None

                if do_break == True:
                    print('Done all cores')
                    break

            for pairx, pair in enumerate(failed_elements): #PARALELIZAR ESTE BUCLE!
                if do_progress == True:
                    ws = aux_func.send_task_evolution(ws, int(x/len(failed_elements) * 1000) / 10 , ind_, server_id)
                print('RE - Doing sample', f_, f_x, len(all_to_do_tile_reg), 'Starting pair ', pair, pairx, '/',
                      len(failed_elements), 'In core', c_core)
                try:
                    overlapping_func(slide_, scene_, pair, r01, r02)
                except Exception as e:
                    print('**********\n' *5)
                    print('Error in Re-Getting final overlap information')
                    print(str(e))
                    print('**********\n'*5)




    # Item 5: record provenance
    # Phase-3 profiling: aggregate the per-invocation AlignQC subprocess timings.
    # This quantifies how much of step 2 is repeated model loading vs inference --
    # the data behind the "reload the model per pair" optimization decision.
    _consensus_profile = None
    try:
        _timing_csv = os.path.join(output_folder, 'test_for_consen', '_consensus_timing.csv')
        if os.path.exists(_timing_csv):
            _loads, _infers = [], []
            for _line in open(_timing_csv):
                _p = _line.strip().split(',')
                if len(_p) >= 2:
                    _loads.append(float(_p[0])); _infers.append(float(_p[1]))
            if _loads:
                _consensus_profile = {
                    "subprocess_calls": len(_loads),
                    "model_load_sec_total": round(sum(_loads), 1),
                    "model_load_sec_mean": round(sum(_loads) / len(_loads), 2),
                    "inference_sec_total": round(sum(_infers), 1),
                    "model_load_fraction": round(sum(_loads) / max(1e-9, sum(_loads) + sum(_infers)), 3),
                }
    except Exception:
        _consensus_profile = None

    # Phase-3 profiling (cascade design): walk the per-pair method2ia_red_*.json
    # files and write a single tidy CSV with one row per (pair, method) capturing
    # method name, AlignQC score, and AlignQC scoring time. This is the data we
    # need to choose method ordering and a threshold for the cascade heuristic.
    # The current consensus run still happens (all methods, voted) -- this is
    # pure data collection on the existing pipeline.
    _cascade_csv = None
    try:
        import csv
        _consen_root = os.path.join(output_folder, 'test_for_consen')
        if os.path.isdir(_consen_root):
            _cascade_csv = os.path.join(output_folder, 'cascade_analysis.csv')
            _rows = 0
            with open(_cascade_csv, 'w', newline='') as _cf:
                _w = csv.writer(_cf)
                _w.writerow(["pair", "method", "score", "score_time_sec", "json_file"])
                for _pair_dir in sorted(os.listdir(_consen_root)):
                    _pd = os.path.join(_consen_root, _pair_dir)
                    if not os.path.isdir(_pd):
                        continue
                    for _fn in sorted(os.listdir(_pd)):
                        if not (_fn.startswith("method2ia_red_") and _fn.endswith(".json")):
                            continue
                        try:
                            _data = json.load(open(os.path.join(_pd, _fn)))
                        except Exception:
                            continue
                        for _m, _rec in _data.items():
                            _score = _rec.get("score")
                            _st = _rec.get("score_time_sec")
                            _w.writerow([_pair_dir, _m, _score, _st, _fn])
                            _rows += 1
            if _rows == 0:
                os.remove(_cascade_csv); _cascade_csv = None
            else:
                print(f"  cascade analysis: {_rows} (pair, method) rows -> {_cascade_csv}")
    except Exception as _e:
        _cascade_csv = None

    _rm = {
        "step": "2_register",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "reference_round": cfg.reference_round, "channel": channel, "n_cores": n_cores,
        "stages": {"naive_stitch": do_naive_stitch, "naive_registration": do_naive_registration,
                   "overlapping_tiles": do_overlapping_tiles, "tile_registration": do_tile_registration},
        "ai_consensus": do_ai_cons, "compression_factor": compr_fac, "eight_bit": do_8bit, "seed": seed,
        "inference_backend": inference_backend, "inference_backend_resolved": _resolved_backend,
        "consensus_workers": consensus_workers if _resolved_backend == "cpu_pool" else None,
        "scorer": _SCORER_NAME,
        "consensus": {"cluster_px": _CONSENSUS_CLUSTER_PX, "angle_threshold_deg": _ANGLE_THRESHOLD_DEG,
                      "priority_weight": _PRIORITY_WEIGHT, "min_overlap_area_frac": _MIN_OVERLAP_AREA_FRAC},
        "consensus_profile": _consensus_profile,
        "duration_sec": round(time.time() - _t_start, 1),
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "opencv": cv2.__version__},
    }
    with open(os.path.join(output_folder, "run_manifest_step2.json"), "w") as _fh:
        json.dump(_rm, _fh, indent=2, default=_json_safe)
    if _consensus_profile:
        print(f"  consensus profile: {_consensus_profile['subprocess_calls']} subprocess calls, "
              f"model-load {_consensus_profile['model_load_sec_total']}s total "
              f"({_consensus_profile['model_load_fraction']*100:.0f}% of consensus), "
              f"mean load {_consensus_profile['model_load_sec_mean']}s/call")
    print(f"  run manifest: {os.path.join(output_folder, 'run_manifest_step2.json')}")

    # Tear down the inference pool (no-op for the subprocess_per_pair backend).
    if _INFERENCE_SERVICE is not None:
        _INFERENCE_SERVICE.shutdown()
        _INFERENCE_SERVICE = None
