<h1 align="center"> Autofluorescence Subtraction (AFS) </h1>

---

<pre> 
08_AFS
├── 1. AFS_list_jobs.R
└── 2. run_AFS.py
    └── AutofluorescenceSubtraction.py
</pre>

---

 **Script:** [AFS_list_jobs.R](src/08_AFS/AFS_list_jobs.R) 

### Description

This function lists all the paths for input and output files and generates a csv with the list of jobs that have to be run for AFS

### Arguments
```
Rscript src/08_AFS/AFS_list_jobs.R --input_path_images <path_to_input_images/> --input_path_medoids <path_to_medoids_file/> --output_folder <path_to_output_director/> --output_folder_qc <path_to_output_qc_directory/> --exp_design_rounds <path_to_exp_design_rounds/> --output_path_csv <path_to_job_list/>
```

| Argument             | Description                                                                                                                                                    |
|----------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_images`   | Path to input tiles (dir). Example: `/path/to/project_directory/output_registration` (for MILAN),  `/path/to/project_directory/split_scenes` (for COMET/AKOYA) |
| `input_path_medoids`        | Path to input medoids (.csv). Example: `src/auxiliary functions/AFS/medoid_series.csv`                                                                         |
| `output_folder`   | Path to output path to save images (dir). Example: `/path/to/project_directory/output_AFS_images`                                                              |
| `output_folder_qc`        | Path to output path to save qc plots (dir). Example: `/path/to/project_directory/output_AFS_QC`                                                                |
| `exp_design_rounds`   | Experimental design for the rounds (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_rounds.csv`                                     |
| `output_path_csv`        | Path to output csv where the job list will be saved (.csv). Example: `/path/to/project_directory/afs_job_list.csv`                                             |

---
**Script:** [run_AFS.py](src/08_AFS/run_AFS.py) 

### Description
It orchestrates AFS. It requires the output CSV file of [AFS_list_jobs.R](src/08_AFS/AFS_list_jobs.R) and [AutofluorescenceSubtraction.py](src/08_AFS/AutofluorescenceSubtraction.py) script  as positional arguments

### Arguments

```
python src/08_AFS/run_AFS.py <csv_path/> src/08_AFS/AutofluorescenceSubtraction.py
```

| Argument                 | Description                                                                                                                         |
|--------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/afs_job_list.csv` |

---

**Script:** [AutofluorescenceSubtraction.py](src/08_AFS/AutofluorescenceSubtraction.py) 

### Description

This script subtracts teh autofluorescence signal from the image. 

### Arguments
```
python src/08_AFS/AutofluorescenceSubtraction.py --input_path_medoids <path_to_input_measured_signal/> --input_path_MS <path_to_input_autofluorescence_image/> --input_path_AF <path_to_input_autofluorescence_image/> --output_path_TS <path_to_output_true_signal/> --output_path_QC <path_to_output_quality_control_image/>
```

| Argument        | Description                                                                                                                                               |
|-----------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_medoids`   | Path to input medoids (.csv). Example: `src/auxiliary functions/AFS/medoid_series.csv`  .                                                                 |
| `input_path_MS` | Path to input MS image (.tiff). Example: `/path/to/project_directory/output_registration/BM_R02_V01_BENCHMARK_ND_S0/BM_R02_V01_BENCHMARK_ND_S0_CY5.tiff`. |
| `input_path_AF`  | Path to input AF image (.tiff). Example: `output_registration/BM_R01_V01_BENCHMARK/BM_R01_V01_BENCHMARK_FITC.tiff`.                                       |
| `output_path_TS`   | Path to output TS image (.tiff). Example: `/path/to/project_directory/output_AFS_images/BM_R02_V01_BENCHMARK/BM_R02_V01_BENCHMARK_FITC.tiff`.             |
| `output_path_QC` | Path to output QC image (.tiff). Example: `/path/to/project_directory/output_AFS_QC/marker_name/BM_R02_V01_BENCHMARK_FITC.tiff`.                          |

---