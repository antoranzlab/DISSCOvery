<h1 align="center"> Split scenes </h1>

---

## Table of content

[1. Generate scenes](#1-generate-scenes-)

[2. Reverse transformation](#2-reverse-transformation)

[3. Split scenes](#3-split-scenes-)

<pre> 
06_split_scenes
├── MILAN
│    ├── 1. generate_scenes_csv.R
│    ├── 2. reverse_transformation_list_jobs.R
│    ├── 3. run_reverse_transformation.py
│    │   └── reverse_transformation.py
│    ├── 4. split_scenes_list_jobs.R
│    └── 5. run_split_scenes.py
│        └── split_scenes.R
│
└── COMET/AKOYA
     ├── 1. generate_scenes_csv.R
     ├── 2. 01_split_scenes_processed_list_jobs.R
     └── 3. run_split_scenes_processed.py
         └── split_scenes_processed.py

</pre>

---

# MILAN

---

## 1. Generate scenes 

---

**Script:** [generate_scenes_csv.R](src/06_split_scenes/generate_scenes_csv.R) 

### Description

The script generates CSV file that is necessary to run cell phenotyping and assigning cells to specific tissues

### Arguments
```
Rscript src/06_split_scenes/generate_scenes_csv.R --input_path_bb <path_to_input_bounding_boxes/> --ref_round <reference_round/> --ref_version <reference_version/> --output_path_csv <path_to_output_csv/> 
```

| Argument             | Description                                                                                                                                                                                                                                                     |
|----------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_bb`   | Path to the parent directory where the tiles are stored (dir). Example: `/path/to/project_directory/output_STS/BBs`. It can also use the output of FFC.                                                                                                     |
| `ref_round`        | Reference round (str). Example: `R01`                                                                                                                                      |
| `ref_version`      | Reference version (str). Example: `V01`               |                   |
| `output_path_csv`    | Path to the CSV where the list of jobs will be saved (.csv). Example: `/path/to/project_directory/experimental_design/experimental_design_scenes.csv`|

---

## 2. Reverse transformation

---
**Script:** [reverse_transformation_list_jobs.R](src/06_split_scenes/reverse_transformation_list_jobs.R) 

### Description

This function lists all the paths for input and output files and generates a csv with the list of jobs that have to be run for reverse transformation

### Arguments
```
Rscript src/06_split_scenes/reverse_transformation_list_jobs.R --input_path_tm <path_to_input_transformation_matrices/> --input_path_masks <path_to_input_foreground_masks/> --input_path_bb <path_to_input_bounding_boxes/> --output_path_masks <path_to_output_foreground_masks/> --output_path_bb <path_to_output_bounding_boxes/> --ref_round <reference_round/> --ref_version <reference_version/> --output_path_csv <path_to_output_csv/>
```

| Argument        | Description                                                                                                                             |
|-----------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_tm`   | Path to the directory with the transformation matrices (dir). Example: `/path/to/project_directory/output_STS/output_coarse_registration/tm`. |
| `input_path_masks` | Path to the foreground masks (dir). Example: `/path/to/project_directory/output_STS/output_masks`.                                      |
| `input_path_bb`  | Path to the bounding boxes (dir). Example: `/path/to/project_directory/output_STS/BBs`.                                                 |
| `output_path_masks`| Path to the foreground mask output (dir). Example: `/path/to/project_directory/output_STS/output_masks_reverse`.                        |
| `output_path_bb` | Path to the bounding boxes output (dir). Example: `/path/to/project_directory/output_STS/BBs_reverse`.                                  |
| `ref_round`      | Reference round (str). Example: `R01`.                                                                                                  |
| `ref_version`       | Reference version (str). Example: `V01`.                                                                                                |
| `output_path_csv`      | Path to output csv where the list of jobs will be saved (.csv). Example: `/path/to/project_directory/output_STS/reverse_transformation_job_list.csv`.                                                     |

---
**Script:** [run_reverse_transformation.py](src/06_split_scenes/run_reverse_transformation.py) 

### Description
It orchestrates reverse transformation. It requires the output CSV file of [reverse_transformation_list_jobs.R](src/06_split_scenes/reverse_transformation_list_jobs.R) and [reverse_transformation.py](src/06_split_scenes/reverse_transformation.py) script  as positional arguments

### Arguments
```
python src/06_split_scenes/run_reverse_transformation.py <csv_path/> src/06_split_scenes/reverse_transformation.py
```

| Argument                 | Description                                                                                                                         |
|--------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/reverse_transformation_job_list.csv` |

---

**Script:** [reverse_transformation.py](src/06_split_scenes/reverse_transformation.py) 

### Description

The script projects the masks and bounding boxes from the reference round to other rounds - it inverts the transformation matrix obtained during the coarse registration

### Arguments
```
python src/06_split_scenes/reverse_transformation.py --input_path_tm <path_to_input_transformation_matrices/> --input_path_masks <path_to_input_foreground_masks/> --input_path_bb <path_to_input_bounding_boxes/> --output_path_masks <path_to_output_foreground_masks/> --output_path_bb <path_to_output_bounding_boxes/> --ref_round <reference_round/> --ref_version <reference_version/> --output_path_csv <path_to_output_csv/>
```

| Argument        | Description                                                                                                                             |
|-----------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_tm`   | Path to the directory with the transformation matrices (dir). Example: `/path/to/project_directory/output_STS/output_coarse_registration/tm`. |
| `input_path_masks` | Path to the foreground masks (dir). Example: `/path/to/project_directory/output_STS/output_masks`.                                      |
| `input_path_bb`  | Path to the bounding boxes (dir). Example: `/path/to/project_directory/output_STS/BBs`.                                                 |
| `output_path_masks`| Path to the foreground mask output (dir). Example: `/path/to/project_directory/output_STS/output_masks_reverse`.                        |
| `output_path_bb` | Path to the bounding boxes output (dir). Example: `/path/to/project_directory/output_STS/BBs_reverse`.                                  |


---

## 3. Split scenes 

---

**Script:** [split_scenes_list_jobs.R](src/06_split_scenes/split_scenes_list_jobs.R) 

### Description

This function lists all the paths for input and output files and generates a csv with the list of jobs that have to be run for split scenes

### Arguments
```
Rscript src/06_split_scenes/split_scenes_list_jobs.R --input_path_tiles <path_to_input_tiles/> --input_path_meta <path_to_input_metadata/> --input_path_masks_foreground <path_to_input_foreground_masks/> --input_path_bb <path_to_input_bounding_boxes/> --input_path_masks_qc <path_to_input_quality_control_masks/> --output_path_error_log <path_to_output_error_log/> --px_size_sts <pixel_size_used_in_STS/> --px_size_qc <pixel_size_used_in_QC/> --output_path_folder <path_to_output_directory/> --output_path_csv <path_to_output_csv/> --skip_existing <skip_existing_results/>
```

| Argument                      | Description                                                                                                                                 |
|-------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_tiles`            | Path to the directory with the input tiles (dir). Example: `/path/to/project_directory/output_FFC_corrected`.                               |
| `input_path_meta`             | Path to the input metadata (dir). Example: `/path/to/project_directory/output_tiles_tiffs`.                                                 |
| `input_path_masks_foreground` | Path to the input foreground mask (dir). Example: `/path/to/project_directory/output_STS/output_masks_reverse`.                             |
| `input_path_bb`               | Path to the input bounding boxes (dir). Example: `/path/to/project_directory/output_STS/BBs_reverse`.                                       |
| `input_path_masks_qc`         | Path to the input QC masks (dir). Example: `/path/to/project_directory/output_QC`.                                                          |
| `output_path_error_log`       | Path to the output error log txts (dir). Example: `/path/to/project_directory/split_scenes_errors_logs`.                                    |
| `px_size_sts`                 | Pixel size used for STS (numeric). Example: `2.6`.                                                                                          |
| `px_size_qc`                  | Pixel size used for QC (numeric). Example: `0.65`.                                                                                          |
| `output_path_folder`          | Path to output directory (dir). Example: `/path/to/project_directory/split_scenes`.                                                         |
| `output_path_csv`             | Path to output csv where the list of jobs will be saved (.csv). Example: `/path/to/project_directory/output_STS/split_scenes_job_list.csv`. |
| `skip_existing`               | Boolean to skip already existing results (boolean). Example: `False`.                                                                         |

---
**Script:** [run_split_scenes.py](src/06_split_scenes/run_split_scenes.py) 

### Description
It orchestrates reverse transformation. It requires the output CSV file of [split_scenes_list_jobs.R](src/06_split_scenes/split_scenes_list_jobs.R) and [split_scenes.R](src/06_split_scenes/split_scenes.R) script  as positional arguments

### Arguments

```
python src/06_split_scenes/run_split_scenes.py <csv_path/> src/06_split_scenes/split_scenes.R
```

| Argument                 | Description                                                                                                                         |
|--------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/split_scenes_job_list.csv` |

---

**Script:** [split_scenes.R](src/06_split_scenes/split_scenes.R) 

### Description

This function generates separate scenes from the original images

### Arguments
```
Rscript src/06_split_scenes/split_scenes.R --input_path_tiles <path_to_input_tiles/> --input_path_meta <path_to_input_metadata/> --input_path_bb <path_to_input_bounding_boxes/> --input_path_masks_foreground <path_to_input_foreground_masks/> --input_path_masks_qc <path_to_input_quality_control_masks/> --output_path_folder <path_to_output_directory/> --conversion_factor_sts <conversion_factor_sts/> --conversion_factor_qc <conversion_factor_qc/> --channel_id <channel_id/> --skip_existing <skip_existing/>
```

| Argument                      | Description                                                                                                     |
|-------------------------------|-----------------------------------------------------------------------------------------------------------------|
| `input_path_tiles`            | Path to the directory with the input tiles (dir). Example: `/path/to/project_directory/output_FFC_corrected`.   |
| `input_path_meta`             | Path to the input metadata (dir). Example: `/path/to/project_directory/output_tiles_tiffs`.                     |
| `input_path_masks_foreground` | Path to the input foreground mask (dir). Example: `/path/to/project_directory/output_STS/output_masks_reverse`. |
| `input_path_bb`               | Path to the input bounding boxes (dir). Example: `/path/to/project_directory/output_STS/BBs_reverse`.           |
| `input_path_masks_qc`         | Path to the input QC masks (dir). Example: `/path/to/project_directory/output_QC`.                              |
| `output_path_folder`          | Path to output directory (dir). Example: `/path/to/project_directory/split_scenes`.                             |
| `conversion_factor_sts`       | Conversion factor for STS (numeric). Example: `4`.                                                              |
| `conversion_factor_qc`        | Conversion factor for STS (numeric). Example: `1`.                                                              |
| `channel_id`     | Channel ID (str). Example: `DAPI`.                                                                              |
| `skip_existing`               | Boolean to skip already existing results (boolean). Example: `False`.                                             |

---

# COMET/AKOYA

---

**Script:** [generate_scenes_csv.R](src/06_split_scenes/generate_scenes_csv.R) 

### Description

The script generates CSV file that is necessary to run cell phenotyping and assigning cells to specific tissues

### Arguments
```
Rscript src/06_split_scenes/generate_scenes_csv.R --input_path_bb <path_to_input_bounding_boxes/> --ref_round <reference_round/> --ref_version <reference_version/> --output_path_csv <path_to_output_csv/> 
```

| Argument             | Description                                                                                                                                                                                                                                                     |
|----------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_bb`   | Path to the parent directory where the tiles are stored (dir). Example: `/path/to/project_directory/output_STS/BBs`. It can also use the output of FFC.                                                                                                     |
| `ref_round`        | Reference round (str). Example: `R01`                                                                                                                                      |
| `ref_version`      | Reference version (str). Example: `V01`               |                   |
| `output_path_csv`    | Path to the CSV where the list of jobs will be saved (.csv). Example: `/path/to/project_directory/experimental_design/experimental_design_scenes.csv`|

---

**Script:** [01_split_scenes_processed_list_jobs.R](src/06_split_scenes//01_split_scenes_processed_list_jobs.R) 

### Description

The script generates CSV job list file

### Arguments
```
Rscript src/06_split_scenes//01_split_scenes_processed_list_jobs.R --input_tiles <input_tiles/> --input_bb <input_bb/> --input_mask_foreground <input_mask_foreground/> --input_mask_qc <input_mask_qc/> --output_folder <output_folder/> --conversion_factor <conversion_factor/> --skip_existing <skip_existing/>
```

| Argument         | Description                                                                                                                             |
|------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| `input_tiles` | Path to input tiles (tiff). Example: `path/to/project_directory/output_processed/BMARK01_R01_V01_COMET/BMARK01_R01_V01_COMET_DAPI.tiff` |
| `input_bb`    | Path to bounding boxes (csv). Example: `path/to/project_directory/output_STS/BBs/BMARK01/BMARK01_R01_V01_COMET_DAPI.csv`                |
| `input_mask_foreground`   | Path to foreground mask (.tiff). Example: `path/to/project_directory/output_STS/output_masks/BMARK01/BMARK01_R01_V01_COMET_DAPI.tiff`   |                   |
| `input_mask_qc` | Path to qualifai mask (dir)). Example: `path/to/project_directory/output_QC/BMARK01/BMARK01_R01_V01_COMET_DAPI.tiff`                    |
| `output_folder`    | Path to output path to save images (dir)). Example: `2.32142857142857`                                                                  |                   |
| `conversion_factor` | Conversion factor for downscaling (numeric). Example: `9.28571428571428`                                                                |
| `skip_existing` | Boolean to skip already existing results (boolean). Example: `TRUE`                                                                      |

---
**Script:** [run_split_scenes_processed.py](src/06_split_scenes/run_split_scenes_processed.py) 

### Description
It orchestrates reverse transformation. It requires the output CSV file of [01_split_scenes_processed_list_jobs.R](src/06_split_scenes/01_split_scenes_processed_list_jobs.R) and [split_scenes.R](src/06_split_scenes/split_scenes_processed.py) script  as positional arguments

### Arguments

```
python src/06_split_scenes/run_split_scenes.py <csv_path/> src/06_split_scenes/split_scenes_processed.py
```

| Argument                 | Description                                                                                                                         |
|--------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/split_scenes_job_list.csv` |

---

**Script:** [split_scenes_processed.py](src/06_split_scenes/split_scenes_processed.py) 

### Description

Splits the slides into scenes

### Arguments
```
python src/06_split_scenes/split_scenes_processed.py --input_path_image <input_path_image/> --input_path_bb <input_path_bb/> --input_path_foreground <input_path_foreground/> --input_path_qc <input_path_qc/> --output_path_image <output_path_image/> --conversion_factor_qc <conversion_factor_qc/>  --conversion_factor_hs <conversion_factor_hs/> --skip_existing <skip_existing/>
```

| Argument       | Description                                                                                                                             |
|----------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_image` | Path to input tiles (tiff). Example: `path/to/project_directory/output_processed/BMARK01_R01_V01_COMET/BMARK01_R01_V01_COMET_DAPI.tiff` |
| `input_path_bb`   | Path to bounding boxes (csv). Example: `path/to/project_directory/output_STS/BBs/BMARK01/BMARK01_R01_V01_COMET_DAPI.csv`                |
| `input_path_foreground` | Path to foreground mask (.tiff). Example: `path/to/project_directory/output_STS/output_masks/BMARK01/BMARK01_R01_V01_COMET_DAPI.tiff`   |                   |
| `input_path_qc` | Path to qualifai mask (dir)). Example: `path/to/project_directory/output_QC/BMARK01/BMARK01_R01_V01_COMET_DAPI.tiff`                    |
| `output_path_image`  | Path to output path to save images (tiff). Example: `path/to/project_directory/split_scenes/bmark01/BMARK01_R01_V01_COMET_DAPI.tiff`    |                   |
| `conversion_factor_qc` | Conversion factor for downscaling (numeric). Example: `2.32142857142857`                                                                |
| `conversion_factor_hs` | Boolean to skip already existing results (boolean). Example: `9.28571428571428`                                                                     |
| `skip_existing` | Boolean to skip already existing results (boolean). Example: `True`                                                                     |

---