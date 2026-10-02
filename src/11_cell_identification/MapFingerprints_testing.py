import os
import argparse
import numpy as np
import pandas as pd
import umap
from sklearn.neighbors import KNeighborsClassifier

def map_fingerprints_testing(marker_list, input_csv_training, input_csv_testing, input_model, output_folder):
    print(f"### marker list: {marker_list} ###")
    print(f"### input training data: {input_csv_training} ###")
    print(f"### input testing data: {input_csv_testing} ###")
    print(f"### input model: {input_model} ###")
    print(f"### output directory: {output_folder} ###")
    
    if not os.path.exists(output_folder):
        print(f"### creating folder: {output_folder} ###")
        os.makedirs(output_folder, exist_ok=True)
    
    print('Loading list of markers')
    
    phenotypic_markers = pd.read_csv(marker_list)
    phenotypic_markers["marker_id"] = (phenotypic_markers["marker_id"].str.replace("-", ".", regex=False).str.upper())
    
    print('Loading data files')
    
    tmp_training = pd.read_csv(input_csv_training)
    tmp_testing = pd.read_csv(input_csv_testing)
    
    tmp_wrong_names = sorted(set(phenotypic_markers["marker_id"]) - set(tmp_training.columns))

    if tmp_wrong_names:
        for name in tmp_wrong_names:
            print(f"{name} not found, it will not be included in the clustering.")
        
    phenotypic_markers = phenotypic_markers[phenotypic_markers["marker_id"].isin(tmp_training.columns)]
    
    print('Generating embedding template')
    
    training_matrix = tmp_training.loc[:, tmp_training.columns.isin(phenotypic_markers['marker_id'])]
    training_matrix = training_matrix.replace(',', '.', regex=True)
    training_matrix = training_matrix.apply(pd.to_numeric, errors='coerce')
    
    # Initialize the UMAP model
    umap_model = umap.UMAP(
        n_neighbors=15,  
        min_dist=0.1,
        n_components=3,  # 2D reduction 3 -> 3D reduction
        metric='euclidean',
        random_state=42
    )
    
    # Apply UMAP
    umap_embeddings = umap_model.fit_transform(training_matrix)
    
    print('Predicting complete data')
    
    testing_matrix = tmp_testing.loc[:, tmp_testing.columns.isin(phenotypic_markers['marker_id'])]
    testing_matrix = testing_matrix.replace(',', '.', regex=True)
    testing_matrix = testing_matrix.apply(pd.to_numeric, errors='coerce')
    
    # Transform the large dataset
    large_umap_embedding = umap_model.transform(testing_matrix)
    
    # Train a kNN classifier using the small dataset's UMAP embedding and annotations
    knn = KNeighborsClassifier(n_neighbors=25)  # Adjust 'n_neighbors' as needed
    training_annotations = tmp_training['predicted.celltype']  # Annotated cell types
    knn.fit(umap_embeddings, training_annotations)
    # Predict cell types for the large dataset
    testing_annotations = knn.predict(large_umap_embedding)
    tmp_testing['CellType'] = testing_annotations
    
    print('Writing csv')
    output_path = os.path.join(output_folder, os.path.basename(input_csv_testing))
    tmp_testing.to_csv(output_path, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Project cells testing.")
    parser.add_argument("--input_marker_list", type=str, required=True, help="Path to input csv with list of markers (.csv). Example: path/to/project_directory/cell_identification/marker_list_path.csv")
    parser.add_argument("--path_input_csv_training", type=str, required=True, help="Path to input csv with training data (.csv). Example: path/to/project_directory/cell_identification/training_data.csv")
    parser.add_argument("--path_input_csv_testing", type=str, required=True, help="Path to input csv with testing data (.csv). Example: path/to/project_directory/cell_identification/tmp_partitions/iter_1.csv")
    parser.add_argument("--path_input_model", type=str, required=False, help="Path to input .rds with umap model (.rds). (currently unused). Example: path/to/project_directory/cell_identification/uMap.rds")
    parser.add_argument("--path_output_folder", type=str, required=True, help="Path to output directory where to save the results. Example: path/to/project_directory/cell_identification/tmp_partitions_annotated")
    
    args = parser.parse_args()
    
    marker_list = args.input_marker_list
    input_csv_training = args.path_input_csv_training
    input_csv_testing = args.path_input_csv_testing
    input_model = args.path_input_model
    output_folder = args.path_output_folder
    
    map_fingerprints_testing(marker_list, input_csv_training, input_csv_testing, input_model, output_folder)
