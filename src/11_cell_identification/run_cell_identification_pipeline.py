#!/usr/bin/env python3
"""
Linear debugging pipeline for the cell-identification workflow.

Run from the target conda environment, for example:

    conda activate cell_identification
    python run_cell_identification_pipeline.py \
        --config cell_identification_XenMIL2_config.yaml

The script intentionally stays linear and explicit. It is not intended to be a
workflow engine; it is a readable/debuggable replacement for the previous .sh.
"""

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError as e:
    raise ImportError(
        "Missing dependency: PyYAML. Install with: conda install pyyaml "
        "or pip install pyyaml"
    ) from e

import polars as pl


def run_cmd(cmd):
    print("\nRunning command:")
    print("  " + shlex.join([str(x) for x in cmd]))
    subprocess.run([str(x) for x in cmd], check=True)


def check_file(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Expected file not found: {path}")


def check_dir(path):
    path = Path(path)
    if not path.is_dir():
        raise NotADirectoryError(f"Expected directory not found: {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the cell-identification pipeline from a YAML config.")
    parser.add_argument("--config", required=True, help="Path to YAML configuration file.")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if cfg is None:
        raise ValueError(f"Config file is empty: {config_path}")

    # Avoid RAPIDS/cuda simulation issues inherited from parent sessions.
    os.environ.pop("NUMBA_ENABLE_CUDASIM", None)

    BASE_INPUT_DIR = Path(cfg["BASE_INPUT_DIR"])
    BASE_OUTPUT_DIR = Path(cfg["BASE_OUTPUT_DIR"])
    BASE_SCRIPT_DIR = Path(cfg["BASE_SCRIPT_DIR"])

    PYTHON_EXE = str(cfg.get("PYTHON_EXE", "")).strip() or sys.executable
    CLUSTERING_ANALYSIS_SCRIPT = str(cfg.get("CLUSTERING_ANALYSIS_SCRIPT", "ClusteringAnalysis.py")).strip()

    NODE_ID = str(cfg.get("NODE_ID", "n01"))
    VERSION_ID = str(cfg.get("VERSION_ID", "v01"))
    CHILD_ID = str(cfg.get("CHILD_ID", "c01"))

    SEED = int(cfg.get("SEED", 1234))
    NORMALIZATION_YES_NO = int(cfg.get("NORMALIZATION_YES_NO", 1))
    NORMALIZATION_SCOPE = str(cfg.get("NORMALIZATION_SCOPE", "sample")).strip()
    SAMPLING_YES_NO = int(cfg.get("SAMPLING_YES_NO", 1))
    NUMBER_OF_CELLS = int(cfg.get("NUMBER_OF_CELLS", 25000))

    RUN_UMAP = int(cfg.get("RUN_UMAP", 1))
    RUN_PCA = int(cfg.get("RUN_PCA", 1))
    RUN_TSNE = int(cfg.get("RUN_TSNE", 1))

    RUN_PHENOGRAPH = int(cfg.get("RUN_PHENOGRAPH", 1))
    RUN_KMEANS = int(cfg.get("RUN_KMEANS", 1))
    RUN_SOM = int(cfg.get("RUN_SOM", 1))
    AUTO_N_CLUSTERS_FROM_PHENOGRAPH = int(cfg.get("AUTO_N_CLUSTERS_FROM_PHENOGRAPH", 1))
    NUMBER_OF_CLUSTERS_FALLBACK = int(cfg.get("NUMBER_OF_CLUSTERS_FALLBACK", 20))

    RUN_MAPCLUSTERS = int(cfg.get("RUN_MAPCLUSTERS", 1))
    RUN_CONFUSION_MATRIX = int(cfg.get("RUN_CONFUSION_MATRIX", 1))

    GENERATE_MARKER_PLOTS = int(cfg.get("GENERATE_MARKER_PLOTS", 1))
    GENERATE_SPATIAL_PLOTS = int(cfg.get("GENERATE_SPATIAL_PLOTS", 1))
    SPATIAL_MAX_POINTS_PER_PLOT = int(cfg.get("SPATIAL_MAX_POINTS_PER_PLOT", 200000))

    RUN_PAIRWISE_DENSITY = int(cfg.get("RUN_PAIRWISE_DENSITY", 0))
    PAIRWISE_TOP_N_MARKERS = int(cfg.get("PAIRWISE_TOP_N_MARKERS", 10))
    PAIRWISE_BINS = int(cfg.get("PAIRWISE_BINS", 96))
    PAIRWISE_METHOD = str(cfg.get("PAIRWISE_METHOD", "som")).strip()

    RUN_DOWNSTREAM_AFTER_ANNOTATION = int(cfg.get("RUN_DOWNSTREAM_AFTER_ANNOTATION", 1))
    PAUSE_FOR_MANUAL_ANNOTATION = int(cfg.get("PAUSE_FOR_MANUAL_ANNOTATION", 1))

    RUN_CHILD_FILTERING = int(cfg.get("RUN_CHILD_FILTERING", 0))
    KEEP_CELLTYPE_COLUMN_IN_CHILD = int(cfg.get("KEEP_CELLTYPE_COLUMN_IN_CHILD", 0))
    MIN_PREDICTION_CONFIDENCE = str(cfg.get("MIN_PREDICTION_CONFIDENCE", "")).strip()
    ALLOWED_PREDICTION_STATUS = str(cfg.get("ALLOWED_PREDICTION_STATUS", "")).strip()

    OVERWRITE_MARKERS = int(cfg.get("OVERWRITE_MARKERS", 0))

    NODE_FOLDER = BASE_OUTPUT_DIR / NODE_ID
    VERSION_FOLDER = NODE_FOLDER / VERSION_ID
    CHILD_FOLDER = NODE_FOLDER / CHILD_ID

    OUTPUT_MERGED = BASE_OUTPUT_DIR / "df_data_merged.parquet"
    OUTPUT_NORMALIZED = NODE_FOLDER / "df_data_norm.parquet"
    OUTPUT_SAMPLED = NODE_FOLDER / "df_data_sampled.parquet"

    MARKER_LIST = VERSION_FOLDER / f"phenotypic_markers_{NODE_ID}_{VERSION_ID}.csv"

    OUTPUT_UMAP = VERSION_FOLDER / "uMap.parquet"
    MODEL_UMAP = VERSION_FOLDER / "uMap.pkl"
    OUTPUT_PCA = VERSION_FOLDER / "PCA.parquet"
    MODEL_PCA = VERSION_FOLDER / "PCA.pkl"
    OUTPUT_TSNE = VERSION_FOLDER / "tsne.parquet"
    MODEL_TSNE = VERSION_FOLDER / "tsne.pkl"

    OUTPUT_PHENOGRAPH = VERSION_FOLDER / "phenograph.parquet"
    OUTPUT_KMEANS = VERSION_FOLDER / "kmeans.parquet"
    OUTPUT_SOM = VERSION_FOLDER / "som.parquet"

    CLUSTER_MAPPING_FOLDER = VERSION_FOLDER / "cluster_mapping"
    MAPPED_PHENOGRAPH = CLUSTER_MAPPING_FOLDER / "phenograph_mapped_clusters.parquet"
    MAPPED_KMEANS = CLUSTER_MAPPING_FOLDER / "kmeans_mapped_clusters.parquet"
    MAPPED_SOM = CLUSTER_MAPPING_FOLDER / "som_mapped_clusters.parquet"

    ANNOTATION_DICTIONARY = VERSION_FOLDER / "annotation_dictionary.csv"
    CONSENSUS_DATA = VERSION_FOLDER / "df_data_consensus.parquet"
    FINGERPRINT_PREDICTIONS = VERSION_FOLDER / "fingerprint_mapping" / "fingerprint_predictions.parquet"

    CONFUSION_MATRIX_CLUSTERS = VERSION_FOLDER / "confusion_matrix_clusters.parquet"
    CONFUSION_MATRIX_ANNOTATED = VERSION_FOLDER / "confusion_matrix_annotated.parquet"

    SELECTED_CELLTYPES = NODE_FOLDER / f"selected_celltypes_{CHILD_ID}.csv"
    OUTPUT_FILTERED_CHILD = CHILD_FOLDER / "df_data_merged.parquet"

    BASE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    NODE_FOLDER.mkdir(parents=True, exist_ok=True)
    VERSION_FOLDER.mkdir(parents=True, exist_ok=True)
    CHILD_FOLDER.mkdir(parents=True, exist_ok=True)
    CLUSTER_MAPPING_FOLDER.mkdir(parents=True, exist_ok=True)

    SCRIPT_MERGE = BASE_SCRIPT_DIR / "MergeData.py"
    SCRIPT_NORMALIZE = BASE_SCRIPT_DIR / "DataNormalization.py"
    SCRIPT_SAMPLE = BASE_SCRIPT_DIR / "DataSampling.py"
    SCRIPT_DR = BASE_SCRIPT_DIR / "DimensionalityReduction.py"
    SCRIPT_CLUSTER = BASE_SCRIPT_DIR / "Clustering.py"
    SCRIPT_MAPCLUSTERS = BASE_SCRIPT_DIR / "MapClusters.py"
    SCRIPT_CLUSTERING_ANALYSIS = BASE_SCRIPT_DIR / CLUSTERING_ANALYSIS_SCRIPT
    SCRIPT_PAIRWISE_DENSITY = BASE_SCRIPT_DIR / "PreComputePairWiseDensity.py"
    SCRIPT_STABILITY = BASE_SCRIPT_DIR / "ClusteringStability.py"
    SCRIPT_MAPFINGERPRINTS = BASE_SCRIPT_DIR / "MapFingerprints.py"
    SCRIPT_FILTER = BASE_SCRIPT_DIR / "DataFiltering.py"
    SCRIPT_CONFUSION_MATRIX = BASE_SCRIPT_DIR / "ClusterConfusionMatrix.py"

    print("\n############# Pipeline configuration #############")
    print(f"Config file:        {config_path}")
    print(f"Python executable:  {PYTHON_EXE}")
    print(f"Input folder:       {BASE_INPUT_DIR}")
    print(f"Output folder:      {BASE_OUTPUT_DIR}")
    print(f"Script folder:      {BASE_SCRIPT_DIR}")
    print(f"Node/version:       {NODE_ID}/{VERSION_ID}")
    print(f"Analysis script:    {SCRIPT_CLUSTERING_ANALYSIS}")

    check_dir(BASE_INPUT_DIR)
    check_dir(BASE_SCRIPT_DIR)
    for script in [
        SCRIPT_MERGE, SCRIPT_NORMALIZE, SCRIPT_SAMPLE, SCRIPT_DR, SCRIPT_CLUSTER,
        SCRIPT_MAPCLUSTERS, SCRIPT_CLUSTERING_ANALYSIS, SCRIPT_STABILITY,
        SCRIPT_MAPFINGERPRINTS, SCRIPT_FILTER, SCRIPT_CONFUSION_MATRIX
    ]:
        check_file(script)

    # -----------------------------------------------------------------------------
    # 1. Merge feature-extraction CSVs
    # -----------------------------------------------------------------------------
    print("\n############# 1. MergeData.py #############")
    run_cmd([
        PYTHON_EXE, SCRIPT_MERGE,
        "--path.input.folder", BASE_INPUT_DIR,
        "--path.output.csv", OUTPUT_MERGED,
    ])
    check_file(OUTPUT_MERGED)

    # -----------------------------------------------------------------------------
    # 2. Normalize
    # -----------------------------------------------------------------------------
    print("\n############# 2. DataNormalization.py #############")
    run_cmd([
        PYTHON_EXE, SCRIPT_NORMALIZE,
        "--path.input.csv", OUTPUT_MERGED,
        "--normalization.yes.no", NORMALIZATION_YES_NO,
        "--normalization.scope", NORMALIZATION_SCOPE,
        "--path.output.csv", OUTPUT_NORMALIZED,
    ])
    check_file(OUTPUT_NORMALIZED)

    # -----------------------------------------------------------------------------
    # 2b. Marker list
    # -----------------------------------------------------------------------------
    print("\n############# 2b. Marker list #############")
    if OVERWRITE_MARKERS == 1 or not MARKER_LIST.is_file():
        print(f"Creating marker list: {MARKER_LIST}")

        df = pl.read_parquet(OUTPUT_NORMALIZED)
        id_cols = {"sample_id", "slide_id", "scene_id", "scan_region", "OID", "X", "Y", "s.area"}
        markers = [col for col, dtype in df.schema.items() if col not in id_cols and dtype.is_numeric()]

        if len(markers) == 0:
            raise ValueError("No numeric marker columns found for marker list.")

        pl.DataFrame({"marker_id": markers}).write_csv(MARKER_LIST)
        print(f"Wrote marker list with {len(markers)} markers.")
    else:
        print(f"Marker list already exists, keeping: {MARKER_LIST}")

    check_file(MARKER_LIST)

    # -----------------------------------------------------------------------------
    # 3. Sampling
    # -----------------------------------------------------------------------------
    print("\n############# 3. DataSampling.py #############")
    run_cmd([
        PYTHON_EXE, SCRIPT_SAMPLE,
        "--path.input.csv", OUTPUT_NORMALIZED,
        "--path.output.csv", OUTPUT_SAMPLED,
        "--sampling.yes.no", SAMPLING_YES_NO,
        "--number.of.cells", NUMBER_OF_CELLS,
        "--selected.seed", SEED,
    ])
    check_file(OUTPUT_SAMPLED)

    # -----------------------------------------------------------------------------
    # 4. Dimensionality reduction
    # -----------------------------------------------------------------------------
    print("\n############# 4. DimensionalityReduction.py #############")

    if RUN_UMAP == 1:
        run_cmd([
            PYTHON_EXE, SCRIPT_DR,
            "--input.marker.list", MARKER_LIST,
            "--path.input.csv", OUTPUT_SAMPLED,
            "--path.output.csv", OUTPUT_UMAP,
            "--path.output.model", MODEL_UMAP,
            "--dimensionality.reduction.method", "uMap",
            "--selected.seed", SEED,
        ])
        check_file(OUTPUT_UMAP)
        check_file(MODEL_UMAP)
    else:
        OUTPUT_UMAP = "not included"
        MODEL_UMAP = "not included"

    if RUN_PCA == 1:
        run_cmd([
            PYTHON_EXE, SCRIPT_DR,
            "--input.marker.list", MARKER_LIST,
            "--path.input.csv", OUTPUT_SAMPLED,
            "--path.output.csv", OUTPUT_PCA,
            "--path.output.model", MODEL_PCA,
            "--dimensionality.reduction.method", "PCA",
            "--selected.seed", SEED,
        ])
        check_file(OUTPUT_PCA)
        check_file(MODEL_PCA)
    else:
        OUTPUT_PCA = "not included"
        MODEL_PCA = "not included"

    if RUN_TSNE == 1:
        run_cmd([
            PYTHON_EXE, SCRIPT_DR,
            "--input.marker.list", MARKER_LIST,
            "--path.input.csv", OUTPUT_SAMPLED,
            "--path.output.csv", OUTPUT_TSNE,
            "--path.output.model", MODEL_TSNE,
            "--dimensionality.reduction.method", "tsne",
            "--selected.seed", SEED,
        ])
        check_file(OUTPUT_TSNE)
        check_file(MODEL_TSNE)
    else:
        OUTPUT_TSNE = "not included"
        MODEL_TSNE = "not included"

    # -----------------------------------------------------------------------------
    # 5. Clustering
    # -----------------------------------------------------------------------------
    print("\n############# 5. Clustering.py #############")

    if RUN_PHENOGRAPH == 1:
        run_cmd([
            PYTHON_EXE, SCRIPT_CLUSTER,
            "--input.marker.list", MARKER_LIST,
            "--path.input.csv", OUTPUT_SAMPLED,
            "--path.output.csv", OUTPUT_PHENOGRAPH,
            "--clustering.method", "phenograph",
            "--selected.seed", SEED,
        ])
        check_file(OUTPUT_PHENOGRAPH)
    else:
        OUTPUT_PHENOGRAPH = "not included"

    if AUTO_N_CLUSTERS_FROM_PHENOGRAPH == 1 and OUTPUT_PHENOGRAPH != "not included":
        df_pg = pl.read_parquet(OUTPUT_PHENOGRAPH)
        if "cluster" not in df_pg.columns:
            raise ValueError("PhenoGraph output does not contain a cluster column.")
        N_CLUSTERS = int(df_pg.select(pl.col("cluster").n_unique()).item())
    else:
        N_CLUSTERS = NUMBER_OF_CLUSTERS_FALLBACK

    print(f"Number of clusters for KMeans/SOM: {N_CLUSTERS}")

    if RUN_KMEANS == 1:
        run_cmd([
            PYTHON_EXE, SCRIPT_CLUSTER,
            "--input.marker.list", MARKER_LIST,
            "--path.input.csv", OUTPUT_SAMPLED,
            "--path.output.csv", OUTPUT_KMEANS,
            "--clustering.method", "kmeans",
            "--number.of.clusters", N_CLUSTERS,
            "--selected.seed", SEED,
        ])
        check_file(OUTPUT_KMEANS)
    else:
        OUTPUT_KMEANS = "not included"

    if RUN_SOM == 1:
        run_cmd([
            PYTHON_EXE, SCRIPT_CLUSTER,
            "--input.marker.list", MARKER_LIST,
            "--path.input.csv", OUTPUT_SAMPLED,
            "--path.output.csv", OUTPUT_SOM,
            "--clustering.method", "som",
            "--number.of.clusters", N_CLUSTERS,
            "--selected.seed", SEED,
        ])
        check_file(OUTPUT_SOM)
    else:
        OUTPUT_SOM = "not included"

    # -----------------------------------------------------------------------------
    # 6. Map clusters to full data
    # -----------------------------------------------------------------------------
    print("\n############# 6. MapClusters.py #############")

    if RUN_MAPCLUSTERS == 1:
        if OUTPUT_UMAP == "not included" or MODEL_UMAP == "not included":
            raise ValueError("MapClusters.py requires UMAP output and UMAP model.")

        if OUTPUT_PHENOGRAPH != "not included":
            run_cmd([
                PYTHON_EXE, SCRIPT_MAPCLUSTERS,
                "--input.marker.list", MARKER_LIST,
                "--path.input.full.data", OUTPUT_NORMALIZED,
                "--path.input.umap", OUTPUT_UMAP,
                "--path.input.umap.model", MODEL_UMAP,
                "--path.input.cluster", OUTPUT_PHENOGRAPH,
                "--path.output.csv", MAPPED_PHENOGRAPH,
                "--knn.n.neighbors", 25,
                "--prediction.high.confidence", 0.80,
                "--prediction.medium.confidence", 0.60,
            ])
            check_file(MAPPED_PHENOGRAPH)
        else:
            MAPPED_PHENOGRAPH = "not included"

        if OUTPUT_KMEANS != "not included":
            run_cmd([
                PYTHON_EXE, SCRIPT_MAPCLUSTERS,
                "--input.marker.list", MARKER_LIST,
                "--path.input.full.data", OUTPUT_NORMALIZED,
                "--path.input.umap", OUTPUT_UMAP,
                "--path.input.umap.model", MODEL_UMAP,
                "--path.input.cluster", OUTPUT_KMEANS,
                "--path.output.csv", MAPPED_KMEANS,
                "--knn.n.neighbors", 25,
                "--prediction.high.confidence", 0.80,
                "--prediction.medium.confidence", 0.60,
            ])
            check_file(MAPPED_KMEANS)
        else:
            MAPPED_KMEANS = "not included"

        if OUTPUT_SOM != "not included":
            run_cmd([
                PYTHON_EXE, SCRIPT_MAPCLUSTERS,
                "--input.marker.list", MARKER_LIST,
                "--path.input.full.data", OUTPUT_NORMALIZED,
                "--path.input.umap", OUTPUT_UMAP,
                "--path.input.umap.model", MODEL_UMAP,
                "--path.input.cluster", OUTPUT_SOM,
                "--path.output.csv", MAPPED_SOM,
                "--knn.n.neighbors", 25,
                "--prediction.high.confidence", 0.80,
                "--prediction.medium.confidence", 0.60,
            ])
            check_file(MAPPED_SOM)
        else:
            MAPPED_SOM = "not included"
    else:
        MAPPED_PHENOGRAPH = "not included"
        MAPPED_KMEANS = "not included"
        MAPPED_SOM = "not included"

    # -----------------------------------------------------------------------------
    # 6b. Confusion matrix (cluster x sample), raw numeric clusters
    # -----------------------------------------------------------------------------
    if RUN_CONFUSION_MATRIX == 1 and RUN_MAPCLUSTERS == 1:
        print("\n############# 6b. ClusterConfusionMatrix.py (clusters) #############")
        run_cmd([
            PYTHON_EXE, SCRIPT_CONFUSION_MATRIX,
            "--mode", "clusters",
            "--path.input.phenograph", MAPPED_PHENOGRAPH,
            "--path.input.kmeans", MAPPED_KMEANS,
            "--path.input.som", MAPPED_SOM,
            "--path.output.csv", CONFUSION_MATRIX_CLUSTERS,
        ])
        check_file(CONFUSION_MATRIX_CLUSTERS)

    # -----------------------------------------------------------------------------
    # 7. Clustering analysis using selected script
    # -----------------------------------------------------------------------------
    # print("\n############# 7. ClusteringAnalysis.py #############")
    # run_cmd([
    #     PYTHON_EXE, SCRIPT_CLUSTERING_ANALYSIS,
    #     "--input.marker.list", MARKER_LIST,
    #     "--path.input.csv", OUTPUT_SAMPLED,
    #     "--path.input.pca", OUTPUT_PCA,
    #     "--path.input.tsne", OUTPUT_TSNE,
    #     "--path.input.umap", OUTPUT_UMAP,
    #     "--path.input.phenograph", OUTPUT_PHENOGRAPH,
    #     "--path.input.kmeans", OUTPUT_KMEANS,
    #     "--path.input.som", OUTPUT_SOM,
    #     "--path.annotation.dictionary", ANNOTATION_DICTIONARY,
    #     "--generate.marker.plots", GENERATE_MARKER_PLOTS,
    #     "--path.output.folder", VERSION_FOLDER,
    #     "--path.input.mapped.phenograph", MAPPED_PHENOGRAPH,
    #     "--path.input.mapped.kmeans", MAPPED_KMEANS,
    #     "--path.input.mapped.som", MAPPED_SOM,
    #     "--generate.spatial.plots", GENERATE_SPATIAL_PLOTS,
    #     "--spatial.max.points.per.plot", SPATIAL_MAX_POINTS_PER_PLOT,
    #     "--selected.seed", SEED,
    # ])
    # check_file(ANNOTATION_DICTIONARY)

    print("\n############# 7. ClusteringAnalysis_updated.py — full first build #############")

    SCRIPT_CLUSTERING_ANALYSIS_UPDATED = BASE_SCRIPT_DIR / "ClusteringAnalysis_updated.py"

    run_cmd([
        PYTHON_EXE, SCRIPT_CLUSTERING_ANALYSIS_UPDATED,
        "--mode", "build",
        "--input.marker.list", MARKER_LIST,
        "--path.input.csv", OUTPUT_SAMPLED,
        "--path.input.pca", OUTPUT_PCA,
        "--path.input.tsne", OUTPUT_TSNE,
        "--path.input.umap", OUTPUT_UMAP,
        "--path.input.phenograph", OUTPUT_PHENOGRAPH,
        "--path.input.kmeans", OUTPUT_KMEANS,
        "--path.input.som", OUTPUT_SOM,
        "--path.annotation.dictionary", ANNOTATION_DICTIONARY,
        "--generate.marker.plots", GENERATE_MARKER_PLOTS,
        "--path.output.folder", VERSION_FOLDER,
        "--path.input.mapped.phenograph", MAPPED_PHENOGRAPH,
        "--path.input.mapped.kmeans", MAPPED_KMEANS,
        "--path.input.mapped.som", MAPPED_SOM,
        "--generate.spatial.plots", GENERATE_SPATIAL_PLOTS,
        "--spatial.max.points.per.plot", SPATIAL_MAX_POINTS_PER_PLOT,
        "--selected.seed", SEED,
        "--write.json", 1,
        "--write.html", 1,
    ])

    check_file(ANNOTATION_DICTIONARY)

    print("\n############# 7b. ClusteringAnalysis_updated.py — annotation update only #############")

    run_cmd([
        PYTHON_EXE, SCRIPT_CLUSTERING_ANALYSIS_UPDATED,
        "--mode", "update",
        "--path.annotation.dictionary", ANNOTATION_DICTIONARY,
        "--path.output.folder", VERSION_FOLDER,
        "--update.dr.plots", 1,
        "--update.spatial.plots", 1,
        "--update.heatmaps", 1,
        "--update.enrichment", 1,
        "--spatial.max.points.per.plot", SPATIAL_MAX_POINTS_PER_PLOT,
        "--selected.seed", SEED,
        "--write.json", 1,
        "--write.html", 1,
    ])

    # -----------------------------------------------------------------------------
    # 8. Optional pairwise density
    # -----------------------------------------------------------------------------
    if RUN_PAIRWISE_DENSITY == 1:
        print("\n############# 8. PreComputePairWiseDensity.py #############")

        if PAIRWISE_METHOD == "phenograph":
            PAIRWISE_CLUSTER_FILE = OUTPUT_PHENOGRAPH
        elif PAIRWISE_METHOD == "kmeans":
            PAIRWISE_CLUSTER_FILE = OUTPUT_KMEANS
        elif PAIRWISE_METHOD == "som":
            PAIRWISE_CLUSTER_FILE = OUTPUT_SOM
        else:
            raise ValueError("PAIRWISE_METHOD must be one of: phenograph, kmeans, som")

        if PAIRWISE_CLUSTER_FILE == "not included":
            raise ValueError(f"Requested pairwise density for {PAIRWISE_METHOD}, but that clustering output is not included.")

        check_file(SCRIPT_PAIRWISE_DENSITY)
        PAIRWISE_OUTPUT_FOLDER = VERSION_FOLDER / "pairwise_density" / PAIRWISE_METHOD

        run_cmd([
            PYTHON_EXE, SCRIPT_PAIRWISE_DENSITY,
            "--input.marker.list", MARKER_LIST,
            "--path.input.csv", OUTPUT_SAMPLED,
            "--path.input.cluster", PAIRWISE_CLUSTER_FILE,
            "--path.output.folder", PAIRWISE_OUTPUT_FOLDER,
            "--top.n.markers", PAIRWISE_TOP_N_MARKERS,
            "--bins", PAIRWISE_BINS,
        ])

    # -----------------------------------------------------------------------------
    # 9. Manual annotation checkpoint
    # -----------------------------------------------------------------------------
    print("\n############# 9. Manual annotation checkpoint #############")
    print(f"Annotation dictionary: {ANNOTATION_DICTIONARY}")
    print(f"Figures folder:        {VERSION_FOLDER / 'figures'}")
    print("Edit the annotation column before consensus/fingerprint mapping.")

    if RUN_DOWNSTREAM_AFTER_ANNOTATION != 1:
        print("RUN_DOWNSTREAM_AFTER_ANNOTATION=0. Stopping after annotation-support plots.")
        sys.exit(0)

    if PAUSE_FOR_MANUAL_ANNOTATION == 1:
        input("\nPress Enter after editing annotation_dictionary.csv to continue...")

    # -----------------------------------------------------------------------------
    # 10. Clustering stability and consensus
    # -----------------------------------------------------------------------------
    print("\n############# 10. ClusteringStability.py #############")
    run_cmd([
        PYTHON_EXE, SCRIPT_STABILITY,
        "--path.input.phenograph", OUTPUT_PHENOGRAPH,
        "--path.input.kmeans", OUTPUT_KMEANS,
        "--path.input.som", OUTPUT_SOM,
        "--path.annotation.dictionary", ANNOTATION_DICTIONARY,
        "--path.output.folder", VERSION_FOLDER,
    ])
    check_file(CONSENSUS_DATA)

    # -----------------------------------------------------------------------------
    # 11. Map fingerprints to full data
    # -----------------------------------------------------------------------------
    print("\n############# 11. MapFingerprints.py #############")
    run_cmd([
        PYTHON_EXE, SCRIPT_MAPFINGERPRINTS,
        "--input.marker.list", MARKER_LIST,
        "--path.input.full.data", OUTPUT_NORMALIZED,
        "--path.input.consensus", CONSENSUS_DATA,
        "--path.output.folder", VERSION_FOLDER,
        "--node.id", NODE_ID,
        "--version.id", VERSION_ID,
        "--max.cells.per.celltype", 2500,
        "--umap.n.neighbors", 15,
        "--umap.min.dist", 0.1,
        "--knn.n.neighbors", 25,
        "--selected.seed", SEED,
        "--refine.min.confidence", 0.60,
        "--refine.min.margin", 0.10,
        "--prediction.high.confidence", 0.80,
        "--prediction.medium.confidence", 0.60,
        "--write.per.sample.files", 1,
    ])
    check_file(FINGERPRINT_PREDICTIONS)

    # -----------------------------------------------------------------------------
    # 11b. Confusion matrix (cluster x sample), consensus/fingerprint annotations
    # -----------------------------------------------------------------------------
    if RUN_CONFUSION_MATRIX == 1:
        print("\n############# 11b. ClusterConfusionMatrix.py (annotated) #############")
        run_cmd([
            PYTHON_EXE, SCRIPT_CONFUSION_MATRIX,
            "--mode", "annotated",
            "--path.input.annotated", FINGERPRINT_PREDICTIONS,
            "--label.col", "CellType",
            "--method.label", "consensus",
            "--path.output.csv", CONFUSION_MATRIX_ANNOTATED,
        ])
        check_file(CONFUSION_MATRIX_ANNOTATED)

    # -----------------------------------------------------------------------------
    # 12. Optional child-node filtering
    # -----------------------------------------------------------------------------
    if RUN_CHILD_FILTERING == 1:
        print("\n############# 12. DataFiltering.py #############")

        if not SELECTED_CELLTYPES.is_file():
            print(f"Selected CellTypes file does not exist. Creating template: {SELECTED_CELLTYPES}")
            celltypes_path = VERSION_FOLDER / "celltypes.csv"
            check_file(celltypes_path)

            df_ct = pl.read_csv(celltypes_path)
            if "CellType" not in df_ct.columns:
                raise ValueError("celltypes.csv does not contain a CellType column.")

            (
                df_ct.select("CellType")
                     .unique()
                     .sort("CellType")
                     .with_columns(pl.lit(0).alias("include"))
                     .write_csv(SELECTED_CELLTYPES)
            )

            print("Edit this file and set include=1 for CellTypes to split, then rerun:")
            print(f"  {SELECTED_CELLTYPES}")
            sys.exit(0)

        filter_cmd = [
            PYTHON_EXE, SCRIPT_FILTER,
            "--path.input.data", OUTPUT_NORMALIZED,
            "--path.input.annotations", FINGERPRINT_PREDICTIONS,
            "--path.split.celltypes", SELECTED_CELLTYPES,
            "--path.output.csv", OUTPUT_FILTERED_CHILD,
            "--keep.celltype.column", KEEP_CELLTYPE_COLUMN_IN_CHILD,
        ]

        if MIN_PREDICTION_CONFIDENCE != "":
            filter_cmd += ["--min.prediction.confidence", MIN_PREDICTION_CONFIDENCE]

        if ALLOWED_PREDICTION_STATUS != "":
            filter_cmd += ["--allowed.prediction.status", ALLOWED_PREDICTION_STATUS]

        run_cmd(filter_cmd)
        check_file(OUTPUT_FILTERED_CHILD)

    print("\n############# Pipeline completed #############")
    print(f"Merged data:             {OUTPUT_MERGED}")
    print(f"Normalized data:         {OUTPUT_NORMALIZED}")
    print(f"Sampled data:            {OUTPUT_SAMPLED}")
    print(f"Marker list:             {MARKER_LIST}")
    print(f"Version folder:          {VERSION_FOLDER}")
    print(f"Annotation dictionary:   {ANNOTATION_DICTIONARY}")
    print(f"Consensus data:          {CONSENSUS_DATA}")
    print(f"Fingerprint predictions: {FINGERPRINT_PREDICTIONS}")
