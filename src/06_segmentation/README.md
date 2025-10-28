<h1 align="center"> Segmentation </h1>

---

<pre> 
06_segmentation
├── MILAN
    ├── 1. segmentation_list_jobs.R
    └── 2. run_segmentation.py
        └── segmentation.py
</pre>

---

[//]: # ( **Script:** [segmentation_list_jobs.R]&#40;src/06_segmentation/segmentation_list_jobs.R&#41; )

[//]: # ()
[//]: # (### Description)

[//]: # ()
[//]: # (This function resizes the input images and lists all the paths for input and output files then generates a csv with the list of jobs that have to be run for segmentation)

[//]: # ()
[//]: # (### Arguments)

[//]: # (```)

[//]: # (    Rscript src/06_segmentation/segmentation_list_jobs.R --input_path_images <path_to_input_images/> --output_folder <path_to_output_directory/> --ref_round <reference_round/> --conversion_factor <conversion_factor/> --output_path_csv <path_to_job_list/>)

[//]: # (```)

[//]: # ()
[//]: # (| Argument             | Description                                                                                                                |)

[//]: # (|----------------------|----------------------------------------------------------------------------------------------------------------------------|)

[//]: # (| `input_path_images`   | Path to input tiles &#40;dir&#41;. Example: `/path/to/project_directory/output_registration`                               |)

[//]: # (| `output_folder`   | Path to output path to save images &#40;dir&#41;. Example: `/path/to/project_directory/output_segmentation`                   |)

[//]: # (| `ref_round`        | Reference round for segmentation &#40;str&#41;. Example: `R01`                         |)

[//]: # (| `conversion_factor`   | Conversion factor &#40;numeric&#41;. Example: `1` |)

[//]: # (| `output_path_csv`        | Path to output csv where the job list will be saved &#40;.csv&#41;. Example: `/path/to/project_directory/cell_segmentation_joblist.csv`     |)

[//]: # ()
[//]: # (---)

[//]: # ()
[//]: # (**Script:** [SEGMENTATION_v3.py]&#40;src/06_segmentation/SEGMENTATION_v3.py&#41; )

[//]: # ()
[//]: # (### Description)

[//]: # ()
[//]: # (This script performs cell segmentation )

[//]: # ()
[//]: # (### Arguments)

[//]: # (```)

[//]: # (python src/06_segmentation/SEGMENTATION_v3.py --path_to_the_image <path_to_input_image/> --path_to_the_models <path_to_input_models/> --model_name <model_identifier/> --output_path <path_to_output_segmentation_matrix/> --QC_path <path_to_output_qc_plot/> --PP <preprocessing/>)

[//]: # (```)

[//]: # ()
[//]: # (| Argument       | Description                                                                                                                                               |)

[//]: # (|----------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|)

[//]: # (| `path_to_the_image`  | Path to the input image &#40;.tiff&#41;. Example: `/path/to/project_directory/output_segmentation/Resized/BM_R01_V01_BENCHMARK/BM_R01_V01_BENCHMARK_DAPI.tiff`  . |)

[//]: # (| `path_to_the_models` | Path to the models &#40;dir&#41;. Example: `src/06_segmentation/models`.                                                                                          |)

[//]: # (| `model_name` | Model you want to use &#40;str&#41;. Example: `stardist4`.                                                                                                        |)

[//]: # (| `output_path`  | Path for the labeled matrix &#40;dir&#41;. Example: `/path/to/project_directory/output_segmentation/Matrix/BM_R01_V01_BENCHMARK/BM_R01_V01_BENCHMARK_DAPI.npy`.   |)

[//]: # (| `QC_path` | Path for the QC image &#40;dir&#41;. Example: `/path/to/project_directory/output_segmentation/QC/BM/BM_R01_V01_BENCHMARK_DAPI.tiff`.                              |)

[//]: # (| `PP` | Preprocessing indicator &#40;boolean&#41;. Example: `True`.                                                                                                       |)

[//]: # ()
[//]: # (---)

[//]: # ()
[//]: # (**Script:** [run_segmentation.py]&#40;src/06_segmentation/run_segmentation.py&#41; )

[//]: # ()
[//]: # (### Description)

[//]: # (It orchestrates AFS. It requires the output CSV file of [segmentation_list_jobs.R]&#40;src/06_segmentation/segmentation_list_jobs&#41;, path to models, model name, preprocessing indicator and [SEGMENTATION_v3.py]&#40;src/06_segmentation/SEGMENTATION_v3.py&#41; script  as positional arguments)

[//]: # ()
[//]: # (### Arguments)

[//]: # ()
[//]: # (```)

[//]: # (python src/06_segmentation/run_segmentation.py <csv_path/> <path_to_input_models/> <model_identifier/> <preprocessing/> src/06_segmentation/segmentation_list_jobs )

[//]: # (```)

[//]: # ()
[//]: # (| Argument                 | Description                                                                                                                         |)

[//]: # (|--------------------------|-------------------------------------------------------------------------------------------------------------------------------------|)

[//]: # (| `csv_path`              | Path to the output CSV file where the list of jobs is stored &#40;.csv&#41;. Example: `/path/to/project_directory/cell_segmentation_joblist.csv` |)

[//]: # (| `path_to_the_models` | Path to the models &#40;dir&#41;. Example: `src/06_segmentation/models`.                                                                                          |)

[//]: # (| `model_name` | Model you want to use &#40;str&#41;. Example: `stardist4`.                                                                                                        |)

[//]: # (| `PP` | Preprocessing indicator &#40;boolean&#41;. Example: `True`.                                                                                                       |)

[//]: # ()
[//]: # ()
[//]: # (---)