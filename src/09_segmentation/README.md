<h1 align="center"> Cell segmentation </h1>

---
<pre> 
09_segmentation
├── 1. segmentation_list_jobs.R
└── 2. run_segmentation.py
    └── segmentation.py

</pre>
---

 **Script:** [segmentation_list_jobs.R](src/09_segmentation/segmentation_list_jobs.R) 

### Description

This function resizes the input images, lists all the paths for input and output files and generates a csv with the list of jobs that have to be run for segmentation

### Arguments

```
Rscript src/09_segmentation/segmentation_list_jobs.R --input_path_images <path_to_input_images/> --output_folder <path_to_output_directory/> --ref_round <reference_round/> --conversion_factor <conversion_factor/> --path_model <path_to_models/> --model_name <model_name/> --pp <preprocessing_indicator/> --output_path_csv <path_to_job_list/>
```

| Argument           | Description                                                                                                                     |
|--------------------|---------------------------------------------------------------------------------------------------------------------------------|
| `input_path_images` | Path to input tiles (dir). Example: `/path/to/project_directory/output_registration`                                            |
| `output_folder`    | Path to output path to save images (dir). Example: `/path/to/project_directory/output_segmentation`                             |
| `ref_round`        | Reference round for segmentation (str). Example: `R01`                                                                          |
| `conversion_factor` | Conversion factor (numeric). Example: `1`                                                                                       |
| `path_model`       | Path to segmentation models. Example: `models/09_models`                                                                        |
| `model_name`       | Name of the model. Example: `stardist` or `cellpose`                                                                            |
| `pp`               | Indicator for the preprocessing. Example: `False`                                                                               |
| `output_path_csv`  | Path to output csv where the job list will be saved (.csv). Example: `/path/to/project_directory/cell_segmentation_joblist.csv` |

---
**Script:** [run_segmentation.py](src/09_segmentation/run_segmentation.py) 

### Description

It orchestrates cell segmentation. It requires the output CSV file of [segmentation_list_jobs.R](src/09_segmentation/segmentation_list_jobs), and [segmentation.py](src/09_segmentation/segmentation.py) script  as positional arguments

### Arguments

```
python src/09_segmentation/run_segmentation.py <csv_path/>  src/09_segmentation/segmentation.py
```


| Argument                 | Description                                                                                                                         |
|--------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/cell_segmentation_joblist.csv` |

---
**Script:** [segmentation.py](src/09_segmentation/segmentation.py) 


### Description

This script performs cell segmentation using either StarDist or Cellpose

### Arguments

```
python src/09_segmentation/segmentation.py --path_to_the_image <path_to_input_image/> --path_to_the_models <path_to_input_models/> --model_name <model_identifier/> --output_path <path_to_output_segmentation_matrix/> --QC_path <path_to_output_qc_plot/> --PP <preprocessing/>
```

| Argument       | Description                                                                                                                                               |
|----------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| `path_to_the_image`  | Path to the input image (.tiff). Example: `/path/to/project_directory/output_segmentation/Resized/BM_R01_V01_BENCHMARK/BM_R01_V01_BENCHMARK_DAPI.tiff`  . |
| `path_to_the_models` | Path to the models (dir). Example: `src/09_segmentation/models`.                                                                                          |
| `model_name` | Model you want to use (str). Example: `stardist4` or `cellpsoe`                                                                                           |
| `output_path`  | Path for the labeled matrix (dir). Example: `/path/to/project_directory/output_segmentation/Matrix/BM_R01_V01_BENCHMARK/BM_R01_V01_BENCHMARK_DAPI.npy`.   |
| `QC_path` | Path for the QC image (dir). Example: `/path/to/project_directory/output_segmentation/QC/BM/BM_R01_V01_BENCHMARK_DAPI.tiff`.                              |
| `PP` | Preprocessing indicator (boolean). Example: `False`.                                                                                                      |

---

