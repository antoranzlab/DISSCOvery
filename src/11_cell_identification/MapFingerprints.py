#!/usr/bin/env python3

import argparse
import csv
import pickle
import warnings
from pathlib import Path

import numpy as np
import polars as pl


REQUIRED_ID_COLS = ["sample_id", "OID"]
OPTIONAL_OUTPUT_COLS = ["slide_id", "scene_id", "scan_region", "X", "Y", "s.area"]


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


def save_pickle(obj, path: str) -> None:
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    with open(path_obj, "wb") as f:
        pickle.dump(obj, f)


# ============================================================
# General helpers
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


# ============================================================
# Reference building
# ============================================================

def load_consensus_annotations(path: str) -> pl.DataFrame:
    df = read_table(path)

    validate_required_ids(df, "consensus annotation data")
    df = clean_required_ids(df)

    if "CellType" not in df.columns:
        raise ValueError("Consensus annotation file must contain a 'CellType' column.")

    df = df.with_columns(
        pl.col("CellType").cast(pl.Utf8).str.strip_chars().alias("CellType")
    )

    n_bad = df.select(
        (
            pl.col("CellType").is_null()
            | (pl.col("CellType").str.strip_chars() == "")
        )
        .sum()
        .alias("n_bad")
    ).item()

    if n_bad > 0:
        raise ValueError("Consensus annotation file contains missing or empty CellType values.")

    return df.select(REQUIRED_ID_COLS + ["CellType"]).unique()


def build_annotated_reference(
    df_full: pl.DataFrame,
    df_consensus: pl.DataFrame,
    marker_cols: list[str],
) -> pl.DataFrame:
    df_ref = (
        df_full
        .select(REQUIRED_ID_COLS + marker_cols)
        .join(df_consensus, on=REQUIRED_ID_COLS, how="inner")
    )

    if df_ref.height == 0:
        raise ValueError("No overlap between full data and consensus annotations.")

    df_ref = df_ref.with_columns([
        pl.col(c).cast(pl.Float32, strict=False).alias(c)
        for c in marker_cols
    ])

    n_bad_marker_values = (
        df_ref
        .select(marker_cols)
        .null_count()
        .select(pl.sum_horizontal(pl.all()).alias("n_bad_marker_values"))
        .item()
    )

    if n_bad_marker_values > 0:
        raise ValueError(
            f"{n_bad_marker_values} marker values could not be converted to numeric "
            "in annotated reference data."
        )

    return df_ref


def balance_reference(
    df_ref: pl.DataFrame,
    max_cells_per_celltype: int,
    selected_seed: int,
) -> pl.DataFrame:
    if max_cells_per_celltype <= 0:
        print("Reference balancing disabled; using all annotated cells.")
        return df_ref

    rng = np.random.default_rng(int(selected_seed))

    parts = []

    celltypes = (
        df_ref
        .select("CellType")
        .unique()
        .sort("CellType")
        .to_series()
        .to_list()
    )

    for ct in celltypes:
        tmp = df_ref.filter(pl.col("CellType") == ct)
        n = tmp.height

        if n <= max_cells_per_celltype:
            parts.append(tmp)
        else:
            # Polars sample accepts seed but not a numpy generator.
            seed = int(rng.integers(0, 2**31 - 1))
            parts.append(
                tmp.sample(
                    n=max_cells_per_celltype,
                    with_replacement=False,
                    shuffle=True,
                    seed=seed,
                )
            )

    out = pl.concat(parts, how="vertical_relaxed")

    return out


# ============================================================
# UMAP + KNN backends
# ============================================================

def fit_umap(
    X_ref: np.ndarray,
    selected_seed: int,
    use_gpu: bool,
    n_neighbors_umap: int,
    min_dist: float,
):
    if use_gpu:
        try:
            from cuml.manifold import UMAP as cuUMAP

            model = cuUMAP(
                n_components=3,
                n_neighbors=int(n_neighbors_umap),
                min_dist=float(min_dist),
                random_state=int(selected_seed),
            )

            embedding = model.fit_transform(X_ref)
            embedding = to_numpy(embedding).astype(np.float32)

            return model, embedding, "gpu"

        except Exception as e:
            warnings.warn(
                f"GPU UMAP failed; falling back to CPU umap-learn. Reason: {e}",
                RuntimeWarning,
            )

    from umap_runtime import load_umap
    umap = load_umap()

    model = umap.UMAP(
        n_components=3,
        n_neighbors=int(n_neighbors_umap),
        min_dist=float(min_dist),
        random_state=int(selected_seed),
    )

    embedding = model.fit_transform(X_ref).astype(np.float32)

    return model, embedding, "cpu"


def transform_umap(model, X: np.ndarray) -> np.ndarray:
    embedding = model.transform(X)
    embedding = to_numpy(embedding).astype(np.float32)
    return embedding


def knn_indices(
    X_query: np.ndarray,
    X_ref: np.ndarray,
    k: int,
    use_gpu: bool,
) -> tuple[np.ndarray, np.ndarray, str]:
    """
    Returns distances and indices of k nearest neighbors.
    """

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
    For each query row, vote among labels_ref[indices[row]].

    Returns:
        top_label
        top_fraction
        margin
        second_label
    """

    n_query = indices.shape[0]

    top_labels = np.empty(n_query, dtype=object)
    second_labels = np.empty(n_query, dtype=object)
    top_fractions = np.zeros(n_query, dtype=np.float32)
    margins = np.zeros(n_query, dtype=np.float32)

    for i in range(n_query):
        labs = labels_ref[indices[i]]

        unique, counts = np.unique(labs, return_counts=True)
        order = np.argsort(counts)[::-1]

        top_label = unique[order[0]]
        top_count = counts[order[0]]
        top_fraction = top_count / len(labs)

        if len(order) > 1:
            second_label = unique[order[1]]
            second_fraction = counts[order[1]] / len(labs)
        else:
            second_label = ""
            second_fraction = 0.0

        top_labels[i] = top_label
        second_labels[i] = second_label
        top_fractions[i] = top_fraction
        margins[i] = top_fraction - second_fraction

    return top_labels, top_fractions, margins, second_labels


# ============================================================
# Reference refinement
# ============================================================

def internal_knn_refinement(
    embedding_ref: np.ndarray,
    labels_original: np.ndarray,
    n_neighbors: int,
    use_gpu: bool,
    refine_min_confidence: float,
    refine_min_margin: float,
) -> dict[str, np.ndarray]:
    """
    Internal KNN refinement of reference labels.

    Uses k+1 neighbors and removes the self neighbor when possible.
    """

    k_internal = min(int(n_neighbors) + 1, embedding_ref.shape[0])

    distances, indices, backend = knn_indices(
        X_query=embedding_ref,
        X_ref=embedding_ref,
        k=k_internal,
        use_gpu=use_gpu,
    )

    refined_indices = []

    for i in range(indices.shape[0]):
        row = indices[i]
        row_no_self = row[row != i]

        if row_no_self.shape[0] >= int(n_neighbors):
            row_no_self = row_no_self[:int(n_neighbors)]

        # Fallback for extremely small references.
        if row_no_self.shape[0] == 0:
            row_no_self = row[:1]

        refined_indices.append(row_no_self)

    # Pad to equal length if needed.
    max_k = max(len(x) for x in refined_indices)
    padded = np.zeros((len(refined_indices), max_k), dtype=np.int64)

    for i, row in enumerate(refined_indices):
        if len(row) < max_k:
            padded[i, :] = np.pad(row, (0, max_k - len(row)), mode="edge")
        else:
            padded[i, :] = row

    knn_label, confidence, margin, second_label = majority_vote_from_indices(
        indices=padded,
        labels_ref=labels_original,
    )

    labels_refined = labels_original.copy().astype(object)
    status = np.empty(labels_original.shape[0], dtype=object)

    for i in range(labels_original.shape[0]):
        if knn_label[i] == labels_original[i]:
            labels_refined[i] = labels_original[i]
            status[i] = "stable"
        elif confidence[i] >= refine_min_confidence and margin[i] >= refine_min_margin:
            labels_refined[i] = knn_label[i]
            status[i] = "relabelled"
        else:
            labels_refined[i] = labels_original[i]
            status[i] = "kept_low_confidence"

    return {
        "reference_knn_CellType": knn_label,
        "reference_knn_second_CellType": second_label,
        "reference_knn_confidence": confidence,
        "reference_knn_margin": margin,
        "CellType_refined": labels_refined,
        "refinement_status": status,
        "internal_knn_backend": np.array([backend] * labels_original.shape[0], dtype=object),
    }


# ============================================================
# Output helpers
# ============================================================

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


def build_celltype_fingerprints(
    df_reference: pl.DataFrame,
    marker_cols: list[str],
    label_col: str = "CellType_refined",
) -> pl.DataFrame:
    return (
        df_reference
        .group_by(label_col)
        .agg([
            pl.col(m).mean().alias(m)
            for m in marker_cols
        ])
        .rename({label_col: "CellType"})
        .sort("CellType")
    )


def write_per_sample_outputs(
    df_predictions: pl.DataFrame,
    output_folder: Path,
    node_id: str,
    version_id: str,
) -> None:
    data_annotated_dir = output_folder / "data_annotated"
    data_annotated_dir.mkdir(parents=True, exist_ok=True)

    if "sample_id" not in df_predictions.columns:
        return

    samples = (
        df_predictions
        .select("sample_id")
        .unique()
        .sort("sample_id")
        .to_series()
        .to_list()
    )

    for sample_id in samples:
        tmp = df_predictions.filter(pl.col("sample_id") == sample_id)

        safe_sample_id = str(sample_id).replace("/", "_").replace(" ", "_")

        cols = [
            c for c in [
                "sample_id",
                "slide_id",
                "scene_id",
                "OID",
                "X",
                "Y",
                "CellType",
                "prediction_confidence",
                "prediction_margin",
                "prediction_status",
            ]
            if c in tmp.columns
        ]

        tmp_out = tmp.select(cols).with_columns([
            pl.lit(node_id).alias("node_id"),
            pl.lit(version_id).alias("version_id"),
        ])

        write_table(tmp_out, str(data_annotated_dir / f"{safe_sample_id}.csv"))


# ============================================================
# Main function
# ============================================================

# marker_list_csv = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/phenotypic_markers_n01_v01.csv'
# input_full_data = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/df_data_norm.parquet'
# input_consensus = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/df_data_consensus.parquet'
# output_folder = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01'
# node_id = 'n01'
# version_id = 'v01'

def map_fingerprints(
    marker_list_csv: str,
    input_full_data: str,
    input_consensus: str,
    output_folder: str,
    node_id: str,
    version_id: str,
    max_cells_per_celltype: int = 500,
    n_neighbors_umap: int = 25,
    min_dist: float = 0.1,
    n_neighbors_knn: int = 25,
    selected_seed: int = 1234,
    refine_min_confidence: float = 0.60,
    refine_min_margin: float = 0.10,
    prediction_high_confidence: float = 0.80,
    prediction_medium_confidence: float = 0.60,
    write_per_sample_files: int = 1,
) -> None:
    print(f"### marker list: {marker_list_csv} ###")
    print(f"### input full data: {input_full_data} ###")
    print(f"### input consensus annotations: {input_consensus} ###")
    print(f"### output folder: {output_folder} ###")
    print(f"### node_id: {node_id} ###")
    print(f"### version_id: {version_id} ###")
    print(f"### max cells per CellType: {max_cells_per_celltype} ###")
    print(f"### UMAP neighbors: {n_neighbors_umap} ###")
    print(f"### UMAP min_dist: {min_dist} ###")
    print(f"### KNN neighbors: {n_neighbors_knn} ###")
    print(f"### selected seed: {selected_seed} ###")
    print(f"### refine min confidence: {refine_min_confidence} ###")
    print(f"### refine min margin: {refine_min_margin} ###")

    out_dir = Path(output_folder)
    mapping_dir = out_dir / "fingerprint_mapping"
    mapping_dir.mkdir(parents=True, exist_ok=True)

    use_gpu = rapids_available()

    if use_gpu:
        print("RAPIDS/cuML detected. GPU backend will be used where possible.")
    else:
        print("RAPIDS/cuML not detected. CPU backend will be used.")

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

    print("Loading consensus annotations")
    df_consensus = load_consensus_annotations(input_consensus)

    print("Building annotated reference")
    df_ref_all = build_annotated_reference(
        df_full=df_full,
        df_consensus=df_consensus,
        marker_cols=marker_cols,
    )

    print(f"Annotated reference cells before balancing: {df_ref_all.height}")

    print("Balancing reference")
    df_ref = balance_reference(
        df_ref=df_ref_all,
        max_cells_per_celltype=int(max_cells_per_celltype),
        selected_seed=int(selected_seed),
    )

    print(f"Reference cells after balancing: {df_ref.height}")

    celltype_counts = (
        df_ref
        .group_by("CellType")
        .len()
        .rename({"len": "N"})
        .sort("CellType")
    )
    write_table(celltype_counts, str(mapping_dir / "reference_celltype_counts.csv"))

    X_ref = df_ref.select(marker_cols).to_numpy().astype(np.float32)
    labels_original = df_ref.select("CellType").to_series().to_numpy().astype(object)

    if X_ref.shape[0] < 3:
        raise ValueError("At least three annotated reference cells are required.")

    if len(np.unique(labels_original)) < 1:
        raise ValueError("No valid CellType labels found in reference.")

    print("Fitting 3D UMAP reference model")
    umap_model, embedding_ref, umap_backend = fit_umap(
        X_ref=X_ref,
        selected_seed=int(selected_seed),
        use_gpu=use_gpu,
        n_neighbors_umap=int(n_neighbors_umap),
        min_dist=float(min_dist),
    )

    print(f"UMAP backend: {umap_backend}")
    print(f"Reference UMAP shape: {embedding_ref.shape}")

    print("Running internal reference KNN refinement")
    reference_qc = internal_knn_refinement(
        embedding_ref=embedding_ref,
        labels_original=labels_original,
        n_neighbors=int(n_neighbors_knn),
        use_gpu=use_gpu,
        refine_min_confidence=float(refine_min_confidence),
        refine_min_margin=float(refine_min_margin),
    )

    df_ref_out = df_ref.with_columns([
        pl.Series("uMap1", embedding_ref[:, 0]),
        pl.Series("uMap2", embedding_ref[:, 1]),
        pl.Series("uMap3", embedding_ref[:, 2]),
        pl.Series("CellType_cluster", labels_original),
        pl.Series("reference_knn_CellType", reference_qc["reference_knn_CellType"]),
        pl.Series("reference_knn_second_CellType", reference_qc["reference_knn_second_CellType"]),
        pl.Series("reference_knn_confidence", reference_qc["reference_knn_confidence"]),
        pl.Series("reference_knn_margin", reference_qc["reference_knn_margin"]),
        pl.Series("CellType_refined", reference_qc["CellType_refined"]),
        pl.Series("refinement_status", reference_qc["refinement_status"]),
        pl.Series("internal_knn_backend", reference_qc["internal_knn_backend"]),
    ])

    write_table(df_ref_out, str(mapping_dir / "fingerprint_reference.parquet"))
    write_table(
        df_ref_out.select(
            REQUIRED_ID_COLS
            + ["CellType_cluster", "CellType_refined", "reference_knn_confidence", "reference_knn_margin", "refinement_status"]
        ),
        str(mapping_dir / "fingerprint_reference_qc.csv"),
    )

    refinement_summary = (
        df_ref_out
        .group_by(["CellType_cluster", "CellType_refined", "refinement_status"])
        .len()
        .rename({"len": "N"})
        .sort(["CellType_cluster", "CellType_refined", "refinement_status"])
    )
    write_table(refinement_summary, str(mapping_dir / "fingerprint_reference_refinement_summary.csv"))

    print("Saving UMAP model")
    save_pickle(umap_model, str(mapping_dir / "fingerprint_umap_model.pkl"))

    print("Computing cell-type fingerprints")
    fingerprints = build_celltype_fingerprints(
        df_reference=df_ref_out,
        marker_cols=marker_cols,
        label_col="CellType_refined",
    )
    write_table(fingerprints, str(mapping_dir / "celltype_fingerprints.parquet"))
    write_table(fingerprints, str(mapping_dir / "celltype_fingerprints.csv"))

    print("Transforming full dataset to UMAP space")
    X_full = df_full.select(marker_cols).to_numpy().astype(np.float32)
    embedding_full = transform_umap(umap_model, X_full)

    print(f"Full UMAP shape: {embedding_full.shape}")

    print("Predicting all cells by KNN in UMAP space")
    labels_refined = df_ref_out.select("CellType_refined").to_series().to_numpy().astype(object)

    k_predict = min(int(n_neighbors_knn), embedding_ref.shape[0])

    # print(f"X_query shape: {embedding_full.shape}")
    # print(np.isnan(embedding_full.shape).sum())
    # print(f"X_ref shape: {embedding_ref.shape}")
    # print(np.isnan(embedding_ref.shape).sum())

    distances, indices, knn_backend = knn_indices(
        X_query=embedding_full,
        X_ref=embedding_ref,
        k=k_predict,
        use_gpu=use_gpu,
    )

    pred_label, pred_confidence, pred_margin, pred_second_label = majority_vote_from_indices(
        indices=indices,
        labels_ref=labels_refined,
    )

    prediction_status = assign_prediction_status(
        confidence=pred_confidence,
        high_threshold=float(prediction_high_confidence),
        medium_threshold=float(prediction_medium_confidence),
    )

    print(f"KNN backend: {knn_backend}")

    output_cols = REQUIRED_ID_COLS + [c for c in OPTIONAL_OUTPUT_COLS if c in df_full.columns and c not in REQUIRED_ID_COLS]

    df_predictions = (
        df_full
        .select(output_cols)
        .with_columns([
            pl.Series("uMap1", embedding_full[:, 0]),
            pl.Series("uMap2", embedding_full[:, 1]),
            pl.Series("uMap3", embedding_full[:, 2]),
            pl.Series("CellType", pred_label),
            pl.Series("CellType_second", pred_second_label),
            pl.Series("prediction_confidence", pred_confidence),
            pl.Series("prediction_margin", pred_margin),
            pl.Series("prediction_status", prediction_status),
            pl.lit(k_predict).alias("n_neighbors"),
            pl.lit(knn_backend).alias("knn_backend"),
            pl.lit(node_id).alias("node_id"),
            pl.lit(version_id).alias("version_id"),
        ])
    )

    print("Writing prediction outputs")
    write_table(df_predictions, str(mapping_dir / "fingerprint_predictions.parquet"))
    # write_table(df_predictions, str(mapping_dir / "fingerprint_predictions.csv"))

    annotation_log_cols = [
        c for c in [
            "sample_id",
            "slide_id",
            "scene_id",
            "OID",
            "X",
            "Y",
            "CellType",
            "prediction_confidence",
            "prediction_margin",
            "prediction_status",
            "node_id",
            "version_id",
        ]
        if c in df_predictions.columns
    ]

    # write_table(
    #     df_predictions.select(annotation_log_cols),
    #     str(out_dir / "annotation_log.csv"),
    # )

    write_table(
        df_predictions.select(annotation_log_cols),
        str(out_dir / "annotation_log.parquet"),
    )

    celltypes = (
        df_predictions
        .group_by("CellType")
        .len()
        .rename({"len": "N"})
        .sort("CellType")
        .with_columns(pl.lit(1).alias("include"))
    )

    write_table(celltypes, str(out_dir / "celltypes.csv"))
    write_table(celltypes, str(mapping_dir / "fingerprint_prediction_summary.csv"))

    if int(write_per_sample_files) == 1:
        print("Writing per-sample annotated outputs")
        write_per_sample_outputs(
            df_predictions=df_predictions,
            output_folder=out_dir,
            node_id=node_id,
            version_id=version_id,
        )

    print("Done")


# ============================================================
# CLI
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Map cluster/consensus annotations to the full dataset using UMAP + KNN fingerprints."
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
        "--path.input.consensus",
        required=True,
        help="Path to consensus annotations csv/parquet.",
    )

    parser.add_argument(
        "--path.output.folder",
        required=True,
        help="Output folder.",
    )

    parser.add_argument(
        "--node.id",
        required=True,
        help="Node identifier, e.g. n01.",
    )

    parser.add_argument(
        "--version.id",
        required=True,
        help="Version identifier, e.g. v01.",
    )

    parser.add_argument(
        "--max.cells.per.celltype",
        type=int,
        default=2500,
        help="Maximum reference cells per CellType. Use <=0 to disable balancing. Default: 2500.",
    )

    parser.add_argument(
        "--umap.n.neighbors",
        type=int,
        default=15,
        help="UMAP n_neighbors. Default: 15.",
    )

    parser.add_argument(
        "--umap.min.dist",
        type=float,
        default=0.1,
        help="UMAP min_dist. Default: 0.1.",
    )

    parser.add_argument(
        "--knn.n.neighbors",
        type=int,
        default=25,
        help="Number of KNN neighbors for refinement and prediction. Default: 25.",
    )

    parser.add_argument(
        "--selected.seed",
        type=int,
        default=1234,
        help="Selected seed. Default: 1234.",
    )

    parser.add_argument(
        "--refine.min.confidence",
        type=float,
        default=0.60,
        help="Minimum internal KNN confidence to relabel reference cells. Default: 0.60.",
    )

    parser.add_argument(
        "--refine.min.margin",
        type=float,
        default=0.10,
        help="Minimum internal KNN margin to relabel reference cells. Default: 0.10.",
    )

    parser.add_argument(
        "--prediction.high.confidence",
        type=float,
        default=0.80,
        help="Threshold for high-confidence predictions. Default: 0.80.",
    )

    parser.add_argument(
        "--prediction.medium.confidence",
        type=float,
        default=0.60,
        help="Threshold for medium-confidence predictions. Default: 0.60.",
    )

    parser.add_argument(
        "--write.per.sample.files",
        type=int,
        default=1,
        choices=[0, 1],
        help="Write one annotated CSV per sample_id. Default: 1.",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    map_fingerprints(
        marker_list_csv=getattr(args, "input.marker.list"),
        input_full_data=getattr(args, "path.input.full.data"),
        input_consensus=getattr(args, "path.input.consensus"),
        output_folder=getattr(args, "path.output.folder"),
        node_id=getattr(args, "node.id"),
        version_id=getattr(args, "version.id"),
        max_cells_per_celltype=getattr(args, "max.cells.per.celltype"),
        n_neighbors_umap=getattr(args, "umap.n.neighbors"),
        min_dist=getattr(args, "umap.min.dist"),
        n_neighbors_knn=getattr(args, "knn.n.neighbors"),
        selected_seed=getattr(args, "selected.seed"),
        refine_min_confidence=getattr(args, "refine.min.confidence"),
        refine_min_margin=getattr(args, "refine.min.margin"),
        prediction_high_confidence=getattr(args, "prediction.high.confidence"),
        prediction_medium_confidence=getattr(args, "prediction.medium.confidence"),
        write_per_sample_files=getattr(args, "write.per.sample.files"),
    )


if __name__ == "__main__":
    main()
