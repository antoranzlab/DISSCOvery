<h1 align="center"> Flat Filed Correction (FFC) </h1>

---

## Table of content

[1. Overview](#1-overview)

[2. FFC BaSiC](#2-ffc-basic)

[3. FFC Kask](#3-ffc-kask)

[4. FFC Raw](#4-ffc-raw)

[5. FFC metadata](#5-ffc-metadata)

<pre> 02_FFC 
├── MILAN
    ├── 1. FFC_list_jobs.R
    │   ├── 1.1 01_hard_stitching*
    │   │   ├── 1.1.1 hard_stitching_list_jobs.R
    │   │   └── 1.1.2 run_hs.py
    │   │       └── hard_stitching.py
    │   └── 1.2 02_STS*
    │       ├── 1.2.1 mask_generation_list_jobs.R
    │       └── 1.2.2 run_STS_mask.py
    │           └── STS_generate_mask.py
    ├── 2. run_ffc_basic.py
    │   └── FFC_BaSiC.py
    ├── 3. run_ffc_kask.py
    │   └── FFC_Kask.py
    ├── 4. run_ffc_raw.py
    │   └── FFC_raw.py
    └── 5. run_ffc_metadata.py
        └── FFC_metadata.py

* preparation of the input data for FFC Kask
</pre>

---

# 1. Overview

---

As a result of the benchmarking study, we have a preferred FFC method per technology and channel. We consider 3 possibilities: raw tiles (no FFC needed), method from Kask et al (https://onlinelibrary.wiley.com/doi/10.1111/jmi.12404) and BaSiC (https://www.nature.com/articles/ncomms14836).  The table below shows the preferable method for each case. 

| Technology | Channel   | Background | Foreground | Method |
|------------|-----------|------------|------------|--------|
| MILAN      | DAPI      | RAW        | RAW        | RAW    |
| MILAN      | FITC      | BASIC      | RAW        | BASIC  |
| MILAN      | AF        | KASK       | KASK       | KASK   |
| MILAN      | TRITC     | BASIC      | BASIC      | BASIC  |
| MILAN      | Cy5       | BASIC      | BASIC      | BASIC  |
| COMET      | DAPI      | KASK       | KASK       | KASK   |
| COMET      | TRITC     | KASK       | KASK       | KASK   |
| COMET      | Cy5       | KASK       | KASK       | KASK   |
| MACSIMA    | DAPI      | RAW        | BASIC      | BASIC  |
| MACSIMA    | FITC      | BASIC      | BASIC      | BASIC  |
| MACSIMA    | APC       | BASIC      | BASIC      | BASIC  |
| MACSIMA    | PE        | RAW        | RAW        | RAW    |
| AKOYA      | DAPI      | BASIC      | BASIC      | BASIC  |
| AKOYA      | ATTO550   | BASIC      | BASIC      | BASIC  |
| AKOYA      | AF750     | BASIC      | BASIC      | BASIC  |
| AKOYA      | Cy5       | BASIC      | BASIC      | BASIC  |

The method from Kask et al requires providing input masks. These can be calculated using the hard stitched DAPI images and the raw tiles. 

If a technology/channel is not included in the list, BASIC is applied as default. 

---
**Script:** [FFC_list_jobs.R](src/02_FFC/FFC_list_jobs.R) 

### Description
This script lists all the folders in the input directory and generates a csv with the list of jobs that have to be run for FFC. 

### Arguments
```
Rscript src/02_FFC//FFC_list_jobs.R --input_path_tiles <path_to_tiles/> --input_path_meta <path_to_input_metadata/> --input_path_masks <path_to_input_masks/> --mask_pixel_size <px_size_masks/> --input_method_dictionary <path_to_input_csv_with_dictionary/> --acquisition_technology <acquisition_technology/> --output_folder_corr <path_to_output_corrected/> --output_folder_templates <path_to_output_templates/> --output_csv <path_to_output_path_csv/> --output_path_csv_metadata <path_to_output_csv_for_metadata/> 
```

| Argument                   | Description                                                                                                                                                                             |
|----------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_tiles`         | Path to the parent directory where the tiles are stored (dir). Example: `/path/to/project_directory/output_tiles_tiffs`.                                                                |
| `input_path_meta`          | Path to the parent directory where the metadata is stored (dir). Usually the same folder as the input_path_tiles. Example: `/path/to/project_directory/output_tiles_tiffs`.             |
| `input_path_masks`         | Path to the parent directory where the masks will be stored (dir). Example: `/path/to/project_directory/output_STS/output_masks` or `/path/to/project_directory/output_FFC_kask_masks`. |
| `mask_pixel_size`          | Pixel size used for the masks (numeric). Example: `2.6`.                                                                                                                                |
| `input_method_dictionary`  | Path to the CSV with the dictionary containing FFC method per technology/channel (.csv). Example: `02_FFC/technology_channel_method_dictionary.csv`.                                    |
| `acquisition_technology`   | Used technology (str). Example: `MILAN`.                                                                                                                                                |
| `output_folder_corr`       | Path to the folder where the FFC tiles will be stored (dir). Example: `/path/to/project_directory/output_FFC_corrected`.                                                                |
| `output_folder_templates`  | Path to the folder where the FFC templates will be stored (dir). Example: `/path/to/project_directory/output_FFC_templates`.                                                            |
| `output_path_csv`          | Path to the CSV where the list of jobs will be saved (.csv). Example: `/path/to/project_directory/FFC_job_list.csv`.                                                                    |
| `output_path_csv_metadata` | Path to the CSV where the jobs list to copy the metadata will be saved (.csv). Example: `/path/to/project_directory/FFC_job_list_metadata.csv`.                                         |

---

# 2. FFC BaSiC

---

**Script:** [FFC_BaSiC.py](src/02_FFC/FFC_BaSiC.py)  

### Description
This function performs FFC using BaSiC method. It takes as an input a path to a folder with tiles and returns the same tiles without vignetting effect. It also creates QC plots. 

**This function requires a library (basicpy) that is not compatible with the typical TensorFlow installation. 
Therefore, it needs its own python environment. It is compatible with GPU acceleration.**

### Arguments

```
python src/02_FFC/02_FFC_BaSiC.py --in_path <path_to_raw_tiles/> --channel <channel_id/> --out_path_corr <path_to_output_directory/> --out_path_templates <path_to_output_qc_directory/> 
```

| Argument               | Description                                                                                                                                                           |
|------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `in_path`         | Path to the input directory where the tiles are stored (dir). Example: `/path/to/project_directory/output_tiles_tiffs/BM_R00_V01_BENCHMARK_ND`.                   |
| `channel`              | Channel name (str). Example: `DAPI`.                                                                                                                               |
| `out_path_corr` | Path to the output directory where the corrected tiles will be stored (dir). Example: `/path/to/project_directory/output_FFC_corrected/BM_R00_V01_BENCHMARK_ND`.      |
| `out_path_templates`     | Path to the output directory where the correction templates will be stored (dir). Example: `/path/to/project_directory/output_FFC_templates/BM_R00_V01_BENCHMARK_ND`. |

---

**Script:** [run_ffc_basic.py](src/02_FFC/run_ffc_basic.py)

### Description
It orchestrates BaSiC FFC. It requires the output CSV file of [FFC_list_jobs.R ](src/02_FFC/FFC_list_jobs.R) and [FFC_BaSiC.py](src/02_FFC/FFC_BaSiC.py) script  as positional arguments

### Arguments
```
python src/02_FFC/run_ffc_basic.py <path_to_output_csv_joblist/> src/02_FFC/FFC_BaSiC.py
```
| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `path_to_output_csv_joblist`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/FFC_job_list.csv` |


---

# 3. FFC Kask

### Description
This function performs FFC with the method described by Kask et al. Before running the main script that reduces vignetting, it is necessary to prepare all the input files required for this algorithm. 
Therefore, first the course stitching and tissue masks have to be generated.  

**File preparation:**

 - Step 1: Coarse stitching
   - [hard_stitching_list_jobs.R](src/03_hard_stitching/hard_stitching_list_jobs.R) 
   - [hard_stitching.py](src/03_hard_stitching/hard_stitching.py)
   
 - Step 2: Mask generation
   - [mask_generation_list_jobs.R](src/04_STS/mask_generation_list_jobs.R) 
   - [STS_generate_mask.py](src/04_STS/STS_generate_mask.py)

**Main script:** 

[FFC_Kask.py](src/02_FFC/FFC_Kask.py)

### Arguments for main script

```
python src/02_FFC/FFC_Kask.py --input_images <path_to_tiles/> --input_metadata <path_to_metadata/> --input_mask <path_to_mask/> --pixel_size <pixel_size_in_mask/> --channel <channel_identifier/> --output_path_corrected_tiles <path_to_corrected_tiles/> --output_path_templates <path_to_templates/> --n_cores <number_of_cores/> --skip_existing <skip_existing_results/> 
```

| Argument                    | Description                                                                                                                                                                |
|-----------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_images`              | Path to the input directory where the raw tiles are stored (dir). Example: `/path/to/project_directory/output_tiles_tiffs/BM_R00_V01_BENCHMARK_ND`.                        |
| `input_metadata`            | Path to the CSV where the metadata is stored (.csv). Example: `/path/to/project_directory/output_tiles_tiffs/BM_R00_V01_BENCHMARK_ND/BM_R00_V01_BENCHMARK_ND.csv`.         |
| `input_mask`                | Path to the TIFF file where the mask is stored (.tiff). Example: `/path/to/project_directory/output_FFC_kask_masks/BM/BM_R00_V01_BENCHMARK_ND_DAPI.tiff`.                  |
| `pixel_size`                | Pixel size used for the mask (numeric). Example: `2.6`.                                                                                                                    |
| `channel`                   | Channel identifier (str). Example: `DAPI`.                                                                                                                                 |
| `output_path_corrected_tiles` | Path to the output directory where the corrected tiles will be stored (dir). Example: `/path/to/project_directory/output_FFC/BM_R00_V01_BENCHMARK_ND`.                     |
| `output_path_templates`     | Path to the output directory where the correction templates will be stored (dir). Example: `/path/to/project_directory/output_FFC_templates/KASK/BM_R00_V01_BENCHMARK_ND`. |
| `n_cores`                   | Number of cores to use (numeric). Example: `10`.                                                                                                                           |
| `skip_existing`             | Whether to skip already existing results (str). Example: `False`.                                                                                                          |

---

**Script:** [run_ffc_kask.py](src/02_FFC/run_ffc_kask.py)

### Description
It orchestrates Kask FFC. It requires the output CSV file of [FFC_list_jobs.R](src/02_FFC/FFC_list_jobs.R) and [FFC_Kask.py](src/02_FFC/FFC_Kask.py) script  as positional arguments

### Arguments
```
python src/02_FFC/run_ffc_kask.py <path_to_output_csv_joblist/> src/02_FFC/FFC_Kask.py
```
| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `path_to_output_csv_joblist`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/FFC_job_list.csv` |


---


# 4. FFC Raw
**Script:** [FFC_raw.py](src/02_FFC/FFC_raw.py) 

### Description
This function copies the raw tiles to the output folder

### Arguments

```
python src/02_FFC/FFC_raw.py --input_images <path_to_tiles/> --channel <channel_identifier/> --output_path_corrected_tiles <path_to_corrected_tiles/> --skip_existing <skip_existing_results/> 
```

| Argument                | Description                                                                                                                                      |
|-------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_images`          | Path to the input directory where the raw tiles are stored (folder). For example: `path/to/project_directory/output_tiles_tiffs/BM_R00_V01_BENCHMARK_ND`. |
| `channel`               | Channel identifier (string). For example: `DAPI`.                                                                                                |
| `output_corrected_images` | Path to the output directory where the corrected tiles will be stored (folder). For example: `path/to/project_directory/output_FFC_corrected/BM_R00_V01_BENCHMARK_ND`. |
| `skip_existing`         | Whether to skip already existing results (boolean). For example: `False`.                                                                        |

---
**Script:** [run_ffc_raw.py](src/02_FFC/run_ffc_raw.py)

### Description
It orchestrates FFC raw. It requires the output CSV file of [FFC_list_jobs.R](src/02_FFC/FFC_list_jobs.R) and [FFC_raw.py](src/02_FFC/FFC_raw.py) script  as positional arguments

### Arguments
```
python src/02_FFC/run_ffc_raw.py <path_to_output_csv_joblist/> src/02_FFC/FFC_raw.py
```
| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `path_to_output_csv_joblist`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/FFC_job_list.csv` |


---

# 5. FFC metadata
**Script:** [FFC_metadata.py](src/02_FFC/FFC_metadata.py)

### Description
This function copies the metadata from the raw tiles to the output folders.

### Arguments

```
python src/02_FFC/FFC_metadata.py --input_metadata <path_to_input_metadata/> --output_metadata <path_to_output_metadata/> 
```

| Argument         | Description                                                                                                                                               |
|------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_metadata` | Path to the input CSV file with the metadata. For example: `path/to/project_directory/output_tiles_tiffs/BM_R00_V01_BENCHMARK_ND/BM_R00_V01_BENCHMARK_ND.csv`. |
| `output_metadata`| Path to the output CSV file with the metadata. For example: `path/to/project_directory/output_FFC_corrected/BM_R00_V01_BENCHMARK_ND/BM_R00_V01_BENCHMARK_ND.csv`.      |

---
**Script:** [run_ffc_metadata.py](src/02_FFC/run_ffc_metadata.py)

### Description
It orchestrates copying the metadata after FFC. It requires the output CSV file of [FFC_job_list_metadata.csv](src/02_FFC/FFC_job_list_metadata.csv) and [FFC_metadata.py](src/02_FFC/FFC_metadata.py) script  as positional arguments

### Arguments
```
python src/02_FFC/run_ffc_metadata.py <path_to_output_csv_joblist/> src/02_FFC/FFC_metadata.py
```
| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `path_to_output_csv_joblist`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/FFC_job_list_metadata.csv` |


---