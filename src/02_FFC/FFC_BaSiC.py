from basicpy import BaSiC
from basicpy import datasets as bdata
import sys
import numpy as np
import pandas as pd
import os
#from tifffile import imsave, imread, imwrite
from tifffile import imread, imwrite
import argparse
import imagecodecs
import torch
import matplotlib.pyplot as plt
import seaborn as sns
from concurrent.futures import ThreadPoolExecutor
from matplotlib.colors import TwoSlopeNorm, LinearSegmentedColormap

def _write_tile(out_path_corr, filename, image):
    if not np.isfinite(image).all():
        raise ValueError(f"Non-finite FFC intensities in {filename}")
    image = np.clip(image, 0, 65535).astype(np.uint16)
    imwrite(os.path.join(out_path_corr, filename), image, photometric="minisblack", dtype="uint16", compression="lzma",)

def RunBasic(in_path, channel, out_path_corr, out_path_templates, skip_existing=False, device="none", n_fit_images=100, seed=1234, n_write_workers=4):
    """Do the FFC using BaSiC, fitting on a tile sample and writing corrected tiles in parallel."""

    # Check if the output directories exist and create them if they do not
    if not os.path.isdir(out_path_corr):
        os.makedirs(out_path_corr)

    if not os.path.isdir(out_path_templates):
        os.makedirs(out_path_templates)

    # Proceed if the input directory and output directories exist
    if (os.path.isdir(in_path) and os.path.isdir(out_path_templates) and os.path.isdir(out_path_corr)):
        # Create list of names of images to load (one channel)
        names = os.listdir(in_path)
        filtered_names = [i for i in names if "_" + channel + ".tiff" in i and i[0] != "."]

        if channel == "FITC":
            filtered_names = [i for i in filtered_names if "_AF_FITC.tiff" not in i and i[0] != "."]

        file_paths = [os.path.join(in_path, file_name) for file_name in filtered_names]

        output_paths = [os.path.join(out_path_corr, file_name) for file_name in filtered_names]
        n_files = [file for file in output_paths if os.path.exists(file)]

        if len(n_files) == len(output_paths):
            return

        # Read the images
        images = [imread(file_path) for file_path in file_paths]  # Ensure imread is used in a loop if it does not support list input
        images = np.stack(images, axis=0)

        print("Num GPUs Available: ", torch.cuda.device_count())

        # Fit on a random subset of tiles, then apply the correction to every tile.
        rng = np.random.default_rng(seed)
        fit_idx = rng.choice(len(images), size=min(n_fit_images, len(images)), replace=False)
        fit_images = images[fit_idx]

        # Compute the transformation matrices
        # basic = BaSiC(get_darkfield=True, smoothness_flatfield=1)
        print(f"BaSiC device requested: {device}; fitting on {len(fit_images)}/{len(images)} tiles")
        basic = BaSiC(device=device)
        gpu_error_markers = ("cuda", "cusolver", "cublas", "cudnn", "cufft", "out of memory")
        try:
            basic.fit(fit_images)  # Apply the BaSiC algorithm to fit the model to the images
        except RuntimeError as exc:
            if basic.device != "cpu" and any(marker in str(exc).lower() for marker in gpu_error_markers):
                print(f"### GPU error during BaSiC fit ({exc}); falling back to CPU ###")
                basic = BaSiC(device="cpu")
                basic.fit(fit_images)
            else:
                raise
        print(f"BaSiC device used: {basic.device}")

        # Retrieve the computed fields
        flatfield = basic.flatfield
        darkfield = basic.darkfield
        baseline = basic.baseline

        # Apply the transformation
        images = basic.transform(images)

        # Keep floating-point correction values until _write_tile clips and
        # converts each tile to unsigned 16-bit. Casting first would wrap.

        # Create a custom divergent colormap
        colors = ["indianred", "white", "dodgerblue"]
        n_bins = 100  # More bins will give you a smoother transition
        cmap_name = "custom1"
        cm = LinearSegmentedColormap.from_list(cmap_name, colors, N=n_bins)

        # Save computations
        np.save(os.path.join(out_path_templates, channel + "_flatfield.npy"), flatfield)
        np.save(os.path.join(out_path_templates, channel + "_darkfield.npy"), darkfield)
        np.save(os.path.join(out_path_templates, channel + "_baseline.npy"), baseline)

        epsilon = 1 * 10 ** (-3)
        # Create a figure with two subplots (1 row, 2 columns)
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 8))
        if flatfield.min() > 1:
            norm = TwoSlopeNorm(vmin=flatfield.min() - epsilon, vcenter=flatfield.mean(), vmax=flatfield.max() + epsilon,)
        else:
            norm = TwoSlopeNorm(vmin=flatfield.min() - epsilon, vcenter=1, vmax=flatfield.max() + epsilon,)

        sns_heatmap1 = sns.heatmap(flatfield, cmap=cm, norm=norm, ax=ax1)
        ax1.set_title("Flatfield")
        ax1.set_xticks([])
        ax1.set_yticks([])

        # Plot the second heatmap
        if darkfield.min() > 0:
            norm2 = TwoSlopeNorm(vmin=darkfield.min() - epsilon, vcenter=darkfield.mean(), vmax=darkfield.max() + epsilon,)
        else:
            norm2 = TwoSlopeNorm(vmin=darkfield.min() - epsilon, vcenter=0, vmax=darkfield.max() + epsilon,)

        sns_heatmap2 = sns.heatmap(darkfield, cmap=cm, norm=norm2, ax=ax2)
        ax2.set_title("Darkfield")
        ax2.set_xticks([])
        ax2.set_yticks([])

        # Display the plot
        plt.tight_layout()  # Adjust subplots to fit into figure area.
        plt.savefig(os.path.join(out_path_templates, channel + "_qcplot.png"), dpi=300)  # Save the figure to a file
        plt.close()  # Close the plot

        with ThreadPoolExecutor(max_workers=n_write_workers) as pool:
            futures = [
                pool.submit(_write_tile, out_path_corr, filtered_names[i], images[i])
                for i in range(len(images))
            ]
            for future in futures:
                future.result()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flat Field Correction with BaSiC")
    parser.add_argument("--in_path", help="path to input images, example: /path/to/project_directory/output_tiles_tiffs/BM_R00_V01_BENCHMARK_ND", type=str)
    parser.add_argument(
        "--channel",
        help="the channel we want to correct: e.g. AF_FIT, Cy5, DAPI, FITC or TRITC",
        type=str,
    )
    parser.add_argument(
        "--out_path_corr", help="path to corrected images, example: /path/to/project_directory/output_FFC_corrected/BM_R00_V01_BENCHMARK_ND", type=str
    )
    parser.add_argument(
        "--out_path_templates",
        help="path to templates, i.e. the transformation matrices, example: /path/to/project_directory/output_FFC_templates/BM_R00_V01_BENCHMARK_ND",
        type=str,
    )
    parser.add_argument(
        "--device",
        help="'cuda', 'cpu', or 'none' (auto-detect: cuda if available, else cpu). Falls back to cpu if cuda fails at runtime. Default: none",
        type=str,
        default="none",
        choices=["cuda", "cpu", "none"],
    )
    parser.add_argument(
        "--n_fit_images",
        help="max tiles randomly sampled to fit the model. Default: 100",
        type=int,
        default=100,
    )
    parser.add_argument(
        "--seed",
        help="random seed for the tile sample. Default: 1234",
        type=int,
        default=1234,
    )
    parser.add_argument(
        "--n_write_workers",
        help="threads used to write corrected tiles concurrently. Default: 4",
        type=int,
        default=4,
    )

    # If no arguments are provided, show help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    in_path = args.in_path
    channel = args.channel
    out_path_corr = args.out_path_corr
    out_path_templates = args.out_path_templates

    RunBasic(
        in_path=in_path,
        channel=channel,
        out_path_corr=out_path_corr,
        out_path_templates=out_path_templates,
        device=args.device,
        n_fit_images=args.n_fit_images,
        seed=args.seed,
        n_write_workers=args.n_write_workers,
    )
