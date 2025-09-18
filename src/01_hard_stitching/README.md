<h1 align="center"> MILAN Coarse Stitching </h1>

---

<pre> 01_hard_stitching 
├── MILAN
|    1. 01_hard_stitching_list_jobs.R
|    2. run_hs.py
|         └── 01_hard_stitching.py

</pre>

----

 **Script:** [01_hard_stitching_list_jobs.R](01_hard_stitching/01_hard_stitching_list_jobs.R)  # Add path 

### Description
This script generates coarse stitched images from the individual tiles. 
This coarse stitched image is used for Smart Tissue Detection (STS) and for generating input files for FFC Kask method. 

### Arguments
```
Rscript src/01_hard_stitching_list_jobs.R --input_path_tiles <path_to_tiles/> --input_path_meta <path_to_metadata/> --output_folder <path_to_output_images/> --output_path_csv <path_to_output_csv/> --output_pixel_size <pixel_size_output_images/> --_skip_existing <skip_existing/> --only_dapi <do_only_dapi/> 
```
| Argument             | Description                                                                                                                                                                                        |
|----------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_path_tiles`   | Path to the parent directory where the tiles are stored (dir). Example: `/path/to/project_directory/output_tiles_tiffs`. It can also use the output of FFC.                                        |
| `input_path_meta`    | Path to the parent directory where the metadata is stored (dir). Example: `/path/to/project_directory/output_tiles_tiffs`                                                                          |
| `output_folder`      | Path to the folder where the hard stitched images will be stored (dir). Example: `/path/to/project_directory/hard_stitching`.                                                                      |
| `output_path_csv`    | Path to the CSV where the list of jobs will be saved (.csv). Example: `/path/to/project_directory/hard_stitching_job_list.csv`.                                                                    |
| `output_pixel_size`  | Pixel size for output images (numeric). Used to calculate conversion factor between real and reduced dimensions. For STS/FFC Kask the recommended value is 2.6, for QUALIFAI 0.65. Example: `2.6`. |
| `skip_existing`     | Boolean to skip already existing results (str). Example: `True`.                                                                                                                                   |
| `only_dapi`          | Boolean indicating whether to process only DAPI (str). Example: `True`.                                                                                                                            |

---

**Script:** [01_hard_stitching.py](01_hard_stitching/01_hard_stitching.py) 

### Description
This function generates a hard stitched image.

### Arguments
```
python src/01_hard_stitching.py --input_tiles <path_to_tiles/> --input_metadata <path_to_metadata/> --output_folder <path_to_output/> --conversion_factor <conversion_factor/> --skip_existing <skip_existing/> --only_dapi <do_only_dapi/> 
```

| Argument           | Description                                                                                                                                                                       |
|--------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_tiles`      | Path to the folder where the tiles are stored (dir). Example: `/path/to/project_directory/output_tiles_tiffs/BM_R00_V01_BENCHMARK_ND`.                                            |
| `input_metadata`   | Path to the CSV file where the metadata is stored (.csv). Example: `/path/to/project_directory/output_tiles_tiffs/BM_R00_V01_BENCHMARK_ND/full_BM_R00_V01_BENCHMARK_ND_meta.csv`. |
| `output_folder`    | Path to the folder where the hard stitched images will be stored (dir). Example: `/path/to/project_directory/hard_stitching/BM`.                                               |
| `conversion_factor`| Conversion factor for downscaling (numeric). Example: `4`.                                                                                                                        |
| `skip_existing`    | Boolean to define whether to skip already existing results (string). Example: `True`.                                                                                             |
| `only_dapi`        | Boolean indicating whether to perform hard stitching only on DAPI (string). Example: `True`.                                                                                      |

---

**Script:** [run_hs.py](01_hard_stitching/run_hs.py) 

### Description
It orchestrates coarse stitching. It requires the output CSV file of [01_hard_stitching_list_jobs.R](01_hard_stitching/01_hard_stitching_list_jobs.R) and [01_hard_stitching.py](01_hard_stitching/01_hard_stitching.py) script  as positional arguments


### Arguments
```
python src/run_hs.py <csv_path/> 01_hard_stitching.py
```

| Argument                 | Description                                                                                                                          |
|--------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| `csv_path`              | Path to the output CSV file where the list of jobs is stored (.csv). Example: `/path/to/project_directory/hard_stitching_job_list.csv` |


