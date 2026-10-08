# Flat Filed Correction - Kask

---
<div align="center">

```mermaid
stateDiagram-v2
    classDef coloring fill:#6d9a8a, stroke:#468e74, color:#ffffff
    classDef coloring2 fill:#cdd7d3, stroke:#468e74, color:#ffffff
    
    FFC1 --> FFC2
    FFC2 --> BaSiC
    FFC2 --> Kask
    FFC2 --> Raw_files
    FFC2 --> Metadata
    
    FFC1: Flat Field Correction
    FFC2: Job list preparation
    Raw_files: Raw files
    
    class FFC1, FFC2, Kask coloring
    class BaSiC, Raw_files, Metadata coloring2
    
```

</div>

---

## 1. Input files preparation

---

This function performs FFC with the method described by [Kask et al. (2016)](https://onlinelibrary.wiley.com/doi/10.1111/jmi.12404). Before running the main script that reduces vignetting, it is necessary to prepare all the input files required for this algorithm. 
Therefore, first the course stitching and tissue masks have to be generated.  

---

<div align="center">

```mermaid
stateDiagram-v2
    classDef coloring fill:#6d9a8a, stroke:#468e74, color:#ffffff
    classDef coloring2 fill:#ffffff, stroke:#6d9a8a

    FFC1 --> FFC2
    FFC2 --> MILAN
    FFC2 --> AKOYA
    AKOYA --> Mask_generation
    MILAN --> Coarse_stitching
    Coarse_stitching --> Mask_generation
    Mask_generation --> Kask
    FFC1: Flat Field Correction
    FFC2: Job list preparation
    Kask: FFC_Kask.py
    
    state Coarse_stitching{
      Joblist --> HS_script
      Joblist: 1. hard_stitching_list_jobs.py
      HS_script: 2. hard_stitching.py
    }
    
    state Mask_generation{
      Joblist2 --> mask_script
      Joblist2: 1. mask_generation_list_jobs.py
      mask_script: 2. STS_generate_mask.py
    }

    class Joblist, HS_script, FFC1, FFC2, Joblist2, mask_script, MILAN, AKOYA, Kask coloring
    class Coarse_stitching, Mask_generation coloring2

```
</div>

---

#### **Coarse stitching scripts:**
   - [hard_stitching_list_jobs.py](https://github.com/antoranzlab/DISSCOvery/blob/main/src/03_hard_stitching/hard_stitching_list_jobs.py) 
   - [hard_stitching.py](https://github.com/antoranzlab/DISSCOvery/blob/main/src/03_hard_stitching/hard_stitching.py)
   
#### **Mask generation scripts:**
   - [mask_generation_list_jobs.py](https://github.com/antoranzlab/DISSCOvery/blob/main/src/04_STS/mask_generation_list_jobs.py) 
   - [STS_generate_mask.py](https://github.com/antoranzlab/DISSCOvery/blob/main/src/04_STS/STS_generate_mask.py)


---

## 2. FFC Kask

#### **Script 1:** [FFC_Kask.py](https://github.com/antoranzlab/DISSCOvery/blob/main/src/02_FFC/FFC_Kask.py)

``` shell
python src/02_FFC/FFC_Kask.py \
    --input_images <path_to_tiles/> \
    --input_metadata <path_to_metadata/> \
    --input_mask <path_to_mask/> \
    --pixel_size <pixel_size_in_mask/> \
    --channel <channel_identifier/> \
    --output_path_corrected_tiles <path_to_corrected_tiles/> \
    --output_path_templates <path_to_templates/> \
    --n_cores <number_of_cores/>
```

`--input_images`
: Path to the input directory where the raw tiles are stored (dir). Example: `/path/to/project_directory/output_tiles_tiffs/test_R00_V01_BENCHMARK_ND`

`--input_metadata`
: Path to the CSV where the metadata is stored (.csv). Example: `/path/to/project_directory/output_tiles_tiffs/test_R00_V01_BENCHMARK_ND/test_R00_V01_BENCHMARK_ND.csv`

`--input_mask`
: Path to the TIFF file where the mask is stored (.tiff). Example: `/path/to/project_directory/output_FFC_kask_masks/test/test_R00_V01_BENCHMARK_ND_DAPI.tiff`

`--pixel_size`
: Pixel size used for the mask (numeric). Example: `2.6`

`--channel`
: Channel identifier (str). Example: `DAPI`

`--output_path_corrected_tiles`
: Path to the output directory where the corrected tiles will be stored (dir). Example: `/path/to/project_directory/output_FFC_corrected/test_R00_V01_BENCHMARK_ND`

`--output_path_templates`
: Path to the output directory where the correction templates will be stored (dir). Example: `/path/to/project_directory/output_FFC_templates/KASK/test_R00_V01_BENCHMARK_ND`

`--n_cores`
: Number of cores to use (numeric). Example: `10`


---

