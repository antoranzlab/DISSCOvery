<h1 align="center"> Feature Extraction </h1>

---

<pre> 
11_feature_extraction
    └──  1. FeatureExtraction.py

</pre>

---

**Script:** [FeatureExtraction.py](src/10_feature_extraction/FeatureExtraction.py) 

### Description

This quantifies the signal for each slide and scene.  

### Arguments
```
python src/10_feature_extraction/FeatureExtraction.py --path_input_AFS <path_to_input_AFS/> --path_exp_design_rounds <exp_design_rounds/> --path_input_seg <path_input_segmentation/> --ref_round <reference_round/> --path_output_csv <path_output_csv/>
```

| Argument        | Description                                                                                                                                    |
|-----------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| `path_input_AFS`  | Path to input AFS images (dir). Example: `/path/to/project_directory/output_AFS_images`  .                                                     |
| `path_exp_design_rounds` | Path to input experimental design for the rounds (.csv). Example: `/path/to/project_directory/experimental_design/exp_design_rounds.csv`.      |
| `path_input_seg`  | Path to input segmentation matrices (dir). Example: `output_registration/output_segmentation/Matrix`.                                          |
| `ref_round`  | Round of reference used during segmentation (string). Example: `R01`.                                                                          |
| `path_output_csv` | Path to output feature extracted tables (dir). Example: `/path/to/project_directory/output_feature_extraction`. |

---