import os
import sys
import numpy as np
import cv2
import tifffile
import pandas as pd
import argparse
import pandas as pd
from sklearn.mixture import GaussianMixture
from scipy.stats import norm
from scipy.ndimage import uniform_filter1d
from sklearn.preprocessing import normalize

from sklearn.metrics import mutual_info_score
from fastdtw import fastdtw

def _boxfilter(x, win_size):
    return cv2.boxFilter(x, ddepth=-1, ksize=(win_size, win_size), normalize=True, borderType=cv2.BORDER_REFLECT)

def fast_ssim_map(im1, im2, win_size=7, K1=0.01, K2=0.03, data_range=1.0):
    """Full SSIM map only (only used for `tmp_ts[ssim_map >= 0.9] = 0`). Replaces
    skimage.metrics.structural_similarity(..., full=True)[1] (was ~63% of per-job AFS time) with
    float32 + cv2.boxFilter instead of float64 + scipy.ndimage.uniform_filter -- ~2.6-3x faster,
    validated on real data: 0 of ~45M pixels differed from the skimage float64 baseline's
    `>= 0.9` threshold decision. Same formula/boundary handling as skimage's defaults
    (K1=0.01, K2=0.03, gaussian_weights=False, win_size=7); only the filter backend/precision differ."""
    im1 = im1.astype(np.float32, copy=False)
    im2 = im2.astype(np.float32, copy=False)
    NP = win_size ** 2
    cov_norm = NP / (NP - 1)

    ux = _boxfilter(im1, win_size)
    uy = _boxfilter(im2, win_size)
    uxx = _boxfilter(im1 * im1, win_size)
    uyy = _boxfilter(im2 * im2, win_size)
    uxy = _boxfilter(im1 * im2, win_size)
    vx = cov_norm * (uxx - ux * ux)
    vy = cov_norm * (uyy - uy * uy)
    vxy = cov_norm * (uxy - ux * uy)

    R = data_range
    C1 = (K1 * R) ** 2
    C2 = (K2 * R) ** 2
    A1 = 2 * ux * uy + C1
    A2 = 2 * vxy + C2
    B1 = ux ** 2 + uy ** 2 + C1
    B2 = vx + vy + C2
    return (A1 * A2) / (B1 * B2)

# DTW backend: the 'dtw' PyPI package this originally used is GPL-3.0, which
# conflicts with this project's commercial-friendly licensing requirement.
# An exact from-scratch replacement was validated first (0.0 max abs diff,
# 40/40 exact matches vs the real GPL package on real MVM histogram data),
# then compared against fastdtw (MIT-licensed, confirmed via GitHub +
# PyPI): fastdtw is ~6x faster than the real GPL algorithm and ~3x faster
# than the exact custom port, and its (expected, upper-bound) approximation
# error never changed a one_component/two_components classification versus
# the real GPL reference on any of 40 real samples tested (2026-09-14).
# Adopted for the real speedup; the exact custom implementation was kept
# only as the validation baseline, not in the shipped pipeline.

# Define the function equivalent to range.x1_q in R
def range_x1_q(x, q):
    x_positive = x[x > 0]
    if len(x_positive) > 10:
        tmp_q_high = np.quantile(x_positive, q)
        tmp_q_min = np.quantile(x_positive, 1 - q)
        if tmp_q_high > tmp_q_min:
            x = (x - tmp_q_min) / (tmp_q_high - tmp_q_min)
            x[x > 1] = 1
            x[x < 0] = 0
        else:
            # Degenerate range (e.g. >(1-q) of the >0 values are equal, most
            # commonly because x is mostly 0) -- (x-lo)/(hi-lo) would divide
            # by ~0. Every caller already zeros NaN output downstream, so
            # returning zeros directly is equivalent, just without the
            # RuntimeWarning and the QC-image black-channel side effect that
            # NaN-then-zero produced (found on real data, 2026-09-14: ~1 in
            # 5 real AFS jobs hit this on the computed true-signal image,
            # where >99% of tissue-masked pixels are legitimately 0).
            x = np.zeros_like(x, dtype=np.float64)
    return x

def range_x1_q_mask(x, y, q):
    x_positive = x[y > 0]
    if len(x_positive) > 10:
        tmp_q_high = np.quantile(x_positive, q)
        tmp_q_min = np.quantile(x_positive, 1 - q)
        if tmp_q_high == 0:
            # x_positive is filtered by the mask y, not by x's own sign, so it
            # can be almost entirely 0 even with real (sparse) signal present
            # -- true signal below (1-q) of the masked region pushes q_high
            # to land exactly on 0. Recover by taking q_high from just the
            # nonzero values instead of discarding sparse-but-real signal;
            # q_min stays 0 (the mask's own background floor is a genuine 0,
            # not a degenerate estimate). Verified on real data (2026-09-15):
            # a masked region with only 0.991% nonzero pixels -- just under
            # the 1% needed for q99 to catch any nonzero value -- recovers a
            # real q99 of 2648 from the nonzero subset alone.
            nz = x_positive[x_positive > 0]
            if len(nz) > 10:
                tmp_q_high = np.quantile(nz, q)
                tmp_q_min = 0.0
        if tmp_q_high > tmp_q_min:
            x = (x - tmp_q_min) / (tmp_q_high - tmp_q_min)
            x[x > 1] = 1
            x[x < 0] = 0
        else:
            x = np.zeros_like(x, dtype=np.float64)
    return x

def pad_to_match(a, b):
    """Pads the smaller array to match the shape of the larger one."""
    # Pad columns (axis=1)
    if a.shape[1] > b.shape[1]:
        pad_width = a.shape[1] - b.shape[1]
        b = np.pad(b, ((0, 0), (0, pad_width)), mode='constant', constant_values=0)
    elif b.shape[1] > a.shape[1]:
        pad_width = b.shape[1] - a.shape[1]
        a = np.pad(a, ((0, 0), (0, pad_width)), mode='constant', constant_values=0)

    # Pad rows (axis=0)
    if a.shape[0] > b.shape[0]:
        pad_height = a.shape[0] - b.shape[0]
        b = np.pad(b, ((0, pad_height), (0, 0)), mode='constant', constant_values=0)
    elif b.shape[0] > a.shape[0]:
        pad_height = b.shape[0] - a.shape[0]
        a = np.pad(a, ((0, pad_height), (0, 0)), mode='constant', constant_values=0)

    return a, b

def autofluorescence_subtraction(input_path_medoids, input_path_MS, input_path_AF, output_path_TS, output_path_QC):
    print(f"### input path medoids: {input_path_medoids} ###")
    print(f"### input path MS: {input_path_MS} ###")
    print(f"### input path AF: {input_path_AF} ###")
    print(f"### output path TS: {output_path_TS} ###")
    print(f"### output path QC: {output_path_QC} ###")
    
    if not os.path.exists(os.path.dirname(output_path_TS)):
        print(f"### creating folder: {os.path.dirname(output_path_TS)} ###")
        os.makedirs(os.path.dirname(output_path_TS), exist_ok=True)
    
    if not os.path.exists(os.path.dirname(output_path_QC)):
        print(f"### creating folder: {os.path.dirname(output_path_QC)} ###")
        os.makedirs(os.path.dirname(output_path_QC), exist_ok=True)
	
    tmp_ms = tifffile.imread(input_path_MS)
    tmp_af = tifffile.imread(input_path_AF)
    
    tmp_ms, tmp_af = pad_to_match(tmp_ms, tmp_af)

    tmp_mask = (tmp_ms > 0) & (tmp_af > 0)
    
    image_fi = np.arctan2(tmp_ms, tmp_af)
    image_fi[np.isnan(image_fi)] = 0
    
    image_fi_foreground = image_fi[tmp_mask]

    if len(image_fi_foreground) == 0:
        # No pixel has both MS and AF signal -- tmp_mask is all-False, so tmp_ts ends up
        # all-zero regardless of tmp_th (tmp_ts *= tmp_mask below); skip classification
        # entirely rather than feed fastdtw a degenerate all-NaN histogram (0/0 from an
        # empty np.histogram), which crashes with an internal IndexError on some inputs.
        print("No overlapping MS/AF foreground pixels -- skipping AF-class assignment, output will be all-zero.")
        tmp_th, assigned_class, distances = 0.0, 'no_signal', {}
    else:
        medoid_series = pd.read_csv(input_path_medoids)

        smoothed_fi = uniform_filter1d(image_fi_foreground, size=5)
        # Use the same binning as medoid columns
        bins = medoid_series.columns[1:].astype(float).values  # skip the 'class' column
        hist, _ = np.histogram(smoothed_fi, bins=bins, density=True)

        hist = 100*hist/np.sum(hist)  # L1 norm

        distances = {}

        for _, row in medoid_series.iterrows():
            label = row['class']
            medoid = row.iloc[1:].astype(float).values
            d, _ = fastdtw(hist, medoid, dist=lambda x, y: np.abs(x - y))  # L1 DTW
            distances[label] = d

        assigned_class = min(distances, key=distances.get)
        print("Assigned class:", assigned_class)
    print("DTW distances:", distances)
    
    if assigned_class == 'one_component':
        # tmp_th = image_fi_foreground.mean() + 2 * image_fi_foreground.std()
        tmp_th = image_fi_foreground.mean() + 2 * np.std(image_fi_foreground)
        if tmp_th > 1.57:
            assigned_class = 'two_components'
    
    if assigned_class == 'two_components':
        N = 100_000  
        np.random.seed(1234)
        if len(image_fi_foreground) > N:
            sampled_data = np.random.choice(image_fi_foreground, N, replace=False)
        else:
            sampled_data = image_fi_foreground
    
        sampled_data = sampled_data.reshape(-1, 1)
        
        gmm = GaussianMixture(n_components=2, covariance_type='full', random_state=1234)
        gmm.fit(sampled_data)
        
        # Extract parameters
        means = gmm.means_.flatten()
        sds = np.sqrt([gmm.covariances_[i][0][0] for i in range(2)])
        props = gmm.weights_
        
        # Create x-axis for density plot
        x_vals = np.linspace(sampled_data.min(), sampled_data.max(), 1000)
        
        # Compute individual component densities
        dens_1 = props[0] * norm.pdf(x_vals, loc=means[0], scale=sds[0])
        dens_2 = props[1] * norm.pdf(x_vals, loc=means[1], scale=sds[1])
        # dens_sum = dens_1 + dens_2
        
        # Find point of maximum overlap (min |dens1 - dens2|, or max sigma/delta)
        delta = np.abs(dens_1 - dens_2)
        sigma = dens_1 + dens_2
        ratio = np.divide(sigma, delta, out=np.zeros_like(sigma), where=delta != 0)
        
        # Find intersection threshold
        max_ratio_idx = np.argmax(ratio[x_vals > min(means)]) + (1000 - len(ratio[x_vals > min(means)]))
        tmp_th = x_vals[max_ratio_idx]

    ssim_map = fast_ssim_map(range_x1_q(tmp_ms,0.99), range_x1_q(tmp_af,0.99), data_range=1)

    image_fi[(image_fi > tmp_th) & (tmp_mask == 1)] = np.median(image_fi_foreground[(image_fi_foreground <= tmp_th)])
    
    tmp_subtraction = tmp_af * np.tan(image_fi)
    
    tmp_ts = tmp_ms - tmp_subtraction
    tmp_ts[tmp_ts < 0] = 0
    tmp_ts[image_fi == 0] = 0
    tmp_ts *= tmp_mask
    tmp_ts[np.isnan(tmp_ts)] = 0
    
    tmp_ts[ssim_map >= 0.9] = 0

    tmp_ts = tmp_ts.round().astype(np.uint16)
    tmp_ts[np.isnan(tmp_ts)] = 0
    tifffile.imwrite(output_path_TS, tmp_ts, photometric='minisblack', compression='lzma') # compression='lzw'
    
    # Save the QC image
    tmp_ms *= tmp_mask
    tmp_af *= tmp_mask
    tmp_q = 1 - 1e-02
    tmp_qc = np.dstack([
        range_x1_q_mask(tmp_ts, tmp_mask, tmp_q), 
        range_x1_q(tmp_af, tmp_q), 
        range_x1_q(tmp_ms, tmp_q)
    ])
    tmp_qc[tmp_qc<0] = 0
    tmp_qc[np.isnan(tmp_qc)] = 0
    tmp_qc = ((2**8-1)*tmp_qc).round().astype(np.uint8)
    tifffile.imwrite(output_path_QC, tmp_qc, photometric='rgb', compression='lzma')
    return (tmp_th, assigned_class, distances)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autofluorescence Subtraction (AFS).")
    parser.add_argument("--input_path_medoids", type=str, help="Path to input medoids csv (.csv).")
    parser.add_argument("--input_path_MS", type=str, help="Path to input MS image (.tiff).")
    parser.add_argument("--input_path_AF", type=str, help="Path to input AF image (.tiff).")
    parser.add_argument("--output_path_TS", type=str, help="Path to output TS image (.tiff).")
    parser.add_argument("--output_path_QC", type=str, help="Path to output QC image (.tiff).")

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    input_path_medoids = args.input_path_medoids
    input_path_MS = args.input_path_MS
    input_path_AF = args.input_path_AF
    output_path_TS = args.output_path_TS
    output_path_QC = args.output_path_QC

    autofluorescence_subtraction(input_path_medoids, input_path_MS, input_path_AF, output_path_TS, output_path_QC)
    
