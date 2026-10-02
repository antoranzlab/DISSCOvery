import os
import shutil
import torch
import numpy as np
import tifffile
from tqdm import tqdm
from torch.utils.data import Dataset, DataLoader
from segmentation_models_pytorch import UnetPlusPlus
from PIL import Image
from pathlib import Path
import argparse
import sys

# ===============================================
# Load OME-TIFF helper
# ===============================================
def load_ome_tiff_2d(path, series=0, level=0, channel=None, z=None):
    import numpy as np
    import tifffile as tf

    with tf.TiffFile(path) as tif:
        s = tif.series[series]
        arr = s.levels[level].asarray()
        axes = s.axes

    ax = {a: i for i, a in enumerate(axes)}

    if 'Z' in ax:
        z = 0 if z is None else z
        arr = np.take(arr, z, axis=ax['Z'])
        axes = axes.replace('Z', '')

    if 'C' in ax:
        channel = 0 if channel is None else channel
        arr = np.take(arr, channel, axis=ax['C'])
        axes = axes.replace('C', '')

    arr = np.squeeze(arr)

    if arr.dtype == np.uint16:
        arr = (arr >> 8).astype(np.uint8)
    elif arr.dtype != np.uint8:
        arr = arr.astype(np.uint8)

    return arr


# ===============================================
# CONFIG
# ===============================================
# input_folder = "/home/luna.kuleuven.be/u0172795/Documents/DISSCOvery/test_MILAN_revission/hard_stitching_QC"
# output_folder = "/media/Share1/Kinga/DISSCOvery_related/DISSCOvery_tests/output_QUALIFAI"
# model_path = "/media/Share1/Kinga/DISSCOvery_related/05_models/05_unetpp_best_117.pth"

parser = argparse.ArgumentParser(description='QC - QUALIFAI. Type QUALIFAI.py -h for positional and optional inputs description')
parser.add_argument('--input_image_path', type=str,
                    help=' full path to the file containing the hard stitched image file in full resolution, e.g. /path/to/project_directory/hard_stitching_full_res')
parser.add_argument('--output_image_path', type=str,
                    help='full path to the file where the STS masks will be saved, e.g. path/to/project_directory/output_QC/subfolder_name/image_name.tiff')
parser.add_argument('--model_path', type=str,
                    help='full path to where the model is saved, e.g. models/03_unetpp_best.pth')


# If no arguments are provided, show help and exit
if len(sys.argv) == 1:
    parser.print_help(sys.stderr)
    sys.exit(1)

args = parser.parse_args()

input_folder = args.input_image_path
output_folder = args.output_image_path
model_path = args.model_path


os.makedirs(output_folder, exist_ok=True)

tile_size = 256
stride = tile_size // 2       # 50% overlap
n_classes = 6
batch_size = 32

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ===============================================
# Hann Window
# ===============================================
def make_hann_window(sz: int) -> np.ndarray:
    h1 = np.hanning(sz).astype(np.float32)
    w2d = np.outer(h1, h1)
    w2d /= w2d.max()
    return w2d

w2d_base = make_hann_window(tile_size)


# ===============================================
# Tile Dataset
# ===============================================
class InferenceTileDataset(Dataset):
    def __init__(self, tile_dir):
        self.tile_paths = sorted(
            [os.path.join(tile_dir, f) for f in os.listdir(tile_dir)
             if f.lower().endswith((".tif", ".tiff"))]
        )

    def __len__(self):
        return len(self.tile_paths)

    def __getitem__(self, idx):
        img_path = self.tile_paths[idx]
        img = tifffile.imread(img_path)
        img = np.expand_dims(img, axis=0) / 255.0
        return torch.tensor(img, dtype=torch.float32), os.path.basename(img_path)


# ===============================================
# Load Model once
# ===============================================
model = UnetPlusPlus(
    encoder_name="resnet34",
    encoder_weights=None,
    in_channels=1,
    classes=n_classes
)
model.load_state_dict(torch.load(model_path, map_location=device))
model.to(device)
model.eval()

use_amp = (device.type == "cuda")


# ===============================================
# MAIN PROCESSING LOOP (recursive)
# ===============================================
folder = [d for root, dirs, files in os.walk(input_folder) for d in dirs]

for root, dirs, files in os.walk(input_folder, folder):
    for wsi_filename in sorted(files):
        if not wsi_filename.lower().endswith((".tif", ".tiff")):
            continue

        wsi_path = os.path.join(root, wsi_filename)
        base_name = os.path.splitext(wsi_filename)[0]

        # Mirror folder structure
        rel_path = os.path.relpath(root, input_folder)
        save_dir = os.path.join(output_folder, rel_path)
        os.makedirs(save_dir, exist_ok=True)

        output_mask_path = os.path.join(save_dir, base_name + ".tiff")

        # if os.path.exists(output_mask_path):
        #     print(f"Skipping {wsi_filename} (already processed).")
        #     continue

        print(f"\n=== Processing: {wsi_path}")

        # -------------------------------------------
        # Reset per-WSI temp folder and tile coords
        # -------------------------------------------
        temp_dir = f"temp_tiles_{base_name}"
        tile_img_dir = os.path.join(temp_dir, "images")
        os.makedirs(tile_img_dir, exist_ok=True)

        tile_coords = []
        tile_id = 0

        # -------------------------------------------
        # Load image
        # -------------------------------------------
        img = load_ome_tiff_2d(wsi_path, series=0, level=0, channel=0)
        H, W = img.shape

        # Padding
        pad_h = (-(H - tile_size) % stride) % stride
        pad_w = (-(W - tile_size) % stride) % stride
        if pad_h or pad_w:
            img = np.pad(img, ((0, pad_h), (0, pad_w)), mode="reflect")

        Hp, Wp = img.shape

        # -------------------------------------------
        # Make tiles
        # -------------------------------------------
        print("Tiling image...")
        for y in range(0, Hp - tile_size + 1, stride):
            for x in range(0, Wp - tile_size + 1, stride):
                tile = img[y:y+tile_size, x:x+tile_size]
                tile_name = f"tile_{tile_id:06d}.tiff"
                tifffile.imwrite(os.path.join(tile_img_dir, tile_name), tile)
                tile_coords.append((tile_name, y, x))
                tile_id += 1

        # -------------------------------------------
        # Predict tiles
        # -------------------------------------------
        print("Running inference...")

        dataset = InferenceTileDataset(tile_img_dir)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=4)

        sum_prob = np.zeros((Hp, Wp, n_classes), dtype=np.float32)
        sum_w    = np.zeros((Hp, Wp), dtype=np.float32)

        with torch.inference_mode():
            for imgs, filenames in tqdm(loader):
                imgs = imgs.to(device, non_blocking=True)

                with torch.amp.autocast("cuda", enabled=use_amp):
                    logits = model(imgs)
                    probs = torch.softmax(logits, dim=1).float().cpu().numpy()

                for p, fname in zip(probs, filenames):
                    idx = int(os.path.splitext(fname)[0].split("_")[1])
                    _, y, x = tile_coords[idx]

                    for c in range(n_classes):
                        sum_prob[y:y+tile_size, x:x+tile_size, c] += p[c] * w2d_base

                    sum_w[y:y+tile_size, x:x+tile_size] += w2d_base

        # -------------------------------------------
        # Stitch prediction
        # -------------------------------------------
        print("Reconstructing full mask...")

        sum_w_safe = np.clip(sum_w, 1e-6, None)
        avg_prob = sum_prob / sum_w_safe[..., None]
        full_pred = np.argmax(avg_prob, axis=-1).astype(np.uint8)

        final_mask = full_pred[:H, :W]

        # -------------------------------------------
        # Convert mask to RGB
        # -------------------------------------------
        print("Colorizing mask...")
        CLASS_TO_COLOR = {
            # 0: (0, 0, 0),
            # 1: (85, 85, 85), # T
            # 2: (255, 214, 0), #  AB
            # 3: (204, 92, 92), # EA
            # 4: (30, 143, 255), # OOF
            # 5: (217, 112, 214) # TF
            
            # 0: (0),
            # 1: (0), # T
            # 2: (255), #  AB
            # 3: (255), # EA
            # 4: (255), # OOF
            # 5: (255) # TF
                  
            0: 0, 
            1: 0, 
            2: 4, 
            3: 1,
            4: 3,
            5: 5 
        }

        # rgb_mask = np.zeros((H, W, 3), dtype=np.uint8)
        rgb_mask = np.zeros((H, W), dtype=np.uint8)
        for cls, color in CLASS_TO_COLOR.items():
            rgb_mask[final_mask == cls] = color

        tifffile.imwrite(output_mask_path, rgb_mask, compression="lzma")
        print(f"Saved mask to: {output_mask_path}")

        # -------------------------------------------
        # Cleanup
        # -------------------------------------------
        shutil.rmtree(temp_dir)
        print("Cleaned temporary tiles.\n")



