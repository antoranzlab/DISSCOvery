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
import tensorflow as tf
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.colors import TwoSlopeNorm, LinearSegmentedColormap

def RunBasic(in_path, channel, out_path_corr, out_path_templates, skip_existing=False):
    """Do the FFC using BaSiC"""

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

        # Check for GPU availability

        print("Num GPUs Available: ", len(tf.config.experimental.list_physical_devices("GPU")),)

        # Compute the transformation matrices
        # basic = BaSiC(get_darkfield=True, smoothness_flatfield=1)
        basic = BaSiC() 
        basic.fit(images)  # Apply the BaSiC algorithm to fit the model to the images

        # Retrieve the computed fields
        flatfield = basic.flatfield
        darkfield = basic.darkfield
        baseline = basic.baseline

        # Apply the transformation
        images = basic.transform(images)

        # Convert images to int16, trimming all values above 65535 to 65535
        images = images.astype(np.uint16)
        # images = np.clip(images, a_min=0, a_max=np.power(2, 16) - 1)

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

        for i in range(0, len(images)):
            imwrite(os.path.join(out_path_corr, filtered_names[i]), images[i].astype(np.uint16), photometric="minisblack", dtype="uint16", compression="lzma",)


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
    )
