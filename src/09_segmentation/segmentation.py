# -*- coding: utf-8 -*-
"""
Created on Tue Feb  9 10:49:02 2021

@author: u0132399
"""
import sys
from csbdeep.utils import normalize
import skimage
from tqdm import tqdm
import math
import numpy as np
import cv2
from scipy import ndimage
import argparse
import tifffile as tiff
from tifffile import imread, imwrite
import os

np.random.seed(6)
n_threads = 1
os.environ['OMP_NUM_THREADS'] = str(n_threads)

def contour_finder(image,label):
    output = skimage.segmentation.find_boundaries(label)   
    image = cv2.convertScaleAbs(image,alpha=(255.0/65535.0))
    org_rgb = cv2.cvtColor(image,cv2.COLOR_GRAY2RGB)
    org_rgb[output==1]=[255,255,0]
    return org_rgb

def marginal_object_removal(label_matrix):
    z_tile = np.ones(np.shape(label_matrix)).astype(dtype='int32')
    z_tile[3:-3,3:-3]=0
    z_tile_new = z_tile*label_matrix
    g = np.unique(z_tile_new)
    INT = np.isin(label_matrix,g)
    label_matrix[INT] = 0
     
    return label_matrix

def label_adjust(max_old, label):
    temp = label
    new_label = label + max_old
    new_label[temp==0]=0
    return new_label

def split(img, window_size, margin):

    sh = list(img.shape)
    sh[0], sh[1] = sh[0] + margin * 2, sh[1] + margin * 2
    img_ = np.zeros(shape=sh).astype(dtype='uint16')
    img_[margin:-margin, margin:-margin] = img

    stride = window_size
    step = window_size + 2 * margin

    nrows, ncols = img.shape[0] // window_size, img.shape[1] // window_size
    splitted = []
    
    for i in range(nrows):
        for j in range(ncols):
            h_start = j*stride
            v_start = i*stride
            cropped = img_[v_start:v_start+step, h_start:h_start+step]
            splitted.append(cropped)
            
    return splitted,img_

def segment(path_image, path_model, model_name, path_output, qc_path, PP=False):
# def segment(PATH_2_IMG, model, PATH_2_OUTPUT, QC_PATH, PP=False):
    #Loading the model:
    if model_name == 'stardist':
        import tensorflow as tf
        from stardist.models import StarDist2D
        print("Num GPUs Available: ", len(tf.config.list_physical_devices('GPU')))
        print("GPUs: ", tf.config.list_physical_devices('GPU'))
        model = StarDist2D(None, name=model_name, basedir= path_model)
    elif model_name == 'cellpose':
        from cellpose import models
        model = models.CellposeModel(gpu=True, pretrained_model=os.path.join(path_model, model_name))
    
    img_org = tiff.imread(path_image)
    img_org = img_org.astype(np.uint16)
    if PP == True:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))  #Define tile size and clip limit. 
        img_org = clahe.apply(img_org)
    
    img = np.array(img_org)
    window_size=460
    
    img_row=img.shape[0]
    img_col = img.shape[1]
    
    row= math.ceil(img_row/window_size)
    col = math.ceil(img_col/window_size)
    
    img_Big = np.zeros((row*window_size,col*window_size)).astype(dtype='uint16')
    margin_row = math.floor((np.size(img_Big,0) - img_row)/2)
    margin_col = math.floor((np.size(img_Big,1) - img_col)/2)
    img_small = img
    img_Big[margin_row:margin_row+ np.size(img_small,0), margin_col:margin_col+ np.size(img_small,1)]= img_small;
    window_size=460
    margin=26
    out,img_ = split(img_Big, window_size=460, margin=26)
    img_big = img_

    z = np.zeros((np.shape(img_big))).astype(dtype = 'int32')
    X = out
    n_channel = 1 if X[0].ndim == 2 else X[0].shape[-1]
    axis_norm = (0,1)   # normalize channels independently

    X = [normalize(x,1,99.8,axis=axis_norm) for x in tqdm(X)]
    stride = 460
    step = 512
    r_ind =[]
    c_ind = []
    l= []
    for f in range(col):
        l.append(f)
    
    c_ind = l*row

    max_old = [0]
    for k in tqdm(range(len(X))):
        im = normalize(X[k], 1,99.8, axis=axis_norm)
        if model_name == 'stardist':
            labels, details = model.predict_instances(im)
        elif model_name == 'cellpose':
            result = model.eval(img, diameter=None, channels=[0, 0])
            labels, flows, styles, diams = result
            print("done")
    
        r_ind.append(math.floor(k/col))
        p = marginal_object_removal(labels)
        p = label_adjust(max(max_old), p)
     
        h_start = r_ind[k]*(stride)
        v_start = c_ind[k]*(stride) 
        z_check = z[h_start:h_start+step, v_start:v_start+step]
        fuk = np.copy(z_check)
        fuk[z_check!=0] = 1
        inter = np.unique(fuk*p)
        intersection = np.isin(p,inter)
        p[intersection] = 0
        p = p + z_check
        z[h_start:h_start+step, v_start:v_start+step]= p
        max_old.append(np.max(p))
        
    K = z 
    
    img_small = img
    margin_row = margin_row+ margin 
    margin_col = margin_col + margin
    z_ = K[margin_row:margin_row+ np.size(img_small,0), margin_col:margin_col+ np.size(img_small,1)]
    np.save(path_output,z_)

    contours = contour_finder(img, z_)
    
    imwrite(qc_path,contours)

#print(max_old)    

def str2bool(v):
    return v.lower() in ('yes', 'true', 't', '1')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Segmentation. type segmentation.py -h for positional and optional inputs description')
    parser.add_argument('--path_to_the_image', type=str,
                        help=' Path to the input image (.tiff). Example: /path/to/project_directory/output_registration/BM_R01_V01_BENCHMARK_S0/BM_R01_V02_BENCHMARK_ND_S0_DAPI.tiff')
    parser.add_argument('--path_to_the_models', type=str,
                        help=' Path to the models (dir). Example: models/06_stardist/')
    parser.add_argument('--model_name', type=str,
                        help=' Model you want to use (str). Example: stardist')
    parser.add_argument('--output_path', type=str,
                        help=' Path for the labeled matrix (dir). Example: /path/to/project_directory/output_segmentation/Matrix/BM_R01_V01_BENCHMARK_S0/BM_R01_V02_BENCHMARK_ND_S0_DAPI.npy ')
    parser.add_argument('--QC_path', type=str,
                        help=' Path for the QC image (dir). Example: /path/to/project_directory/output_segmentation/QC/BM/BM_R01_V02_BENCHMARK_ND_S0_DAPI.tiff ')
    parser.add_argument('--PP', type=str2bool,
                        help=' Preprocessing indicator (boolean). Example: True')

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    # full path to the czi file
    input_path_image= args.path_to_the_image
    input_path_model = args.path_to_the_models
    model_name = args.model_name
    output_path_matrix = args.output_path
    output_path_qc = args.QC_path
    pp = args.PP

    segment(path_image=input_path_image, path_model= input_path_model, model_name= model_name, path_output=output_path_matrix, qc_path=output_path_qc, PP=False)
