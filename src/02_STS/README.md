<h1 align="center"> Smart Tissue Selection (STS) </h1>

---

## Table of content

[1. Coarse Registration](#1-coarse-registration)

[2.  Mask generation](#2-mask-generation)

[3.  Bounding Box Generation ](#3-bounding-box-generation-)

[4. Evaluate concordance](#4-evaluate-concordance-)

<pre> 
02_STS 
├── MILAN
    ├── 1. coarse_registration_list_jobs.R
    ├── 2. run_sts_coarse_reg.py
    │   └── STS_coarse_registration_imreg.py
    ├── 3. mask_generation_list_jobs.R
    ├── 4. run_STS_mask.py
    │   └── STS_generate_mask.py
    ├── 5. BB_estimation_list_jobs.R
    ├── 6. run_STS_BB.py
    │   └── STS_generate_BB.py
    ├── 7. bb_concordance_list_jobs.R
    └── 8. run_STS_concordance.py
        └── STS_evaluate_concordance.R

</pre>

---

# 1. Coarse Registration

---

**Script:** [coarse_registration_list_jobs.R](src/02_STS/coarse_registration_list_jobs.R)


### Description
This function lists all the paths for input and output files and generates a csv with the list of jobs that have to be run for Coarse Registration.
### Arguments
```
Rscript src/02_STS/coarse_registration_list_jobs.R --input_path_images <path_to_hard_stitching_images/> --output_path_images <path_to_output_images/> --output_path_tm <path_to_output_transformation_matrices/> --ref_channel <reference_channel/> --ref_round <reference_round/> --ref_version <reference_version/> --output_path_csv <path_to_output_csv/>  
```
| Argument           | Description                                                                                                                            |
|--------------------|----------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_images` | Full path to the hard stitching images (dir). Example: `/path/to/project_directory/hard_stitching` or `/path/to/project_directory/hard_stitching_FFC`                                 |
| `output_path_images`| Full path to the output images (dir). Example: `/path/to/project_directory/output_coarse_registration/images`                          |
| `output_path_tm`    | Full path to the output transformation matrices (dir). Example: `/path/to/project_directory/output_coarse_registration/tm`             |
| `ref_channel`      | Reference channel (str). Example: `DAPI`                                                                                               |
| `ref_round`        | Reference round (str). Example: `R01`                                                                                                  |
| `ref_version`      | Reference version (str). Example: `V01`                                                                                                |
| `output_path_csv`  | Path to output CSV where the list of jobs will be saved (.csv). Example: `/path/to/project_directory/coarse_registration_job_list.csv` |

---

**Script:** [STS_coarse_registration_imreg.py](src/02_STS/STS_coarse_registration_imreg.py)

### Description
The script performs coarse registration with Imreg. 


### Arguments
```
python src/02_STS/STS_coarse_registration_imreg.py --path_fixed_image <path_to_fixed_image/> --path_query_image <path_to_query_image/> --path_query_registered <path_to_output_registered_image/> --path_transformation_matrix <path_to_transformation_matrix/>
```

| Argument                  | Description                                                                                                          |
|---------------------------|----------------------------------------------------------------------------------------------------------------------|
| `path_fixed_image`        | Full path to the reference image (.tiff). Example: `path/to/project_directory/hard_stitching/BM/BM_R01_V01_BENCHMARK_ND_DAPI.tiff` |
| `path_query_image`        | Full path to the query/moving image (.tiff). Example: `/path/to/project_directory/hard_stitching/BM/BM_R02_V01_BENCHMARK_ND_DAPI.tiff`   |
| `path_query_registered`   | Full path to the registered query/moving image (.tiff). Example: `/path/to/project_directory/output_coarse_registration/images/BM/BM_R02_V01_BENCHMARK_ND_DAPI.tiff` |
| `path_transformation_matrix` | Full path to the transformation matrix (.npy). Example: `/path/to/project_directory/output_coarse_registration/tm/BM/BM_R02_V01_BENCHMARK_ND_DAPI.npy` |

---

**Script:** [run_sts_coarse_reg.py](src/02_STS/run_sts_coarse_reg.py) 

### Description
It orchestrates coarse stitching. It requires the output CSV file of [coarse_registration_list_jobs.R](src/02_STS/coarse_registration_list_jobs.R) and [STS_coarse_registration_imreg.py](src/02_STS/STS_coarse_registration_imreg.py) script  as positional arguments


### Arguments
```
python src/02_STS/run_sts_coarse_reg.py <csv_path/> src/02_STS/STS_coarse_registration_imreg.py
```

| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/coarse_registration_job_list.csv` |


---

# 2. Mask generation

---

**Script:** [mask_generation_list_jobs.R](src/02_STS/mask_generation_list_jobs.R)

### Description
This function lists all the paths for input and output files and generates a csv with the list of jobs that have to be run for Mask Generation.

### Arguments

```
Rscript src/02_STS/mask_generation_list_jobs.R --input_path_images <path_to_hard_registered_images/> --output_path_images <path_to_output_masks/> --path_model <path_to_model/> --output_path_csv <path_to_output_csv/> --ref_channel <reference_channel/> 
```

| Argument            | Description                                                                                                                                                                                                                        |
|---------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_images` | Full path to the registered hard stitching images directory (dir). Example: `/path/to/project_directory/output_STS/output_coarse_registration/images` (for STS) or  `/path/to/project_directory/hard_stitching_FFC` (for FFC Kask) |
| `output_path_images` | Full path to the output masks directory (dir). Example: `/path/to/project_directory/output_STS/output_masks` (for STS) or `/path/to/project_directory/output_FFC_kask_masks ` (for FFC Kask)                                       |
| `path_model`        | Full path to the segmentation model file (`.h5`). Example: `/path/to/model/02_STS/uNet_simple_best.h5`                                                                                                                             |
| `output_path_csv`   | Path to the output CSV where the list of jobs will be saved (.csv). Example: `/path/to/project_directory/generate_mask_job_list.csv` (for STS) or `/path/to/project_directory/generate_mask_job_list_ffc.csv` (for FFC Kask)                     |
| `ref_channel`       | Reference channel (string). Example: `DAPI`                                                                                                                                                                                        |


---

**Script:** [STS_generate_mask.py](src/02_STS/STS_generate_mask.py)

### Description
The script creates tissue masks. 

### Arguments
```
python src/02_STS/STS_generate_mask.py --input_image_path <path_to_registered_hard_stitching/> -- output_image_path <path_to_output_mask/> --model_path <path_to_pretrained_model/> 
```
| Argument           | Description                                                                                                                                                                                                     |
|--------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_image_path`  | Full path to the image file where the registered hard stitched image is stored (.tiff). Example: `/path/to/project_directory/output_STS/output_coarse_registration/images/BM/BM_R00_V01_BENCHMARK_ND_DAPI.tiff` |
| `output_image_path` | Full path to the output file where the mask will be stored (.tiff). Example: `/path/to/project_directory/output_STS/output_masks/BM/BM_R00_V01_BENCHMARK_ND_DAPI.tiff`                                          |
| `model_path`        | Path to the output directory where the AI model is saved (.h5). Example: `/path/to/project_directory/02_STS/uNet_simple_best.h5`                                                                                |

---

**Script:** [run_STS_mask.py](src/02_STS/run_STS_mask.py) 

### Description
It orchestrates coarse stitching. It requires the output CSV file of [mask_generation_list_jobs.R](src/02_STS/mask_generation_list_jobs.R) and [STS_generate_mask.py](src/02_STS/STS_generate_mask.py) script  as positional arguments


### Arguments
```
python src/02_STS/run_STS_mask.py <csv_path/> src/02_STS/STS_generate_mask.py
```

| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/generate_mask_job_list.csv` |


---

# 3. Bounding Box Generation

---

**Script:** [02_STS/BB_estimation_list_jobs.R](src/02_STS/BB_estimation_list_jobs.R) 

### Description
This function lists all the paths for input and output files and generates a csv with the list of jobs that have to be run for Bounding Boxes Estimation.


### Arguments

```
Rscript src/02_STS/BB_estimation_list_jobs.R --input_path_images <path_to_STS_masks/> --output_path_bbs <path_to_output_bbs/> --filter_small <filter_small_objects/> --output_path_csv <path_to_output_csv/>
```

| Argument          | Description                                                                                                                                                                                |
|-------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_images`| Full path to the masks calculated in STS (dir). Example: `/path/to/project_directory/output_STS/output_masks`|
| `output_path_bbs`  | Full path to the bounding boxes output (dir). Example: `/path/to/project_directory/output_STS/BBs`                                                                                         |
| `filter_small`    | Boolean indicating whether to filter out small objects (str). Example: `True`                                                                                                           |
| `output_path_csv`  | Path to output csv where the list of jobs will be saved (.csv). Example: `/path/to/project_directory/BB_estimation_job_list.csv`                                                           |

---

**Script:** [02_STS/STS_generate_BB.py](src/02_STS/STS_generate_BB.py) 

### Description
The script creates csv files that contains bounding boxes coordinates for each scene

### Arguments

```
python src/02_STS/STS_generate_BB.py --input_image_path <path_to_mask/> --bbox_tile_path <path_to_output_BB_csv/> --filter_small <filter_small_annotations/> 
```
| Argument           | Description                                                                                                                                                           |
|--------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_image_path`  | Full path to the image file where the STS mask is stored (.tiff). Example: `/path/to/project_directory/output_STS/masks/BM_R00_V01_BENCHMARK_ND_DAPI.tiff`            |
| `bbox_tile_path`    | Full path to the output CSV file where the bounding boxes will be stored (.csv). Example: `/path/to/project_directory/output_STS/BB/BM_R00_V01_BENCHMARK_ND_DAPI.csv` |
| `filter_small`      | Boolean indicating whether small objects from the mask need to be filtered (str). Example: `True`. This is hardcoded to 0.1% of the whole image.                           |


---

**Script:** [run_STS_BB.py](src/02_STS/run_STS_BB.py) 

### Description
It orchestrates Bound Boxes estimation. It requires the output CSV file of [BB_estimation_list_jobs.R](src/02_STS/BB_estimation_list_jobs.R) and [STS_generate_BB.py](src/02_STS/STS_generate_BB.py) script  as positional arguments


### Arguments
```
python src/02_STS/run_STS_BB.py <csv_path/> src/02_STS/STS_generate_BB.py
```

| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/BB_estimation_job_list.csv` |


---

# 4. Evaluate concordance 

---

**Script:** [02_STS/bb_concordance_list_jobs.R](src/02_STS/bb_concordance_list_jobs.R) 


### Description
This function lists all the paths for input and output files and generates a csv with the list of jobs that have to be run for concordance evaluation 

```
Rscript src/02_STS/bb_concordance_list_jobs.R --input_path_BB <path_to_BB/> --output_path_html <path_to_heatmap/> --output_path_json <path_to_json/> --ref_round <reference_round/> --ref_version <reference_version/> --path_output_csv <path_to_job_list/>
```

### Arguments 

| Argument           | Description                                                                                                                                     |
|--------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_BB`    | Full path to the directory where the bounding boxes of all the slides are stored (dir). Example: `/path/to/project_directory/output_STS/BBs` |
| `output_path_html`  | Full path to the output HTML file where the heatmap will be saved (dir). Example: `/path/to/project_directory/output_STS/heatmaps_html`      |
| `output_path_json`  | Full path to the output JSON file where the heatmap will be saved (dir). Example: `/path/to/project_directory/output_STS/heatmaps_json`      |
| `ref_round`         | Round to be used as reference (str). Example: `R01`                                                                                          |
| `ref_version`       | Version to be used as a reference (str). Example: `V02`                                                             |
| `path_output_csv`   | Path to output CSV where the list of jobs will be saved (.csv). Example: `/path/to/project_directory/bb_concordance_job_list.csv`               |

---

**Script:** [02_STS/STS_evaluate_concordance.R](src/02_STS/STS_evaluate_concordance.R)

### Description
This script performs concordance evaluation. 

```
Rscript src/02_STS/bb_concordance_list_jobs.R --input_path_BB <path_to_BB/> --output_heatmap_path_html <path_to_heatmap/> --output_heatmap_path_json <path_to_json/> --reference_round <reference_round/> --reference_version <reference_version/> --path_output_csv <path_to_job_list/>
```

### Arguments 

| Argument           | Description                                                                                                                                  |
|--------------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_BB`    | Full path to the directory where the bounding boxes of all the slides are stored (dir). Example: `/path/to/project_directory/output_STS/BBs` |
| `output_path_html`  | Full path to the output HTML file where the heatmap will be saved (dir). Example: `/path/to/project_directory/output_STS/heatmaps_html`   |
| `output_path_json`  | Full path to the output JSON file where the heatmap will be saved (dir). Example: `/path/to/project_directory/output_STS/heatmaps_json`   |
| `ref_round`         | Round to be used as reference (str). Example: `R01`                                                                                       |
| `ref_version`       | Version to be used as a reference (str). Example: `V02`                                                             |

---

**Script:** [run_STS_concordance.py](src/02_STS/run_STS_concordance.py) 

### Description
It orchestrates coarse stitching. It requires the output CSV file of [bb_concordance_list_jobs.R](src/02_STS/bb_concordance_list_jobs.R) and [STS_evaluate_concordance.R](src/02_STS/STS_evaluate_concordance.R) script  as positional arguments


### Arguments
```
python src/02_STS/run_STS_mask.py <csv_path/> src/02_STS/STS_evaluate_concordance.R
```

| Argument                 | Description                                                                                                                         |
|--------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/bb_concordance_job_list.csv` |