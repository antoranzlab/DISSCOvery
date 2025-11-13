<h1 align="center"> Cell identification </h1>

---

## Table of content

<pre> 
11_cell_identification 
 └──┌── 1. MergeData.R
    ├── 2. DataNormalization.R
    ├── 3. DataSampling.R
    ├── 4. DimensionalityReduction.R
    ├── 5. Clustering.R
    ├── 6. ClusteringAnalysis.R
    ├── 7. ClusteringStability.R
    ├── 8. MapFingerprints_training.R
    ├── 9. MapFingerprints_testing.R
    ├── 10. MapFingerprints_post.R
    ├── 11. DigitalReconstruction_generate_csv.R -> TO DO, FILE IS MISSING
    └── 12. DataFiltering.R

</pre>

---

# 1. Merge Data

---

**Script:** [MergeData.R](src/11_cell_identification/MergeData.R)


### Description
This function takes all the csvs listed in input folder, filters the scenes from the input with positive quality control flag and saves the data in csv file. Additionally, it generates an output.qc file that ensures successful execution of the subsequential scripts
### Arguments
```
Rscript src/11_cell_identification/MergeData.R --path.input.folder <path.input.folder/> --path.input.exp.design.scenes <path.input.exp.design.scenes/> --path.output.qc <path_to_output_qc/> --path.output.csv <path_to_output_csv/>  
```

| Argument           | Description                                                                                                                                                              |
|--------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `path.input.folder` | Path to the input folder where the csvs from feature extraction are located (dir). Example: `/path/to/project_directory/output_feature_extraction/feature_extraction.csv` |
| `path.input.exp.design.scenes`| Path to the input excel where the experimental design for the scenes is stored (.xlsx). Example: `/path/to/project_directory/experimental_design/exp_design_scenes.xlsx` |
| `path.output.qc`    | Path to output QC file (.csv). Example: `/path/to/project_directory/output_cell_identification/df_data_qc.csv`                                                                       |
| `path.output.csv`      | Path to the output csv where the merged cell data will be stored (.csv). Example: `/path/to/project_directory/output_cell_identification/df_data_merged.csv`  |

---

**Script:** [DataNormalization.R](src/11_cell_identification/DataNormalization.R)


### Description
It takes the csv file created with `MergeData.R` and if the variable `normalization.yes.no` is set to 1,  it normalizes mean fluorescence intensity (MFI) values to z-scores. 
The normalization is performed per scene. Z-scores are later trimmed into the [-5, +5] range. If `normalization.yes.no` is set to 0, the script saves the values in csv without normalization.

### Arguments
```
Rscript src/11_cell_identification/DataNormalization.R --path.input.csv <path.input.csv/> --normalization.yes.no <normalization_variable/> --path.output.csv <path.output.csv/> 
```

| Argument           | Description                                                                                                                           |
|--------------------|---------------------------------------------------------------------------------------------------------------------------------------|
| `path.input.csv` | Path to input csv file (.csv). Example: `/path/to/project_directory/output_cell_identification/df_data_merged.csv`                    |
| `normalization.yes.no`| Normalization yes (1) or no (0) (binary). Example: `1`                                                                                |
| `path.output.qc`    | Path to output csv with normalized data (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/df_data_norm.csv` |

---

**Script:** [DataSampling.R](src/11_cell_identification/DataSampling.R)


### Description
This function takes the csv file created with `DataNormalization.R` and if the variable `sampling.yes.no` is set to 1, it samples the number of cells defined in `number.of.cells` following a stratified random sampling approach. 
If the number of cells to be sampled are more than the total number of cells, the total number of cells is taken. If `sampling.yes.no` is set to 0, it saves the csv without sampling.

### Arguments
```
Rscript src/11_cell_identification/DataSampling.R --path.input.csv <path.input.csv/> --path.output.csv <path.output.csv/> --sampling.yes.no <sampling_variable/> --number.of.cells <number.of.cells/> --selected.seed <selected.seed/>
```

| Argument           | Description                                                                                                                             |
|--------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| `path.input.csv` | Path to input csv (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/df_data_norm.csv`                         |
| `path.output.csv`| Path to output csv where sampled data will be stored (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/df_data_sampled.csv` |
| `sampling.yes.no`    | Binary specifying if sampling needs to be performed (binary). Example: `1`  |
| `number.of.cells`    | Number of cells to be sampled (integer). Example: `25000`           |
| `selected.seed`    | Seed for sampling. Example: `1234`                |

---

**Script:** [DimensionalityReduction.R](src/11_cell_identification/DimensionalityReduction.R)


### Description
Using the sampled data, the set of user-selected markers are taken and a dimensionality reduction (DR) method is applied (to be chosen between PCA, tsne, and umap).
This function is executed 3 times, once per DR method.

### Arguments
```
Rscript src/11_cell_identification/DimensionalityReduction.R --input.marker.list <marker_list/> --path.input.csv <path.input.csv/> --path.output.csv <path.output.csv/> --path.output.model <path_to_output_model/> --dimensionality.reduction.method <DR_method_name/>
```

| Argument           | Description                                                                                                                                                                       |
|--------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input.marker.list` | Path to input csv where the markers selected for the clustering are saved (.csv). Example: `/path/to/project_directory/output_cell_identification/phenotypic_markers_n01_v01.csv` |
| `path.input.csv`| Path to input csv with sampled data (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/df_data_sampled.csv`                                              |
| `path.output.csv`    | Path to output csv where the results from the DR will be stored (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/uMap.csv`                         |
| `path.output.model`    | Path to output model where the DR model will be stored (.rds). Example: `/path/to/project_directory/output_cell_identification/n01/v01/uMap.rds`                                  |
| `dimensionality.reduction.method`    | DR method to be used (string). Example: `uMap`, `tsne` or `PCA`                                                                                                                    |

The `phenotypic_markers.csv` file contains one column, `marker_id`, with the list of markers that will be used for the clustering. Example:

```
marker_id
SOX2
CD4
CD3
CD8
PANCK
```

---

**Script:** [Clustering.R](src/11_cell_identification/Clustering.R)


### Description
Using the sampled data, the set of user-selected markers are taken and a clustering method is applied (to be chosen between phenograph, kmeans, and flowsom).
This function is executed 3 times, once per clustering method.

### Arguments
```
Rscript src/11_cell_identification/Clustering.R --input.marker.list <marker_list/> --path.input.csv <path.input.csv/> --path.output.csv <path.output.csv/> --clustering.method <clustering_method/> --number.of.clusters <number_of_clusters/>
```

| Argument           | Description                                                                                                                                                                        |
|--------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input.marker.list` | Path to input csv where the markers selected for the clustering are saved  (.csv). Example: `/path/to/project_directory/output_cell_identification/phenotypic_markers_n01_v01.csv` |
| `path.input.csv`| Path to input csv with sampled data (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/df_data_sampled.csv`                                               |
| `path.output.csv`    | Path to output folder where the results from the clustering will be stored (dir). Example: `/path/to/project_directory/output_cell_identification/n01/v01/phenograph.csv`          |
| `clustering.method`    | Clustering method to be applied (string). Example: `phenograph`, `flowsom` or `kmeans`                                                                                                     |
| `number.of.clusters`    | Number of clusters (integer). Example: `30`                                                                                                                                        |

---

**Script:** [ClusteringAnalysis.R](src/11_cell_identification/ClusteringAnalysis.R)


### Description
The results from DimensionalityReduction.R and Clustering.R are evaluated and several graphs are generated to be displayed on the GUI.

### Arguments
```
Rscript src/11_cell_identification/ClusteringAnalysis.R --input.marker.list <marker_list/> --path.input.csv <path.input.csv/> --path.input.pca <path.input.pca/> --path.input.tsne <path.input.tsne/> --path.input.umap <number_of_clusters/> --path.input.phenograph <path.input.phenograph/> --path.input.kmeans <path.input.kmeans/> --path.input.flowsom <path.input.flowsom/> --path.annotation.dictionary <path.annotation.dictionary/> --generate.marker.plots <generate.marker.plots/> --path.output.folder <ath.output.folder/>
```

| Argument                     | Description                                                                                                                                                   |
|------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input.marker.list`          | Path to input csv where the markers selected for the clustering are saved (.csv).Example: `/path/to/project_directory/output_cell_identification/phenotypic_markers_n01_v01.csv`               |
| `path.input.csv`             | Path to input csv with sampled data (.csv).Example: `/path/to/project_directory/output_cell_identification/n01/df_data_sampled.csv`                           |
| `path.input.pca`             | Path to input csv with PCA data, if existing (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/pca.csv`                         |
| `path.input.tsne`            | Path to input csv with tSNE data, if existing (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/tsne.csv`                       |
| `path.input.umap`            | Path to input csv with uMap data, if existing (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/uMap.csv`                       |
| `path.input.phenograph`      | Path to input csv with PhenoGraph data (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/phenograph.csv`                        |
| `path.input.kmeans`          | Path to input csv with KMeans data (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/kmeans.csv`                                |
| `path.input.flowsom`         | Path to input csv with FlowSom data (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/flowsom.csv`                              |
| `path.annotation.dictionary` | Path to input csv where the annotations are stored (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/annotation_dictionary.csv` |
| `generate.marker.plots`      | Binary describing if marker plots need to be generated (binary). Example: `1`                                                                                |
| `path.output.folder`         | Path to output folder where plots will be saved (dir). Example: `/path/to/project_directory/output_cell_identification/n01/v01`                               |

---

**Script:** [ClusteringStability.R](src/11_cell_identification/ClusteringStability.R)


### Description
This function evaluates the annotations made for each cluster in each clustering method and builds the consensus.

### Arguments
```
Rscript src/11_cell_identification/ClusteringStability.R --path.input.phenograph <path.input.phenograph/> --path.input.kmeans <path.input.kmeans/> --path.input.flowsom <path.input.flowsom/> --path.annotation.dictionary <path.annotation.dictionary/> --path.output.folder <path.output.folder/> 
```

| Argument           | Description                                                                                                                                                                |
|--------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `path.input.phenograph` | Path to input csv with PhenoGraph data (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/phenograph.csv` |
| `path.input.kmeans`| Path to input csv with KMeans data (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/kmeans.csv`     |
| `path.input.flowsom`    | Path to input csv with FlowSom data (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/flowsom.csv`    |
| `path.annotation.dictionary`    | Path to input csv where the annotations are stored (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/annotation_dictionary.csv`              |
| `path.output.folder`    | Path to output folder where the results from the clustering consensus will be stored (dir). Example: `/path/to/project_directory/output_cell_identification/n01/v01`       |

---

**Script:** [MapFingerprints_training.R](src/11_cell_identification/MapFingerprints_training.R)


### Description
This function generates a umap template from the consensus data, reannotates the consensus clustering results that were based on the KNN, fine-tunes the template based on the reannotations, and generates all the auxiliary files to project the complete dataset in a parallel setup.

### Arguments
```
Rscript src/11_cell_identification/MapFingerprints_training.R --input.marker.list <input.marker.list/> --path.input.csv.annotated <path.input.csv.annotated/> --path.input.csv.complete <path.input.csv.complete/> --path.output.folder <path.output.folder/> --path.output.partitions <path.output.partitions/> --path.output.tmp.results <path.output.tmp.results/> --number.of.cores <number.of.cores/> --number.of.cells <number.of.cells/> --selected.seed <selected.seed/>
```

| Argument           | Description                                                                                                                                                              |
|--------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input.marker.list` | Path to the csv where the markers used for clustering are defined (.csv). Example: `/path/to/project_directory/output_cell_identification/phenotypic_markers_n01_v01.csv` |
| `path.input.csv.annotated`| PPath to the csv with the annotated data (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/df_data_consensus.csv`                          |
| `path.input.csv.complete`    | Path to input csv with complete data (normalized data). Example: `/path/to/project_directory/output_cell_identification/n01/df_data_norm.csv`                            |
| `path.output.folder`    | Path to output folder with some temporal data will be stored (dir). Example: `/path/to/project_directory/output_cell_identification/n01/v01`                             |
| `path.output.partitions`    | Path to output directory where partition data will be stored (dir). Example: `/path/to/project_directory/output_cell_identification/n01/v01/tmp_partitions`              |
| `path.output.tmp.results`| Path to output directory where the intermediate results will be stored (dir). Example: `/path/to/project_directory/output_cell_identification/n01/v01/tmp_results`       |
| `number.of.cores`    | Number of cores for the training (integer). Example: `10`                                                                                                                |
| `number.of.cells`    | Number of cells from each category sampled to generate the umap template. Maximum is equal to 500 (integer). Example: `500`                                              |
| `selected.seed`    | Seed for reproducibility (integer). Example: `1234`                                                                                                                      |

---

**Script:** [MapFingerprints_testing.R](src/11_cell_identification/MapFingerprints_testing.R)


### Description
This function takes all the partitions saved in the previous step and projects them into the model.
Then, it  applies a knn approach to assign a new label to the cells based on the annotated data. The function only executes one job at once, therefore it needs to be orchestrated from outside
### Arguments
```
Rscript src/11_cell_identification/MapFingerprints_testing.R --input.marker.list <input.marker.list/> --path.input.csv.training <path.input.csv.training/> --path.input.csv.testing <path.input.csv.testing/> --path.input.model <path.input.model/> --path.output.folder <path.output.folder/>
```

| Argument          | Description                                                                                                                                                              |
|-------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input.marker.list` | Path to the csv where the markers used for clustering are defined (.csv). Example: `/path/to/project_directory/output_cell_identification/phenotypic_markers_n01_v01.csv`                        |
| `path.input.csv.training`| Path to the csv with the training data (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/tmp_results/training_data.csv`                                  |
| `path.input.csv.testing`   | Path to the input csv where the training data is stored (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/tmp_partitions/iter_1.csv`    |
| `path.input.model`    | Path to input csv where the complete data is stored (.rds). Example: `/path/to/project_directory/output_cell_identification/n01/v01/tmp_results/tmp_umap.rds`      |
| `path.output.folder`   | Path to the output directory where the results will be stored (dir). Example: `/path/to/project_directory/output_cell_identification/n01/v01/tmp_partitions_annotated`    |

---

**Script:** [MapFingerprints_post.R](src/11_cell_identification/MapFingerprints_post.R)


### Description
This function lumps the partitions and saves a csv per identifier (combination of slide and scene). It also keeps track of the annotations of each cell at each level.
### Arguments
```
Rscript src/11_cell_identification/MapFingerprints_post.R --path.input.folder <path.input.folder/> --path.output.folder <path.output.folder/> --path.annotation.log <path.annotation.log/> --path.celltypes <path.celltypes/> --node.id <node.id/> --version.id <version.id/>
```

| Argument          | Description                                                                                                                                                             |
|-------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `path.input.folder` | Path to input directory where partitions have been stored (dir). Example: `/path/to/project_directory/output_cell_identification/n01/v01/tmp_partitions_annotated`                       |
| `path.output.folder`| Path to output directory where csvs will be stored (dir). Example: `/path/to/project_directory/output_cell_identification/n01/v01/data_annotated`                             |
| `path.annotation.log`   | Path to csv to keep track of cell labels (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/annotation_log.csv`  |
| `path.celltypes`    | Path to output csv where the cell types for split selection are stored (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/unique_celltypes.csv`     |
| `node.id`   | Identifier for the level at which the annotations will be stored (.string). Example: `n01`  |
| `version.id`   | Version performed clustering (string). Example: `v01`   |

---

**Script:** [DigitalReconstruction_generate_csv.R](src/11_cell_identification/DigitalReconstruction_generate_csv.R)

[//]: # ()
[//]: # (### Description)

[//]: # (This function lumps the partitions and saves a csv per identifier &#40;combination of slide and scene&#41;. It also keeps track of the annotations of each cell at each level.)

[//]: # (### Arguments)

[//]: # (```)

[//]: # (Rscript src/11_cell_identification/MapFingerprints_post.R --path.input.folder <path.input.folder/> --path.output.folder <path.output.folder/> --path.annotation.log <path.annotation.log/> --path.celltypes <path.celltypes/> --node.id <node.id/> --version.id <version.id/>)

[//]: # (```)

[//]: # ()
[//]: # (| Argument          | Description                                                                                                                                                             |)

[//]: # (|-------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|)

[//]: # (| `path.input.folder` | Path to input directory where partitions have been stored &#40;dir&#41;. Example: `/path/to/project_directory/output_cell_identification/n01/v01/tmp_partitions_annotated`                       |)

[//]: # (| `path.output.folder`| Path to output directory where csvs will be stored &#40;dir&#41;. Example: `/path/to/project_directory/output_cell_identification/n01/v01/data_annotated`                             |)

[//]: # (| `path.annotation.log`   | Path to csv to keep track of cell labels &#40;.csv&#41;. Example: `/path/to/project_directory/output_cell_identification/n01/v01/annotation_log.csv`  |)

[//]: # (| `path.celltypes`    | Path to output csv where the cell types for split selection are stored &#40;.csv&#41;. Example: `/path/to/project_directory/output_cell_identification/n01/v01/unique_celltypes.csv`     |)

[//]: # (| `node.id`   | Identifier for the level at which the annotations will be stored &#40;.string&#41;. Example: `n01`  |)

[//]: # (| `version.id`   | Version performed clustering &#40;string&#41;. Example: `v01`   |)

---

**Script:** [DataFiltering.R](src/11_cell_identification/DataFiltering.R)


### Description
TO DO 
### Arguments
```
Rscript src/11_cell_identification/DataFiltering.R --path.input.folder <path.input.folder/> --path.split.celltype <path.split.celltype/> --path.output.csv <path.output.csv/> 
```

| Argument          | Description                                                                                                                                                             |
|-------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `path.input.folder` | Path to input directory where the annotated data is stored (dir). Example: `/path/to/project_directory/output_cell_identification/n01/v01/data_annotated`                       |
| `path.split.celltype`| Path to input directory where the selected celltypes are listed (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/selected_celltypes_c01.csv`                            |
| `path.output.csv`   | Path to output csv where the split data will be stored (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/c01/merged_data_c01.csv` |
