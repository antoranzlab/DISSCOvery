<h1 align="center"> Coarse Stitching </h1>

---

<pre> 
03_hard_stitching 
├── MILAN
│   ├── 1. hard_stitching_list_jobs.R
│   └── 2. run_hs.py
│       └── hard_stitching.py
│
├── COMET/AKOYA (resizing)
│   ├── 1. resize_images_list_jobs.R
│   └── 2. run_resize.py
│       └── 01_resize_processed.py
│
└── AKOYA
    ├── 1. rebuild_preprocessed_ffc_akoya_list_jobs.R
    ├── 2. run_rebuild.py
    │    └── 01_rebuild_after_ffc.py
    └── 3. run_resize.py
        └── 01_resize_processed.py

</pre>

----

# MILAN

----

 **Script:** [hard_stitching_list_jobs.R](src/03_hard_stitching/hard_stitching_list_jobs.R) 

### Description
This script generates coarse stitched images from the individual tiles. 
This coarse stitched image is used for Smart Tissue Detection (STS), Qual-IF-AI, and for generating input files for FFC Kask method. 

### Arguments
```
Rscript src/03_hard_stitching/03_hard_stitching_list_jobs.R --input_path_tiles <path_to_tiles/> --input_path_meta <path_to_metadata/> --output_folder <path_to_output_images/> --output_path_csv <path_to_output_csv/> --output_pixel_size <pixel_size_output_images/> --_skip_existing <skip_existing/> --only_dapi <do_only_dapi/> 
```
| Argument             | Description                                                                                                                                                                                                                                                      |
|----------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_tiles`   | Path to the parent directory where the tiles are stored (dir). Example: `/path/to/project_directory/output_tiles_tiffs`. It can also use the output of FFC.                                                                                                      |
| `input_path_meta`    | Path to the parent directory where the metadata is stored (dir). Example: `/path/to/project_directory/output_tiles_tiffs`                                                                                                                                        |
| `output_folder`      | Path to the folder where the hard stitched images will be stored (dir). Example: `/path/to/project_directory/hard_stitching` (for STS), `/path/to/project_directory/hard_stitching_FFC` (for FFC Kask) or `hard_stitching_full_res` (for QUALIFAI)               |                   |
| `output_path_csv`    | Path to the CSV where the list of jobs will be saved (.csv). Example: `/path/to/project_directory/hard_stitching_job_list.csv` (for STS), `/path/to/project_directory/hard_stitching_job_list_FFC.csv` (for FFC Kask) or  `hard_stitching_job_list_full_res.csv` (for QUALIFAI)|
| `output_pixel_size`  | Pixel size for output images (numeric). Used to calculate conversion factor between real and reduced dimensions. For STS/FFC Kask the recommended value is 2.6, for QUALIFAI 0.65. Example: `2.6`.                                                               |
| `skip_existing`     | Boolean to skip already existing results (str). Example: `True`.                                                                                                                                                                                                 |
| `only_dapi`          | Boolean indicating whether to process only DAPI (str). Example: `True`.                                                                                                                                                                                          |

---
**Script:** [run_hs.py](src/03_hard_stitching/run_hs.py) 

### Description
It orchestrates hard stitching. It requires the output CSV file of [hard_stitching_list_jobs.R](src/03_hard_stitching/hard_stitching_list_jobs.R) and [hard_stitching.py](src/03_hard_stitching/hard_stitching.py) script  as positional arguments


### Arguments
```
python src/03_hard_stitching/run_hs.py <csv_path/> src/03_hard_stitching/hard_stitching.py
```

| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/hard_stitching_job_list.csv` |

----
**Script:** [hard_stitching.py](src/03_hard_stitching/hard_stitching.py) 

### Description
This function generates a hard stitched image.

### Arguments
```
python src/03_hard_stitching/hard_stitching.py --input_tiles <path_to_tiles/> --input_metadata <path_to_metadata/> --output_folder <path_to_output/> --conversion_factor <conversion_factor/> --skip_existing <skip_existing/> --only_dapi <do_only_dapi/> 
```

| Argument           | Description                                                                                                                                                                                                                                                   |
|--------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_tiles`      | Path to the folder where the tiles are stored (dir). Example: `/path/to/project_directory/output_tiles_tiffs/BM_R00_V01_BENCHMARK_ND`.                                                                                                                        |
| `input_metadata`   | Path to the CSV file where the metadata is stored (.csv). Example: `/path/to/project_directory/output_tiles_tiffs/BM_R00_V01_BENCHMARK_ND/full_BM_R00_V01_BENCHMARK_ND_meta.csv`.                                                                             |
| `output_folder`    | Path to the folder where the hard stitched images will be stored (dir). Example: `/path/to/project_directory/hard_stitching/BM`, `/path/to/project_directory/hard_stitching_FFC/BM` or `/path/to/project_directory/hard_stitching_full_res/BM` (for QULIFAI). |
| `conversion_factor`| Conversion factor for downscaling (numeric). Example: `4`.                                                                                                                                                                                                    |
| `skip_existing`    | Boolean to define whether to skip already existing results (string). Example: `True`.                                                                                                                                                                         |
| `only_dapi`        | Boolean indicating whether to perform hard stitching only on DAPI (string). Example: `True`.                                                                                                                                                                  |

---

# COMET/AKOYA (resizing)

----

**Script:** [resize_images_list_jobs.R](src/03_hard_stitching/resize_images_list_jobs.R) 

### Description
This function lists all the folders in the input directory and generates a csv with the list of jobs that have to be run for coarse stitching. 
Images from COMET needs it to be executed twice, once for STS and once for QUALIFAI. Image from AKOYA needs to be resized only for QULIFAI

### Arguments
```
Rscript src/03_hard_stitching/resize_images_list_jobs.R --input_path_images <input_path_images/> --output_folder <output_folder/> --input_pixel_size <input_pixel_size/> --output_pixel_size <output_pixel_size/> --output_path_csv <output_path_csv/>  
```

| Argument           | Description                                                                                                                                                                       |
|--------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_images`      | Path to input tiles (dir). Example:  `path/to/project_directory/output_processed` (AKOYA) or `path/to/project_directory/output_tiles_tiffs` (COMET).                              |
| `output_folder`   | Path to output path to save images (dir). Example:  `path/to/project_directory/hard_stitching` or `path/to/project_directory/resized_images`.                                     |
| `input_pixel_size`    | Pixel size input images (numeric). Example: `0.5` (AKOYA) or `0.28` (COMET).                                                                                                      |
| `output_pixel_size`| Pixel size input images (numeric). Example: `2.6` (for STS) or `0.65` (for QUALIFAI).                                                                                             |
| `output_path_csv`    | Path to output csv where the job list will be saved (.csv). Example:  `path/to/project_directory/hard_stitching_job_list.csv`  or `path/to/project_directory/resize_job_list.csv` |

---
**Script:** [run_resize.py](src/03_hard_stitching/run_resize.py) 

### Description
It orchestrates resizing the images. It requires the output CSV file of [resize_images_list_jobs.R](src/03_hard_stitching/hresize_images_list_jobs.R) and [01_resize_processed.py](src/03_hard_stitching/01_resize_processed.py) script  as positional arguments

### Arguments
```
python src/03_hard_stitching/run_resize.py <csv_path/> src/03_hard_stitching/01_resize_processed.py
```

| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `path/to/project_directory/hard_stitching_job_list.csv` |

---

**Script:** [01_resize_processed.py](src/03_hard_stitching/01_resize_processed.py) 

### Description
This function generates a rescaled, renomalized, 8-bit image.

### Arguments
```
python src/03_hard_stitching/01_resize_processed.py --input_path_image <input_path_image/> --output_path_image <output_path_image/> --conversion_factor <conversion_factor/> --skip_existing <skip_existing/> 
```

| Argument           | Description                                                                                                       |
|--------------------|-------------------------------------------------------------------------------------------------------------------|
| `input_path_image`      | Path to the image (.tiff). Example:  `path/to/project_directory/output_processed/bmark01_R01_V01_COMET_Cy5.tiff`. |
| `output_path_image`   | Path to the output image (.tiff). Example:  `path/to/project_directory/hard_stitching/bmark01/bmark01_R01_V01_COMET_Cy5.tiff`.                  |
| `conversion_factor`    | Conversion factor for downscaling. For example, `4`.                                                              |
| `skip_existing`| Boolean to define whether to skip already existing results. For example, `TRUE`                                   |

---

# AKOYA

----
**Script:** [rebuild_preprocessed_ffc_akoya_list_jobs.R](src/03_hard_stitching/rebuild_preprocessed_ffc_akoya_list_jobs.R) 

### Description
This function lists all the folders in the input directory and generates a csv with the list of jobs that have to be run for coarse stitching.

### Arguments
```
Rscript src/03_hard_stitching/rebuild_preprocessed_ffc_akoya_list_jobs.R --input_path_tiles <input_path_tiles/> --input_path_meta <nput_path_meta/> --output_folder <output_folder/> --output_path_csv <output_path_csv/> --output_pixel_size <output_pixel_size/>  
```

| Argument            | Description                                                                                                                      |
|---------------------|----------------------------------------------------------------------------------------------------------------------------------|
| `input_path_tiles`  | Path to input tiles (dir). Example:  `path/to/project_directory/output_FFC_corrected`                                            |
| `input_path_meta`   | Path to input metadata files (dir). Example:  `path/to/project_directory/output_FFC_corrected`                                   |
| `output_folder`     | Path to output path to save images (dir). Example:  `path/to/project_directory/output_processed`                                 |
| `output_path_csv`   | Path to output csv where the job list will be saved (.csv). Example:  `path/to/project_directory/rebuild_processed_job_list.csv` |
| `output_pixel_size` | Output pixel size (numeric). Example: `0.5`                                                                                      |

---
**Script:** [run_rebuild.py](src/03_hard_stitching/run_rebuild.py) 

### Description
It orchestrates rebuilding the images. It requires the output CSV file of [rebuild_preprocessed_ffc_akoya_list_jobs.R](src/03_hard_stitching/rebuild_preprocessed_ffc_akoya_list_jobs.R) and [01_rebuild_after_ffc.py](src/03_hard_stitching/01_rebuild_after_ffc.py) script  as positional arguments


### Arguments
```
python src/03_hard_stitching/run_rebuild.py <csv_path/> src/03_hard_stitching/01_rebuild_after_ffc.py
```

| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `path/to/project_directory/rebuild_processed_job_list.csv` |

---

**Script:** [01_rebuild_after_ffc.py](src/03_hard_stitching/01_rebuild_after_ffc.py) 

### Description
This function generates an images with a corrected size

### Arguments
```
python src/03_hard_stitching/01_rebuild_after_ffc.py --input_tiles <input_tiles/> --input_metadata <input_metadata/> --output_folder <output_folder/> --conversion_factor <conversion_factor/> --skip_existing <skip_existing/>  
```

| Argument           | Description                                                                                                                                    |
|--------------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_tiles`      | Path to input tiles (dir). Example:  `path/to/project_directory/output_FFC_corrected/bmark01_R01_V01_Akoya`                                    |
| `input_metadata`   | Path to input metadata files (dir). Example:  `path/to/project_directory/output_FFC_corrected/bmark01_R02_V01_Akoya/bmark01_R02_V01_Akoya.csv` |
| `output_folder`    | Path to output path to save images (dir). Example:  `path/to/project_directory/output_processed/bmark01_R01_V01_Akoya`                         |
| `conversion_factor`| Path to output csv where the job list will be saved (.csv). Example:  `1`                                                                      |
| `skip_existing`    | Output pixel size (numeric). Example:  `False`                                                                                                 |

---