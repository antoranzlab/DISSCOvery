import tifffile as tiff
import matplotlib.pyplot as plt
import matplotlib
import cv2

print(matplotlib.get_backend())

image = tiff.imread('/media/Share2/MIBCC_intermediate_Results/STS/LOIC1_merged_mask_resized.ome.tiff')

plt.hist(image)
plt.waitKey(0)
plt.show()