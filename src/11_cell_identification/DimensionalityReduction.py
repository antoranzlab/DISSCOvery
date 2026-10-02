#!/usr/bin/env python3

import argparse
import csv
import pickle
import warnings
from pathlib import Path

import numpy as np
import polars as pl

REQUIRED_ID_COLS = ["sample_id", "OID"]
PREFERRED_ID_COLS = ["sample_id", "slide_id", "scene_id", "scan_region", "OID", "X", "Y", "s.area"]

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
    out_dir = Path(path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    path_l = path.lower()

    if path_l.endswith(".parquet"):
        df.write_parquet(path)
    elif path_l.endswith(".csv"):
        df.write_csv(path)
    else:
        raise ValueError("Output must end with .csv or .parquet")

def save_model(obj, path: str) -> None:
    out_dir = Path(path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(path, "wb") as f:
        pickle.dump(obj, f)

def normalize_colname(col: str) -> str:
    return str(col).replace("-", ".").upper()

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
    """
    Resolve marker names from the marker list against actual dataframe columns.

    This allows marker lists such as CD38, cd38, CD-38, etc.,
    while preserving the original dataframe column names.
    """
    normalized_to_real = {}

    for col in data_columns:
        norm = normalize_colname(col)

        if norm in normalized_to_real:
            raise ValueError(
                f"Ambiguous normalized column name '{norm}' maps to both "
                f"'{normalized_to_real[norm]}' and '{col}'."
            )

        normalized_to_real[norm] = col

    resolved_cols = []
    missing_markers = []

    for marker in marker_ids:
        norm_marker = normalize_colname(marker)

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

def rapids_available() -> bool:
    try:
        import cupy as cp
        import cuml  # noqa: F401

        return cp.cuda.runtime.getDeviceCount() > 0

    except Exception:
        return False

def to_numpy_layout(layout) -> np.ndarray:
    """
    Convert cuML / CuPy / cuDF / NumPy layout objects to a NumPy array.
    """
    if hasattr(layout, "to_numpy"):
        return layout.to_numpy()

    if hasattr(layout, "get"):
        return layout.get()

    return np.asarray(layout)

# marker_list_csv = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/phenotypic_markers_n01_v01.csv'
# input_csv = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/df_data_sampled.parquet'
# output_csv = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/uMap.parquet'
# output_model = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/uMap.pkl'
# dr_method = 'uMap'
# selected_seed = 1234

def dimensionality_reduction(
    marker_list_csv: str,
    input_csv: str,
    output_csv: str,
    output_model: str,
    dr_method: str,
    selected_seed: int = 1234,
) -> None:
    print(f"### list of markers csv: {marker_list_csv} ###")
    print(f"### input csv/parquet: {input_csv} ###")
    print(f"### output csv/parquet: {output_csv} ###")
    print(f"### output model: {output_model} ###")
    print(f"### dimensionality reduction method: {dr_method} ###")
    print(f"### selected seed: {selected_seed} ###")

    # Load marker list
    print("Loading marker list")
    marker_ids = load_marker_list(marker_list_csv)
    print(f"{len(marker_ids)} markers requested")
    
    # Load data
    print("Loading input data")
    df_data = read_table(input_csv)

    missing_required_ids = [c for c in REQUIRED_ID_COLS if c not in df_data.columns]

    if missing_required_ids:
        raise ValueError(
            "Missing required ID columns: " + ", ".join(missing_required_ids)
        )

    df_data = df_data.with_columns([pl.col(c).cast(pl.Utf8).str.strip_chars().alias(c) for c in REQUIRED_ID_COLS])
    bad_id_expr = pl.any_horizontal([pl.col(c).is_null() | (pl.col(c).cast(pl.Utf8).str.strip_chars() == "") for c in REQUIRED_ID_COLS])
    n_bad_ids = df_data.select(bad_id_expr.sum().alias("n_bad_ids")).item()

    if n_bad_ids > 0:
        raise ValueError(
            "Required ID columns contain missing or empty values: " + ", ".join(REQUIRED_ID_COLS)
        )

    # Normalize column names
    marker_cols = resolve_marker_columns(marker_ids, df_data.columns)

    print(f"{len(marker_cols)} markers found in input data")
    print("Markers used:")
    print(marker_cols)
    
    marker_df = df_data.select([pl.col(c).cast(pl.Float32, strict=False).alias(c) for c in marker_cols])
    
    n_bad_marker_values = marker_df.null_count().select(pl.sum_horizontal(pl.all()).alias("n_bad_marker_values")).item()

    if n_bad_marker_values > 0:
        raise ValueError(
            f"{n_bad_marker_values} marker values could not be converted to numeric. "
            "Please check marker columns before dimensionality reduction."
        )

    Xmat = marker_df.to_numpy()

    print(f"Xmat shape: {Xmat.shape}")
    print(f"Xmat dtype: {Xmat.dtype}")
    
    if Xmat.shape[0] < 2:
        raise ValueError("At least two rows are required for dimensionality reduction.")

    print("Running dimensionality reduction")

    use_gpu = rapids_available()

    if use_gpu:
        print("RAPIDS/cuML detected. Using GPU backend where supported.")
    else:
        print("RAPIDS/cuML not detected. Using CPU backend.")
    
    method = dr_method.strip().lower()

    if method == "umap":
        if use_gpu:
            from cuml.manifold import UMAP as cuUMAP
    
            reducer = cuUMAP(
                n_components=2,
                random_state=int(selected_seed),
            )
    
            layout = reducer.fit_transform(Xmat)
            layout = to_numpy_layout(layout)
            method_label = "uMap"
    
        else:
            from umap_runtime import load_umap
            umap = load_umap()

            reducer = umap.UMAP(
                n_components=2,
                random_state=int(selected_seed),
            )
    
            layout = reducer.fit_transform(Xmat)
            method_label = "uMap"
        
    elif method == "tsne":
        if Xmat.shape[0] <= 20:
            perplexity = max(1, Xmat.shape[0] // 3)
        else:
            perplexity = 20

        if use_gpu:
            from cuml.manifold import TSNE as cuTSNE

            reducer = cuTSNE(
                n_components=2,
                perplexity=perplexity,
                random_state=int(selected_seed),
            )

            layout = reducer.fit_transform(Xmat)
            layout = to_numpy_layout(layout)
            method_label = "tsne"

        else:
            from sklearn.manifold import TSNE

            reducer = TSNE(
                n_components=2,
                perplexity=perplexity,
                init="random",
                random_state=int(selected_seed),
            )
    
            layout = reducer.fit_transform(Xmat)
            method_label = "tsne"

    elif method == "pca":
        if use_gpu:
            from cuml.decomposition import PCA as cuPCA
    
            reducer = cuPCA(
                n_components=2,
            )
    
            layout = reducer.fit_transform(Xmat)
            layout = to_numpy_layout(layout)
            method_label = "PCA"
    
        else:
            from sklearn.decomposition import PCA

            reducer = PCA(
                n_components=2,
                random_state=int(selected_seed),
            )
    
            layout = reducer.fit_transform(Xmat)
            method_label = "PCA"
        
    else:
        raise ValueError("Method not valid. Choose between: uMap, tsne, PCA.")
    
    save_model(reducer, output_model)
    
    id_cols = [c for c in PREFERRED_ID_COLS if c in df_data.columns]

    # Avoid conflict with original imaging coordinates.
    # The DR output uses X/Y as embedding coordinates.
    id_cols_no_xy = [c for c in id_cols if c not in {"X", "Y"}]

    df_out = (
        df_data
        .select(id_cols_no_xy)
        .with_columns([
            pl.lit(method_label).alias("dr_method"),
            pl.Series("X", layout[:, 0]),
            pl.Series("Y", layout[:, 1]),
        ])
    )
    
    print("Writing output")
    write_table(df_out, output_csv)

    print("Done")

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dimensionality Reduction.")
    parser.add_argument("--input.marker.list", required=True, help="Path to input csv/parquet where selected markers are saved.")
    parser.add_argument("--path.input.csv", required=True, help="Path to input csv/parquet where sampled data is stored.")
    parser.add_argument("--path.output.csv", required=True, help="Path to output csv/parquet where DR results will be stored.")
    parser.add_argument("--path.output.model", required=True, help="Path to output model where the DR model will be stored.")
    parser.add_argument("--dimensionality.reduction.method", required=True, help="One of PCA, tsne, uMap.")
    parser.add_argument("--selected.seed", type=int, default=1234, help="Selected seed for reproducibility. Default: 1234.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dimensionality_reduction(
        marker_list_csv=getattr(args, "input.marker.list"),
        input_csv=getattr(args, "path.input.csv"),
        output_csv=getattr(args, "path.output.csv"),
        output_model=getattr(args, "path.output.model"),
        dr_method=getattr(args, "dimensionality.reduction.method"),
        selected_seed=getattr(args, "selected.seed"),
    )


if __name__ == "__main__":
    main()
