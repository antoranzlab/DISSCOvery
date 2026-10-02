#!/usr/bin/env python3

import argparse
import csv
import warnings
from pathlib import Path

import numpy as np
import polars as pl

REQUIRED_ID_COLS = ["sample_id", "OID"]
PREFERRED_ID_COLS = ["sample_id", "OID", "slide_id", "scene_id", "scan_region", "X", "Y", "s.area"]

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
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    path_l = path.lower()

    if path_l.endswith(".parquet"):
        df.write_parquet(path)
    elif path_l.endswith(".csv"):
        df.write_csv(path)
    else:
        raise ValueError("Output must end with .csv or .parquet")


def normalize_name(s: str) -> str:
    return str(s).replace("-", ".").upper()


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

    resolved_cols = []
    missing_markers = []

    for marker in marker_ids:
        norm_marker = normalize_name(marker)

        if norm_marker in normalized_to_real:
            resolved_cols.append(normalized_to_real[norm_marker])
        else:
            missing_markers.append(marker)

    if missing_markers:
        warnings.warn(
            "The following markers were not found and will be ignored: "
            + ", ".join(missing_markers),
            RuntimeWarning,
        )

    if len(resolved_cols) == 0:
        raise ValueError("None of the provided markers were found in the input data.")

    return resolved_cols


def validate_required_ids(df: pl.DataFrame, label: str) -> None:
    missing = [c for c in REQUIRED_ID_COLS if c not in df.columns]

    if missing:
        raise ValueError(
            f"{label} is missing required ID columns: " + ", ".join(missing)
        )

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


def rapids_available() -> bool:
    try:
        import cupy as cp
        import cuml  # noqa: F401

        return cp.cuda.runtime.getDeviceCount() > 0

    except Exception:
        return False


def to_numpy_layout(x) -> np.ndarray:
    if hasattr(x, "to_numpy"):
        return x.to_numpy()

    if hasattr(x, "get"):
        return x.get()

    return np.asarray(x)

def _jaccard_knn_graph(X: np.ndarray, k: int = 30) -> "sp.coo_matrix":
    # Jaccard-weighted kNN graph, PhenoGraph's own construction (k=30, euclidean,
    # undirected/averaged symmetrization -- its defaults, matched here so results are
    # equivalent to phenograph.cluster(X, n_jobs=1)). Reimplemented rather than calling
    # phenograph directly: the phenograph package unconditionally imports leidenalg
    # (GPL-3.0-or-later) and igraph (GPL-2.0) even though this call never uses them, and
    # its actual default community-detection path (Louvain) shells out to a vendored
    # binary whose license forbids redistribution without the authors' agreement -- worse
    # than GPL for our purposes. This graph-construction step itself has no such issue.
    from scipy import sparse as sp
    from sklearn.neighbors import NearestNeighbors

    nbrs = NearestNeighbors(n_neighbors=k + 1, metric="euclidean").fit(X)
    _, idx = nbrs.kneighbors(X)
    idx = idx[:, 1:] if idx[0, 0] == 0 else idx[:, :-1]

    n = idx.shape[0]
    s = []
    for i in range(n):
        shared = np.fromiter(
            (len(set(idx[i]).intersection(set(idx[j]))) for j in idx[i]), dtype=float
        )
        s.extend(shared / (2 * k - shared))
    row = np.concatenate([np.full(k, i) for i in range(n)])
    col = np.concatenate(idx)
    graph = sp.coo_matrix((s, (row, col)), shape=(n, n))
    return (graph + graph.transpose()).multiply(0.5).tocsr()


def _sort_clusters_by_size(clusters: np.ndarray, min_size: int = 10) -> np.ndarray:
    labels, counts = np.unique(clusters, return_counts=True)
    order = np.argsort(counts)[::-1]
    remap = {labels[i]: (rank if counts[i] > min_size else -1) for rank, i in enumerate(order)}
    return np.vectorize(remap.get)(clusters)


def run_graph_clustering(X: np.ndarray, random_state: int = 1234) -> np.ndarray:
    import random

    random.seed(int(random_state))
    np.random.seed(int(random_state))

    try:
        from sknetwork.clustering import Louvain
    except ImportError as e:
        raise ImportError("Please install scikit-network: pip install scikit-network") from e

    graph = _jaccard_knn_graph(X, k=30)
    communities = Louvain(resolution=1.0, random_state=int(random_state)).fit_predict(graph)
    communities = _sort_clusters_by_size(communities, min_size=10)
    return communities.astype(str)

def run_kmeans(
    X: np.ndarray,
    n_clusters: int,
    random_state: int,
    use_gpu: bool,
) -> np.ndarray:
    if use_gpu:
        try:
            from cuml.cluster import KMeans as cuKMeans

            model = cuKMeans(
                n_clusters=int(n_clusters),
                random_state=int(random_state),
                max_iter=300,
            )

            labels = model.fit_predict(X)
            labels = to_numpy_layout(labels)

            return labels.astype(int).astype(str)

        except Exception as e:
            warnings.warn(
                f"GPU KMeans failed; falling back to sklearn KMeans. Reason: {e}",
                RuntimeWarning,
            )

    from sklearn.cluster import KMeans

    model = KMeans(
        n_clusters=int(n_clusters),
        n_init=10,
        max_iter=300,
        random_state=int(random_state),
    )

    labels = model.fit_predict(X)

    return labels.astype(int).astype(str)


def run_som(
    X: np.ndarray,
    n_clusters: int,
    random_state: int,
    som_x: int = 10,
    som_y: int = 10,
    num_iteration: int = 2000,
) -> np.ndarray:
    try:
        from minisom import MiniSom
        from sklearn.cluster import AgglomerativeClustering
    except ImportError as e:
        raise ImportError(
            "Please install minisom and scikit-learn: pip install minisom scikit-learn"
        ) from e

    som = MiniSom(
        som_x,
        som_y,
        X.shape[1],
        sigma=1.0,
        learning_rate=0.5,
        random_seed=int(random_state),
    )

    som.random_weights_init(X)
    som.train_random(X, num_iteration=int(num_iteration))

    bmus = np.array([som.winner(x) for x in X])
    bmu_idx = bmus[:, 0] * som_y + bmus[:, 1]

    codebook = som.get_weights().reshape(som_x * som_y, X.shape[1])

    meta = AgglomerativeClustering(n_clusters=int(n_clusters))
    meta_labels = meta.fit_predict(codebook)

    labels = meta_labels[bmu_idx]

    return labels.astype(int).astype(str)

# 
# marker_list_csv = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/phenotypic_markers_n01_v01.csv'
# input_csv = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/df_data_sampled.parquet'
# output_csv = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/phenograph.parquet'
# cl_method = 'phenograph'
# n_clusters = None
# random_state = 1234

def clustering(
    marker_list_csv: str,
    input_csv: str,
    output_csv: str,
    cl_method: str,
    n_clusters = None,
    random_state: int = 1234,
) -> None:
    print(f"### list of markers csv: {marker_list_csv} ###")
    print(f"### input csv: {input_csv} ###")
    print(f"### output csv: {output_csv} ###")
    print(f"### clustering method: {cl_method} ###")
    print(f"### number of clusters: {n_clusters if n_clusters is not None else 'no need to specify'} ###")
    print(f"### selected seed: {random_state} ###")
    
    # Load markers
    print("Loading list of markers")
    marker_ids = load_marker_list(marker_list_csv)
    print(f"{len(marker_ids)} markers requested")

    # Load data
    print("Loading data file")
    df_data = read_table(input_csv)
    
    validate_required_ids(df_data, "input data")
    
    df_data = df_data.with_columns(pl.col("sample_id").cast(pl.Utf8).str.strip_chars().alias("sample_id"))

    marker_cols = resolve_marker_columns(marker_ids, df_data.columns)

    print(f"{len(marker_cols)} markers found in input data")
    print("Markers used:")
    print(marker_cols)

    marker_df = df_data.select([pl.col(c).cast(pl.Float32, strict=False).alias(c) for c in marker_cols])
    
    n_bad_marker_values = (
        marker_df
        .null_count()
        .select(pl.sum_horizontal(pl.all()).alias("n_bad_marker_values"))
        .item()
    )

    if n_bad_marker_values > 0:
        raise ValueError(
            f"{n_bad_marker_values} marker values could not be converted to numeric. "
            "Please check marker columns before clustering."
        )

    X = marker_df.to_numpy()

    print(f"X shape: {X.shape}")
    print(f"X dtype: {X.dtype}")

    if X.shape[0] < 2:
        raise ValueError("At least two rows are required for clustering.")

    method = cl_method.strip().lower()

    use_gpu = rapids_available()

    if use_gpu:
        print("RAPIDS/cuML detected. GPU will be used where supported.")
    else:
        print("RAPIDS/cuML not detected. CPU backend will be used.")

    print("Clustering")
    
    if method == "phenograph":
        clusters = run_graph_clustering(X, random_state=random_state)
        cl_method_label = "phenograph"

    elif method == "kmeans":
        if n_clusters is None:
            raise ValueError("kmeans requires --number.of.clusters")

        clusters = run_kmeans(
            X=X,
            n_clusters=int(n_clusters),
            random_state=int(random_state),
            use_gpu=use_gpu,
        )
        cl_method_label = "kmeans"

    elif method == "som":
        if n_clusters is None:
            raise ValueError("som requires --number.of.clusters")

        clusters = run_som(
            X=X,
            n_clusters=int(n_clusters),
            random_state=int(random_state),
        )
        cl_method_label = "som"

    else:
        raise ValueError("clustering method not valid. Choose between: phenograph, kmeans, som.")

    if len(clusters) != df_data.height:
        raise RuntimeError(
            f"Number of cluster labels ({len(clusters)}) does not match "
            f"number of input rows ({df_data.height})."
        )

    id_cols = [c for c in PREFERRED_ID_COLS if c in df_data.columns]
    id_cols_no_xy = [c for c in id_cols if c not in {"X", "Y"}]
    
    df_out = (
        df_data
        .select(id_cols_no_xy)
        .with_columns([
            pl.lit(cl_method_label).alias("cl_method"),
            pl.Series("cluster", clusters),
        ])
    )
    
    print("Writing output")
    write_table(df_out, output_csv)

    print("Done")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clustering.")
    parser.add_argument("--input.marker.list", required=True, help="List of markers csv/parquet.")
    parser.add_argument("--path.input.csv", required=True, help="Path to input sampled data csv/parquet.")
    parser.add_argument("--path.output.csv", required=True, help="Path to output clustering results csv/parquet.")
    parser.add_argument("--clustering.method", required=True, help="phenograph, kmeans, som.")
    parser.add_argument("--number.of.clusters", type=int, default=None, help="Number of clusters, required for kmeans and som.")
    parser.add_argument("--selected.seed", type=int, default=1234, help="Selected seed for reproducibility. Default: 42.")

    return parser


def main() -> None:
    args = build_parser().parse_args()

    clustering(
        marker_list_csv=getattr(args, "input.marker.list"),
        input_csv=getattr(args, "path.input.csv"),
        output_csv=getattr(args, "path.output.csv"),
        cl_method=getattr(args, "clustering.method"),
        n_clusters=getattr(args, "number.of.clusters"),
        random_state=getattr(args, "selected.seed"),
    )


if __name__ == "__main__":
    main()
