#!/usr/bin/env python3

import argparse
import csv
import pickle
import warnings
from pathlib import Path

import numpy as np
import polars as pl


REQUIRED_ID_COLS = ["sample_id", "OID"]

OPTIONAL_OUTPUT_COLS = [
    "slide_id",
    "scene_id",
    "scan_region",
    "X",
    "Y",
    "s.area",
]


# ============================================================
# I/O helpers
# ============================================================

def sniff_separator(fp: Path) -> str:
    with open(fp, "r", newline="") as f:
        sample = f.read(4096)

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        return dialect.delimiter
    except csv.Error:
        return ";"


def read_table(path: str) -> pl.DataFrame:
    path_obj = Path(path)
    path_l = path.lower()

    if not path_obj.exists():
        raise ValueError(f"Input file does not exist: {path}")

    if path_l.endswith(".parquet"):
        return pl.read_parquet(path)

    if path_l.endswith((".csv", ".txt", ".tsv")):
        sep = sniff_separator(path_obj)
        return pl.read_csv(
            path,
            separator=sep,
            infer_schema_length=10000,
            ignore_errors=False,
        )

    raise ValueError("Input must end with .csv, .txt, .tsv, or .parquet")


def write_table(df: pl.DataFrame, path: str) -> None:
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    path_l = path.lower()

    if path_l.endswith(".parquet"):
        df.write_parquet(path)
    elif path_l.endswith(".csv"):
        df.write_csv(path)
    else:
        raise ValueError("Output must end with .csv or .parquet")


def load_pickle(path: str):
    with open(path, "rb") as f:
        return pickle.load(f)


# ============================================================
# Common helpers
# ============================================================

def normalize_name(x: str) -> str:
    return str(x).replace("-", ".").replace("_", ".").upper()


def validate_required_ids(df: pl.DataFrame, label: str) -> None:
    missing = [c for c in REQUIRED_ID_COLS if c not in df.columns]

    if missing:
        raise ValueError(f"{label} missing required ID columns: " + ", ".join(missing))

    bad_id_expr = pl.any_horizontal([
        pl.col(c).is_null() | (pl.col(c).cast(pl.Utf8).str.strip_chars() == "")
        for c in REQUIRED_ID_COLS
    ])

    n_bad_ids = df.select(bad_id_expr.sum().alias("n_bad_ids")).item()

    if n_bad_ids > 0:
        raise ValueError(
            f"{label} contains missing or empty values in required ID columns: "
            + ", ".join(REQUIRED_ID_COLS)
        )


def clean_required_ids(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns([
        pl.col(c).cast(pl.Utf8).str.strip_chars().alias(c)
        for c in REQUIRED_ID_COLS
    ])


def load_marker_list(marker_list_csv: str) -> list[str]:
    markers = read_table(marker_list_csv)

    if "marker_id" not in markers.columns:
        raise ValueError("Marker list must contain a column named 'marker_id'.")

    marker_ids = (
        markers
        .select(pl.col("marker_id").cast(pl.Utf8).str.strip_chars())
        .drop_nulls()
        .to_series()
        .to_list()
    )

    marker_ids = [m for m in marker_ids if m != ""]

    if len(marker_ids) == 0:
        raise ValueError("Marker list contains no valid markers.")

    return marker_ids


def resolve_marker_columns(marker_ids: list[str], data_columns: list[str]) -> list[str]:
    normalized_to_real = {}

    for col in data_columns:
        norm = normalize_name(col)

        if norm in normalized_to_real:
            raise ValueError(
                f"Ambiguous normalized column name '{norm}' maps to both "
                f"'{normalized_to_real[norm]}' and '{col}'."
            )

        normalized_to_real[norm] = col

    resolved = []
    missing = []

    for marker in marker_ids:
        norm = normalize_name(marker)

        if norm in normalized_to_real:
            resolved.append(normalized_to_real[norm])
        else:
            missing.append(marker)

    if missing:
        warnings.warn(
            "Markers not found and ignored: " + ", ".join(missing),
            RuntimeWarning,
        )

    if len(resolved) == 0:
        raise ValueError("None of the provided markers were found in the input data.")

    return resolved


def rapids_available() -> bool:
    try:
        import cupy as cp
        import cuml  # noqa: F401

        return cp.cuda.runtime.getDeviceCount() > 0
    except Exception:
        return False


def to_numpy(x) -> np.ndarray:
    if hasattr(x, "to_numpy"):
        return x.to_numpy()

    if hasattr(x, "get"):
        return x.get()

    return np.asarray(x)


def transform_umap(model, X: np.ndarray) -> np.ndarray:
    embedding = model.transform(X)
    embedding = to_numpy(embedding).astype(np.float32)
    return embedding


# ============================================================
# KNN mapping
# ============================================================

def knn_indices(
    X_query: np.ndarray,
    X_ref: np.ndarray,
    k: int,
    use_gpu: bool,
) -> tuple[np.ndarray, np.ndarray, str]:
    if use_gpu:
        try:
            from cuml.neighbors import NearestNeighbors as cuNearestNeighbors

            nn = cuNearestNeighbors(
                n_neighbors=int(k),
                metric="euclidean",
            )

            nn.fit(X_ref)

            distances, indices = nn.kneighbors(X_query)

            distances = to_numpy(distances)
            indices = to_numpy(indices)

            return distances, indices.astype(np.int64), "gpu"

        except Exception as e:
            warnings.warn(
                f"GPU NearestNeighbors failed; falling back to sklearn. Reason: {e}",
                RuntimeWarning,
            )

    from sklearn.neighbors import NearestNeighbors

    nn = NearestNeighbors(
        n_neighbors=int(k),
        metric="euclidean",
        algorithm="auto",
    )

    nn.fit(X_ref)

    distances, indices = nn.kneighbors(X_query)

    return distances, indices.astype(np.int64), "cpu"


def majority_vote_from_indices(
    indices: np.ndarray,
    labels_ref: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Faster majority vote for KNN labels.

    For each query row, vote among labels_ref[indices[row]].

    Returns:
        top_label
        top_fraction
        margin
        second_label
    """

    labels_ref = labels_ref.astype(str)

    # Encode labels once: string labels -> integer codes
    label_names, label_codes = np.unique(labels_ref, return_inverse=True)
    label_codes = label_codes.astype(np.int32)

    neighbor_codes = label_codes[indices]

    n_query, k = neighbor_codes.shape
    n_labels = len(label_names)

    top_codes = np.empty(n_query, dtype=np.int32)
    second_codes = np.empty(n_query, dtype=np.int32)
    top_fractions = np.empty(n_query, dtype=np.float32)
    margins = np.empty(n_query, dtype=np.float32)

    for i in range(n_query):
        counts = np.bincount(neighbor_codes[i], minlength=n_labels)

        # Top label
        top_code = int(np.argmax(counts))
        top_count = counts[top_code]

        # Second label
        counts[top_code] = -1
        second_code = int(np.argmax(counts))
        second_count = max(int(counts[second_code]), 0)

        top_codes[i] = top_code
        second_codes[i] = second_code
        top_fractions[i] = top_count / k
        margins[i] = (top_count - second_count) / k

    top_labels = label_names[top_codes]
    second_labels = label_names[second_codes]

    return top_labels, top_fractions, margins, second_labels


def assign_prediction_status(
    confidence: np.ndarray,
    high_threshold: float,
    medium_threshold: float,
) -> np.ndarray:
    out = np.empty(confidence.shape[0], dtype=object)

    out[confidence >= high_threshold] = "high_confidence"
    out[(confidence < high_threshold) & (confidence >= medium_threshold)] = "medium_confidence"
    out[confidence < medium_threshold] = "low_confidence"

    return out


# ============================================================
# Core
# ============================================================

# marker_list_csv = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/phenotypic_markers_n01_v01.csv'
# input_full_data = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/df_data_norm.parquet'
# input_umap = "/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/uMap.parquet"
# input_umap_model = "/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/uMap.pkl"
# input_cluster = "/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/phenograph.parquet"
# output_csv = "/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/cluster_mapping/phenograph_mapped_clusters.parquet"

def map_clusters(
    marker_list_csv: str,
    input_full_data: str,
    input_umap: str,
    input_umap_model: str,
    input_cluster: str,
    output_csv: str,
    n_neighbors_knn: int = 25,
    prediction_high_confidence: float = 0.80,
    prediction_medium_confidence: float = 0.60,
) -> None:
    print(f"### marker list: {marker_list_csv} ###")
    print(f"### input full data: {input_full_data} ###")
    print(f"### input sampled UMAP: {input_umap} ###")
    print(f"### input UMAP model: {input_umap_model} ###")
    print(f"### input sampled clusters: {input_cluster} ###")
    print(f"### output csv/parquet: {output_csv} ###")
    print(f"### KNN neighbors: {n_neighbors_knn} ###")
    print(f"### high confidence threshold: {prediction_high_confidence} ###")
    print(f"### medium confidence threshold: {prediction_medium_confidence} ###")

    use_gpu = rapids_available()

    if use_gpu:
        print("RAPIDS/cuML detected. GPU backend will be used where possible.")
    else:
        print("RAPIDS/cuML not detected. CPU backend will be used.")

    # --------------------------------------------------------
    # Load full normalized data
    # --------------------------------------------------------
    print("Loading full normalized data")
    df_full = read_table(input_full_data)
    validate_required_ids(df_full, "full normalized data")
    df_full = clean_required_ids(df_full)

    print("Loading marker list")
    marker_ids = load_marker_list(marker_list_csv)
    marker_cols = resolve_marker_columns(marker_ids, df_full.columns)

    print(f"{len(marker_cols)} markers used:")
    print(marker_cols)

    df_full = df_full.with_columns([
        pl.col(m).cast(pl.Float32, strict=False).alias(m)
        for m in marker_cols
    ])

    n_bad_full_marker_values = (
        df_full
        .select(marker_cols)
        .null_count()
        .select(pl.sum_horizontal(pl.all()).alias("n_bad_marker_values"))
        .item()
    )

    if n_bad_full_marker_values > 0:
        raise ValueError(
            f"{n_bad_full_marker_values} full-data marker values could not be converted to numeric."
        )

    # --------------------------------------------------------
    # Load sampled UMAP reference
    # --------------------------------------------------------
    print("Loading sampled UMAP reference")
    df_umap = read_table(input_umap)
    validate_required_ids(df_umap, "sampled UMAP")
    df_umap = clean_required_ids(df_umap)

    if "X" not in df_umap.columns or "Y" not in df_umap.columns:
        raise ValueError("Sampled UMAP file must contain columns 'X' and 'Y'.")

    df_umap = df_umap.with_columns([
        pl.col("X").cast(pl.Float32, strict=False).alias("uMap1"),
        pl.col("Y").cast(pl.Float32, strict=False).alias("uMap2"),
    ])

    # --------------------------------------------------------
    # Load sampled cluster labels
    # --------------------------------------------------------
    print("Loading sampled cluster labels")
    df_cluster = read_table(input_cluster)
    validate_required_ids(df_cluster, "sampled clusters")
    df_cluster = clean_required_ids(df_cluster)

    required_cluster_cols = {"cl_method", "cluster"}
    missing_cluster = required_cluster_cols - set(df_cluster.columns)

    if missing_cluster:
        raise ValueError(
            "Cluster file must contain columns: cl_method, cluster. "
            f"Missing: {sorted(missing_cluster)}"
        )

    df_cluster = df_cluster.with_columns([
        pl.col("cl_method").cast(pl.Utf8).str.strip_chars().alias("cl_method"),
        pl.col("cluster").cast(pl.Utf8).str.strip_chars().alias("cluster"),
    ])

    # --------------------------------------------------------
    # Build reference table: sampled UMAP + sampled cluster
    # --------------------------------------------------------
    print("Building sampled cluster reference")

    df_ref = (
        df_umap
        .select(REQUIRED_ID_COLS + ["uMap1", "uMap2"])
        .join(
            df_cluster.select(REQUIRED_ID_COLS + ["cl_method", "cluster"]),
            on=REQUIRED_ID_COLS,
            how="inner",
        )
    )

    if df_ref.height == 0:
        raise ValueError("No overlap between sampled UMAP and sampled cluster file.")

    cl_methods = df_ref.select("cl_method").unique().to_series().to_list()

    if len(cl_methods) != 1:
        raise ValueError(
            "MapClusters.py expects one clustering method per call. "
            f"Detected methods: {cl_methods}"
        )

    cl_method = str(cl_methods[0])

    print(f"Reference clustering method: {cl_method}")
    print(f"Reference cells: {df_ref.height}")

    X_ref = df_ref.select(["uMap1", "uMap2"]).to_numpy().astype(np.float32)
    labels_ref = df_ref.select("cluster").to_series().to_numpy().astype(object)

    if X_ref.shape[0] < 2:
        raise ValueError("At least two sampled reference cells are required.")

    # --------------------------------------------------------
    # Transform full data using saved UMAP model
    # --------------------------------------------------------
    print("Loading UMAP model")
    # Unpickling a CPU UMAP model imports its package initializer too.
    from umap_runtime import load_umap
    load_umap()
    umap_model = load_pickle(input_umap_model)

    print("Transforming full dataset into sampled UMAP space")
    X_full = df_full.select(marker_cols).to_numpy().astype(np.float32)
    embedding_full = transform_umap(umap_model, X_full)

    if embedding_full.shape[1] < 2:
        raise ValueError("UMAP transform returned fewer than 2 dimensions.")

    embedding_full = embedding_full[:, :2].astype(np.float32)

    print(f"Full UMAP shape: {embedding_full.shape}")

    # --------------------------------------------------------
    # KNN cluster mapping
    # --------------------------------------------------------
    print("Mapping clusters by KNN in UMAP space")

    k_predict = min(int(n_neighbors_knn), X_ref.shape[0])

    distances, indices, knn_backend = knn_indices(
        X_query=embedding_full,
        X_ref=X_ref,
        k=k_predict,
        use_gpu=use_gpu,
    )

    mapped_cluster, mapped_confidence, mapped_margin, second_cluster = majority_vote_from_indices(
        indices=indices,
        labels_ref=labels_ref,
    )

    prediction_status = assign_prediction_status(
        confidence=mapped_confidence,
        high_threshold=float(prediction_high_confidence),
        medium_threshold=float(prediction_medium_confidence),
    )

    print(f"KNN backend: {knn_backend}")

    output_cols = (
        REQUIRED_ID_COLS
        + [
            c for c in OPTIONAL_OUTPUT_COLS
            if c in df_full.columns and c not in REQUIRED_ID_COLS
        ]
    )

    df_out = (
        df_full
        .select(output_cols)
        .with_columns([
            pl.Series("uMap1", embedding_full[:, 0]),
            pl.Series("uMap2", embedding_full[:, 1]),
            pl.lit(cl_method).alias("cl_method"),
            pl.Series("cluster_mapped", mapped_cluster),
            pl.Series("cluster_second", second_cluster),
            pl.Series("cluster_confidence", mapped_confidence),
            pl.Series("cluster_margin", mapped_margin),
            pl.Series("cluster_prediction_status", prediction_status),
            pl.lit(k_predict).alias("n_neighbors"),
            pl.lit(knn_backend).alias("knn_backend"),
        ])
    )

    # Put reference label next to mapped label if present.
    preferred_output_order = [
        c for c in [
            "sample_id",
            "OID",
            "slide_id",
            "scene_id",
            "scan_region",
            "X",
            "Y",
            "s.area",
            "uMap1",
            "uMap2",
            "cl_method",
            "cluster_mapped",
            "cluster_second",
            "cluster_confidence",
            "cluster_margin",
            "cluster_prediction_status",
            "n_neighbors",
            "knn_backend",
        ]
        if c in df_out.columns
    ]

    remaining_cols = [c for c in df_out.columns if c not in preferred_output_order]
    df_out = df_out.select(preferred_output_order + remaining_cols)

    print("Writing mapped clusters")
    write_table(df_out, output_csv)

    # Summary next to output
    output_path = Path(output_csv)
    summary_path = output_path.with_name(output_path.stem + "_summary.csv")

    summary = (
        df_out
        .group_by(["cl_method", "cluster_mapped", "cluster_prediction_status"])
        .agg([
            pl.len().alias("N"),
            pl.col("cluster_confidence").mean().alias("mean_confidence"),
            pl.col("cluster_margin").mean().alias("mean_margin"),
        ])
        .sort(["cl_method", "cluster_mapped", "cluster_prediction_status"])
    )

    write_table(summary, str(summary_path))

    print("Done")


# ============================================================
# CLI
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Map sampled clustering labels to the full dataset using the saved UMAP model "
            "and KNN in UMAP space. Does not use annotation dictionaries."
        )
    )

    parser.add_argument(
        "--input.marker.list",
        required=True,
        help="Path to marker list csv/parquet.",
    )

    parser.add_argument(
        "--path.input.full.data",
        required=True,
        help="Path to full normalized data csv/parquet.",
    )

    parser.add_argument(
        "--path.input.umap",
        required=True,
        help="Path to sampled UMAP output csv/parquet.",
    )

    parser.add_argument(
        "--path.input.umap.model",
        required=True,
        help="Path to saved UMAP model pickle.",
    )

    parser.add_argument(
        "--path.input.cluster",
        required=True,
        help="Path to sampled clustering output csv/parquet for one method.",
    )

    parser.add_argument(
        "--path.output.csv",
        required=True,
        help="Path to output mapped cluster table csv/parquet.",
    )

    parser.add_argument(
        "--knn.n.neighbors",
        type=int,
        default=25,
        help="Number of neighbors for cluster label voting. Default: 25.",
    )

    parser.add_argument(
        "--prediction.high.confidence",
        type=float,
        default=0.80,
        help="Threshold for high-confidence cluster mappings. Default: 0.80.",
    )

    parser.add_argument(
        "--prediction.medium.confidence",
        type=float,
        default=0.60,
        help="Threshold for medium-confidence cluster mappings. Default: 0.60.",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    map_clusters(
        marker_list_csv=getattr(args, "input.marker.list"),
        input_full_data=getattr(args, "path.input.full.data"),
        input_umap=getattr(args, "path.input.umap"),
        input_umap_model=getattr(args, "path.input.umap.model"),
        input_cluster=getattr(args, "path.input.cluster"),
        output_csv=getattr(args, "path.output.csv"),
        n_neighbors_knn=getattr(args, "knn.n.neighbors"),
        prediction_high_confidence=getattr(args, "prediction.high.confidence"),
        prediction_medium_confidence=getattr(args, "prediction.medium.confidence"),
    )


if __name__ == "__main__":
    main()
