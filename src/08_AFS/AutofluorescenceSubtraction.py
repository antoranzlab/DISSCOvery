import os
import sys
import numpy as np
import tifffile
import pandas as pd
import argparse
import pandas as pd
from sklearn.mixture import GaussianMixture
from scipy.stats import norm
from dtw import dtw
from scipy.ndimage import uniform_filter1d
from sklearn.preprocessing import normalize
    
from sklearn.metrics import mutual_info_score
from skimage.metrics import structural_similarity as ssim

# Define the function equivalent to range.x1_q in R
def range_x1_q(x, q):
    x_positive = x[x > 0]
    if len(x_positive) > 10:
        tmp_q_high = np.quantile(x_positive, q)
        tmp_q_min = np.quantile(x_positive, 1 - q)
        x = (x - tmp_q_min) / (tmp_q_high - tmp_q_min)
        x[x > 1] = 1
        x[x < 0] = 0
    return x

def range_x1_q_mask(x, y, q):
    x_positive = x[y > 0]
    if len(x_positive) > 10:
        tmp_q_high = np.quantile(x_positive, q)
        tmp_q_min = np.quantile(x_positive, 1 - q)
        x = (x - tmp_q_min) / (tmp_q_high - tmp_q_min)
        x[x > 1] = 1
        x[x < 0] = 0
    return x

def range_x1_q_mask(x, y, q):
    x_positive = x[y > 0]
    if len(x_positive) > 10:
        tmp_q_high = np.quantile(x_positive, q)
        tmp_q_min = np.quantile(x_positive, 1 - q)
        x = (x - tmp_q_min) / (tmp_q_high - tmp_q_min)
        x[x > 1] = 1
        x[x < 0] = 0
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
        d, _, _, _ = dtw(hist, medoid, dist=lambda x, y: np.abs(x - y))  # L1 DTW
        distances[label] = d
    
    assigned_class = min(distances, key=distances.get)
    print("Assigned class:", assigned_class)
    print("DTW distances:", distances)
    
    if assigned_class == 'one_component':
        tmp_th = image_fi_foreground.mean() + 2 * image_fi_foreground.std()
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

    ssim_val, ssim_map = ssim(range_x1_q(tmp_ms,0.99), range_x1_q(tmp_af,0.99), data_range=1, full=True)

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