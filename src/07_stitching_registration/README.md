<h1 align="center"> COLLAGE registration </h1>

---

## Table of content

[1. Rename files](#1-rename-files)

[2. COLLAGE](#2-collage)

[3. Undo renaming](#2-undo-renaming)

[4. Evaluate registration performance (AlgnQC)](#3-evaluate-registration-performance-algnqc)

<pre> 
07_stitching_registration
└── MILAN
    ├── 1. rename_round_versions.R
    ├── 2. COLLAGE
    ├── 3. undo_rename_round_versions.R
    ├── 4. algnqc_list_jobs.R
    └── 5. run_algnqc.py
        └── evaluate_registration_algnqc.py
</pre>

---

# 1. Rename files

---

**Script:** [rename_round_versions.R](src/07_stitching_registration/rename_round_versions.R) 

### Description

COLLAGE require only one version of the same round. This script maps the round/versions and changes the files names with new round IDs 

### Arguments
```
Rscript src/07_stitching_registration/rename_round_versions.R --input_path_tiles <path_to_input_tile/> --output_path_dictionary <path_to_output_dictionary/> 
```

| Argument             | Description                                                                                                                                                                                                                                                  |
|----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_tiles`   | Path to input tiles (dir). Example: `/path/to/project_directory/split_scenes`                                                                                                     |
| `output_path_dictionary`        | Path to output dictionary csv (.csv). Example: `/path/to/project_directory/round_version_dictionary.csv`                                                                                                                                    |

---

# 2. COLLAGE

Registration for MILAN is conducted using COLLAGE. More information can be found here:
https://www.biorxiv.org/content/10.1101/2024.07.15.603557v1


---

# 3. Undo renaming

---
**Script:** [undo_rename_round_versions.R](src/07_stitching_registration/undo_rename_round_versions.R) 

### Description

This function renames back teh files to their original names

### Arguments
```
Rscript src/07_stitching_registration/undo_rename_round_versions.R --input_path_images_ffc <path_to_input_transformation_matrices/> --input_path_images_reg <path_to_input_foreground_masks/> --input_path_dictionary <path_to_input_bounding_boxes/>
```

| Argument        | Description                                                                                                    |
|-----------------|----------------------------------------------------------------------------------------------------------------|
| `input_path_images_ffc`   | Path to the input flat field corrected tiles (dir). Example: `/path/to/project_directory/output_FFC_corrected`. |
| `input_path_images_reg` | Path to the input registered image (dir). Example: `/path/to/project_directory/output_registration`.       |
| `input_path_dictionary`  | path to the input naming dictionary (.csv). Example: `/path/to/project_directory/round_version_dictionary.csv`.   |

---

# 4. Evaluate registration performance (AlgnQC)

---

**Script:** [algnqc_list_jobs.R](src/07_stitching_registration/algnqc_list_jobs.R) 

### Description

This function lists all the paths for input and output files and generates a csv with the list of jobs that have to be run for QC evaluation

### Arguments
```
Rscript src/07_stitching_registration/algnqc_list_jobs.R --input_path_images <path_to_input_images/> --output_folder_csv <path_to_output_directory_csv/> --output_folder_html <path_to_output_directory_html/> --output_folder_json <path_to_output_directory_json/> --path_model <path_to_algnqc_model/> --ref_round <reference_round/> --ref_version <reference_version/> --ref_channel <reference_channel/> --output_path_csv <path_csv/>
```

| Argument     | Description                                                                                                     |
|--------------|-----------------------------------------------------------------------------------------------------------------|
| `input_path_images` | Path to input images (dir). Example: `/path/to/project_directory/output_registration/output_registration`.      |
| `output_folder_csv` | Path to output path to save csv (dir). Example: `/path/to/project_directory/output_registration_qc/csv`.        |
| `output_folder_html` | Path to output path to save csv (dir). Example: `/path/to/project_directory/output_registration_qc/html`.       |
| `output_folder_json` | Path to output path to save csv (dir). Example: `/path/to/project_directory/output_registration_qc/json`.       |
| `path_model` | Path to the classification model (h5). Example: `models/07_classification_network.h5`.                          |
| `ref_round` | Reference round (str).  Example: `R01`.                                                                         |
| `ref_version` | Reference version (str). Example: `V01`.                                                                        |
| `ref_channel` | Reference channel (str). Example: `DAPI`.                                                                       |
| `output_path_csv` | Path to output csv where to save the joblist (.csv). Example: `/path/to/project_directory/algnqc_job_list.csv`. |

---

**Script:** [run_algnqc.py](src/07_stitching_registration/run_algnqc.py) 

### Description
It orchestrates QC evaluation. It requires the output CSV file of [algnqc_list_jobs.R](src/07_stitching_registration/algnqc_list_jobs.R) and [evaluate_registration_algnqc.py](src/07_stitching_registration/evaluate_registration_algnqc.py) script  as positional arguments

### Arguments

```
python src/07_stitching_registration/run_algnqc.py <csv_path/> src/07_stitching_registration/evaluate_registration_algnqc.py
```

| Argument                 | Description                                                                                                                         |
|--------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/algnqc_job_list.csv` |

---

**Script:** [evaluate_registration_algnqc.py](src/07_stitching_registration/evaluate_registration_algnqc.py) 

### Description

This script generates the QC figures to evaluate the registration.

### Arguments
```
Rscript src/07_stitching_registration/evaluate_registration_algnqc.py --path_ref_image <path_to_reference_image/> --path_query_image <path_to_query_image/> --path_model <loaded_algnqc_model/> --path_csv <path_csv/> --path_html <path_to_html_output/> --path_json <path_to_json_output/>
```

| Argument     | Description                                                                                                                                                                 |
|--------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `path_ref_image` | Path to the reference image (.tiff). Example, `/path/to/project_directory/output_registration_collage/BM_R01_V01_BENCHMARK_ND_S0/BM_R01_V01_BENCHMARK_ND_S0_DAPI.tiff`.     |
| `path_query_image` | Path to the query image (.tiff). Example, `/path/to/project_directory/output_registration_collage/BM_R01_V01_BENCHMARK_ND_S0/BM_R01_V01_BENCHMARK_ND_S0_DAPI.tiff`.         |
| `path_model` | Loaded Algnqc model (.h5). Example: `models/07_classification_network.h5`.                                                                                                  |
| `path_csv` | Path to the csv output where the AlgnQC stats will be saved. Example, `/path/to/project_directory/output_registration_qc/csv/BM_S0/BM_R01_V01_BENCHMARK_ND_S0_DAPI.csv`.    |
| `path_html` | Path to the html output where the AlgnQC stats will be saved. Example, `/path/to/project_directory/output_registration_qc/html/BM_S0/BM_R01_V01_BENCHMARK_ND_S0_DAPI.html`. |
| `path_json` | Path to the json output where the AlgnQC stats will be saved. Example, `/path/to/project_directory/output_registration_qc/json/BM_S0/BM_R01_V01_BENCHMARK_ND_S0_DAPI.json`. |

---

