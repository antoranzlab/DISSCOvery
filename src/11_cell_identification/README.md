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
    ├── 9. MapFingerprints_testing.py
    ├── 10. MapFingerprints_post.py
    └──  11. DataFiltering.py

</pre>

---
The user should note that in the cell identification level we can have different versions and different nodes. 
Different nodes refer to the hierarchical definition of cell types (the parent node could be the main cell types, whereas a child node could be the different Tcy subtypes within previously identified Tcys). 
Parallel parent nodes can also be defined to use different normalization/sampling approaches. Different versions are runs of the node with different sets of markers or annotations. 
Therefore, the same node can have different versions. The scheme below summaraize the entire process.

<p align="center">
  <img src="images/cell_identification_schema.png" alt="My Plot" width="600"/>
</p>

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

Int he software this list is created by providing the requited information in the GUI. While running manually, the user has to create the file themselves. 

---

**Script:** [Clustering.R](src/11_cell_identification/Clustering.R)


### Description
Using the sampled data, the set of user-selected markers are taken and a clustering method is applied (to be chosen between phenograph, kmeans, and flowsom).
This function is executed 3 times, once per clustering method. Phenograph doesn't take the maximum number of clusters in its function.
Therefore, the numnber of clusters provided for kmean anf flwosome must match the numnber of clsuerts obtained using phenograph. 

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
The results from DimensionalityReduction.R and Clustering.R are evaluated and several graphs are generated to be displayed on the GUI. Each graph is annotated by a user. 
All annotations, for each clustering method are then merged together into one `annotation_dictionary.csv` file. 

Outside of the software the user first runs `ClusteringAnalysis.R` to create all plots and `annotation_dictionary.csv` file. 
Then they use the plots to properly annotate `annotation_dictionary.csv` for the next step. 

The content of the `annotation_dictionary.csv` looks like this:

```
cl_method      cluster       annotation     annotated
flowsom        1             Tumor          1
flowsom        15            Tumor          1
flowsom        6             B cell         1
kmeans         21            T cell         1
phenograph     3             Tumor          1
```

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

**Script:** [MapFingerprints_testing.py](src/11_cell_identification/MapFingerprints_testing.py)


### Description
This function takes all the partitions saved in the previous step and projects them into the model.
Then, it  applies a knn approach to assign a new label to the cells based on the annotated data. 
The function only executes one job at once, therefore it needs to be orchestrated from outside or run for each `iter_X.csv` file produced in the previous step
### Arguments
```
python src/11_cell_identification/MapFingerprints_testing.py --input_marker_list <input_marker_list/> --path_input_csv_training <path_input_csv_training/> --path_input_csv_testing <path_input_csv_testing/> --path_input_model <path_input_model/> --path_output_folder <path_output_folder/>
```

| Argument          | Description                                                                                                                                                              |
|-------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `input_marker_list` | Path to the csv where the markers used for clustering are defined (.csv). Example: `/path/to/project_directory/output_cell_identification/phenotypic_markers_n01_v01.csv`                        |
| `path_input_csv_training`| Path to the csv with the training data (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/tmp_results/training_data.csv`                                  |
| `path_input_csv_testing`   | Path to the input csv where the training data is stored (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/tmp_partitions/iter_1.csv`    |
| `path_input_model`    | Path to input csv where the complete data is stored (.rds). Example: `/path/to/project_directory/output_cell_identification/n01/v01/tmp_results/tmp_umap.rds`      |
| `path_output_folder`   | Path to the output directory where the results will be stored (dir). Example: `/path/to/project_directory/output_cell_identification/n01/v01/tmp_partitions_annotated`    |

---

**Script:** [MapFingerprints_post.py](src/11_cell_identification/MapFingerprints_post.py)

### Description
This function lumps the partitions and saves a csv per identifier (combination of slide and scene). It also keeps track of the annotations of each cell at each level.
### Arguments
```
python src/11_cell_identification/MapFingerprints_post.py --path_input_folder <path_input_folder/> --path_output_folder <path_output_folder/> --path_annotation_log <path_annotation_log/> --path_celltypes <path_celltypes/> --node_id <node_id/> --version_id <version_id/>
```

| Argument         | Description                                                                                                                                                             |
|------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `path_input_folder` | Path to input directory where partitions have been stored (dir). Example: `/path/to/project_directory/output_cell_identification/n01/v01/tmp_partitions_annotated`                       |
| `path_output_folder`| Path to output directory where csvs will be stored (dir). Example: `/path/to/project_directory/output_cell_identification/n01/v01/data_annotated`                             |
| `path_annotation_log`  | Path to csv to keep track of cell labels (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/annotation_log.csv`  |
| `path_celltypes`   | Path to output csv where the cell types for split selection are stored (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/v01/unique_celltypes.csv`     |
| `node_id`  | Identifier for the level at which the annotations will be stored (.string). Example: `n01`  |
| `version_id`   | Version performed clustering (string). Example: `v01`   |

---

**Script:** [DataFiltering.py](src/11_cell_identification/DataFiltering.py)


### Description
Allows for re-clustering of the selected cell types or finalize the clustering process. 
Takes all the csvs listed in `path_input_folder`, filters the selected cell types from `selected_celltypes_c01.csv` and creates a file that will be an input to repeat the entire clustering procedure with only particular cell types. 

The content of the `selected_celltypes_c01.csv` should be as presented below:

```
CellType      include 
Tumor         1       
```

### Arguments
```
python src/11_cell_identification/DataFiltering.py --path_input_folder <path_input_folder/> --path_split_celltypes <path_split_celltypes/> --path_output_csv <path_output_csv/> 
```

| Argument          | Description                                                                                                                                                             |
|-------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `path_input_folder` | Path to input directory where the annotated data is stored (dir). Example: `/path/to/project_directory/output_cell_identification/n01/v01/data_annotated`                       |
| `path_split_celltypes`| Path to input directory where the selected celltypes are listed (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/selected_celltypes_c01.csv`                            |
| `path_output_csv`   | Path to output csv where the split data will be stored (.csv). Example: `/path/to/project_directory/output_cell_identification/n01/c01/merged_data_c01.csv` |

---
