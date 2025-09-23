<h1 align="center"> Qual-IF-AI (QC) </h1>

---

<pre> 
03_QC 
├── MILAN
    ├── 1. qualifai_list_jobs_multiclass.R
    └── 2. run_QC.py
        └── QUALIFAI.py

</pre>

----

 **Script:** [qualifai_list_jobs_multiclass.R](src/03_QC/qualifai_list_jobs_multiclass.R) 

### Description
TThis function takes as an input the directory of a hard stitched, full resolution images, or equivalent, and lists all the jobs to be run with QUALIFAI

### Arguments
```
Rscript src/03_QC/qualifai_list_jobs_multiclass.R --input_folder_path <path_to_input_images/> --output_folder_path <path_to_output_images/> --model_path <loaded_mode/> --output_path_csv <path_to_output_csv/> 
```
| Argument             | Description                                                                                                                          |
|----------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `input_folder_path`   | Path to the parent directory where the input images are stored (dir). Example: `/path/to/project_directory/hard_stitching_full_res`. |
| `input_path_meta`    | Path to the directory where the output masks will be stored (dir). Example: `/path/to/project_directory/output_QC`                   |
| `output_folder`      | Path to the model to identify artifacts (pth). Example: `/src/03_QC/model_20_DAPI_resnet34_currated/unetpp_best.pth`                 |
| `output_path_csv`    | Path to the CSV where the list of jobs will be saved (.csv). Example:  `/path/to/project_directory/qualifai_list_jobs.csv`           |

---

**Script:** [QUALIFAI.py](src/03_QC/QUALIFAI.py) 

### Description
This function generates a multiclass mask of the same size as the input image.

### Arguments
```
python src/03_QC/QUALIFAI.py --input_image_path <path_to_the_input_image/> --output_image_path <path_to_the_output_mask/> --model_path <<loaded_mode/> 
```

| Argument           | Description                                                                                                                                            |
|--------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_image_path`      | Path to the folder where the full resolution, hard stitched images are stored (dir). Example: `/path/to/project_directory/hard_stitching_full_res/BM`. |
| `output_image_path`    | Path to the folder where the masks will be stored (dir). Example: `/path/to/project_directory/output_QC`.                                              |
| `model_path`        | Path to the output directory where the AI model is saved (.pth). Example: `/src/03_QC/model_20_DAPI_resnet34_currated/unetpp_best.pth`                 |

---

**Script:** [run_QC.py](src/03_QC/run_QC.py) 

### Description
It orchestrates quality checking. It requires the output CSV file of [qualifai_list_jobs_multiclass.R](src/03_QC/qualifai_list_jobs_multiclass.R) and [QUALIFAI.py](src/03_QC/QUALIFAI.py) script  as positional arguments


### Arguments
```
python src/03_QC/run_QC.py <csv_path/> src/03_QC/QUALIFAI.py
```

| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/qualifai_list_jobs.csv` |


