#!/usr/bin/env python3

import argparse
import csv
import hashlib
import html
import json
import warnings
from pathlib import Path

import numpy as np
import polars as pl
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from scipy.cluster.hierarchy import linkage, leaves_list
from scipy.spatial.distance import pdist
from scipy.stats import hypergeom


REQUIRED_ID_COLS = ["sample_id", "OID"]
PREFERRED_ID_COLS = ["sample_id", "OID", "slide_id", "scene_id", "scan_region", "X", "Y", "s.area"]
WRITE_HTML_DEFAULT = 1


# =============================================================================
# I/O helpers
# =============================================================================

def sniff_separator(fp: Path) -> str:
    with open(fp, "r", newline="") as f:
        sample = f.read(4096)

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        return dialect.delimiter
    except csv.Error:
        return ";"


def is_included(path: str | None) -> bool:
    if path is None:
        return False

    path_s = str(path).strip()

    if path_s == "":
        return False

    if path_s.lower() in {"not included", "none", "null", "na"}:
        return False

    return True


def read_table(path: str) -> pl.DataFrame:
    path_obj = Path(path)
    path_l = str(path).lower()

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


def write_table(df: pl.DataFrame | pd.DataFrame, path: str) -> None:
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(df, pd.DataFrame):
        df = pl.from_pandas(df)

    path_l = str(path).lower()

    if path_l.endswith(".parquet"):
        df.write_parquet(path)

    elif path_l.endswith(".csv"):
        # CSV cannot store list/nested columns. Convert list columns to readable strings.
        list_cols = [
            c for c, dtype in df.schema.items()
            if isinstance(dtype, pl.List)
        ]

        if list_cols:
            df = df.with_columns([
                pl.col(c)
                .list.eval(pl.element().cast(pl.Utf8))
                .list.join(";")
                .alias(c)
                for c in list_cols
            ])

        df.write_csv(path)

    else:
        raise ValueError("Output must end with .csv or .parquet")


def write_plotly_figure(fig, output_file: Path, write_json: int = 0, write_html: int | None = None) -> None:
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if write_html is None:
        write_html = WRITE_HTML_DEFAULT

    if int(write_html) == 1:
        html_file = output_file.with_suffix(".html")
        fig.write_html(html_file, include_plotlyjs="cdn")
        print(f"Wrote: {html_file}")

    if int(write_json) == 1:
        json_file = output_file.with_suffix(".json")
        fig.write_json(json_file, pretty=False)
        print(f"Wrote: {json_file}")

def write_json_file(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print(f"Wrote: {path}")


def safe_filename(x: str) -> str:
    return (
        str(x)
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
        .replace(":", "_")
    )


def file_sha1(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# =============================================================================
# General data helpers
# =============================================================================

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


def clean_required_ids(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns([
        pl.col(c).cast(pl.Utf8).str.strip_chars().alias(c)
        for c in REQUIRED_ID_COLS
    ])


def load_optional_table(path: str | None, label: str) -> pl.DataFrame | None:
    if not is_included(path):
        return None

    df = read_table(path)
    validate_required_ids(df, label)
    return clean_required_ids(df)


# =============================================================================
# Load pipeline outputs
# =============================================================================

def load_dr_tables(input_pca: str, input_tsne: str, input_umap: str) -> pl.DataFrame:
    dfs = []

    for path, label in [
        (input_pca, "PCA file"),
        (input_tsne, "tSNE file"),
        (input_umap, "UMAP file"),
    ]:
        df = load_optional_table(path, label)

        if df is None:
            continue

        required = {"dr_method", "X", "Y"}
        missing = required - set(df.columns)

        if missing:
            raise ValueError(f"{label} is missing columns: {sorted(missing)}")

        df = df.with_columns([
            pl.col("dr_method").cast(pl.Utf8).str.strip_chars().alias("dr_method"),
            pl.col("X").cast(pl.Float32, strict=False).alias("X"),
            pl.col("Y").cast(pl.Float32, strict=False).alias("Y"),
        ])

        dfs.append(df)

    if len(dfs) == 0:
        raise ValueError("No dimensionality-reduction files were provided.")

    return pl.concat(dfs, how="vertical_relaxed")


def load_cluster_tables(input_phenograph: str, input_kmeans: str, input_som: str) -> pl.DataFrame:
    dfs = []

    for path, label in [
        (input_phenograph, "phenograph file"),
        (input_kmeans, "kmeans file"),
        (input_som, "som file"),
    ]:
        df = load_optional_table(path, label)

        if df is None:
            continue

        required = {"cl_method", "cluster"}
        missing = required - set(df.columns)

        if missing:
            raise ValueError(f"{label} is missing columns: {sorted(missing)}")

        df = df.with_columns([
            pl.col("cl_method").cast(pl.Utf8).str.strip_chars().alias("cl_method"),
            pl.col("cluster").cast(pl.Utf8).str.strip_chars().alias("cluster"),
        ])

        dfs.append(df)

    if len(dfs) == 0:
        raise ValueError("No clustering files were provided.")

    return pl.concat(dfs, how="vertical_relaxed")


def load_mapped_cluster_tables(
    input_mapped_phenograph: str,
    input_mapped_kmeans: str,
    input_mapped_som: str,
) -> pl.DataFrame | None:
    """Load mapped full-data cluster tables produced by MapClusters.py."""
    dfs = []

    for path, label in [
        (input_mapped_phenograph, "mapped phenograph file"),
        (input_mapped_kmeans, "mapped kmeans file"),
        (input_mapped_som, "mapped som file"),
    ]:
        if not is_included(path):
            continue

        df = read_table(path)
        validate_required_ids(df, label)
        df = clean_required_ids(df)

        required = {"cl_method", "cluster_mapped", "X", "Y"}
        missing = required - set(df.columns)

        if missing:
            raise ValueError(f"{label} is missing columns: {sorted(missing)}")

        df = df.with_columns([
            pl.col("cl_method").cast(pl.Utf8).str.strip_chars().alias("cl_method"),
            pl.col("cluster_mapped").cast(pl.Utf8).str.strip_chars().alias("cluster_mapped"),
            pl.col("X").cast(pl.Float32, strict=False).alias("X"),
            pl.col("Y").cast(pl.Float32, strict=False).alias("Y"),
        ])

        optional_text_cols = [
            "cluster_reference",
            "cluster_second",
            "cluster_prediction_status",
            "slide_id",
            "scene_id",
            "scan_region",
        ]

        for col in optional_text_cols:
            if col in df.columns:
                df = df.with_columns(pl.col(col).cast(pl.Utf8).str.strip_chars().alias(col))

        dfs.append(df)

    if len(dfs) == 0:
        return None

    return pl.concat(dfs, how="vertical_relaxed")


# =============================================================================
# Annotation dictionary
# =============================================================================

def load_or_create_annotation_dictionary(
    annotation_dictionary_path: str,
    df_clusters: pl.DataFrame,
    output_folder: Path,
) -> pl.DataFrame:
    print("Loading or creating annotation dictionary")

    output_dictionary = output_folder / "annotation_dictionary.csv"

    if is_included(annotation_dictionary_path) and Path(annotation_dictionary_path).exists():
        annotation_dictionary = read_table(annotation_dictionary_path)
    elif output_dictionary.exists():
        annotation_dictionary = read_table(str(output_dictionary))
    else:
        annotation_dictionary = (
            df_clusters
            .select(["cl_method", "cluster"])
            .unique()
            .sort(["cl_method", "cluster"])
            .with_columns(pl.col("cluster").alias("annotation"))
        )
        write_table(annotation_dictionary, str(output_dictionary))
        print(f"Created annotation dictionary: {output_dictionary}")

    required = {"cl_method", "cluster", "annotation"}
    missing = required - set(annotation_dictionary.columns)

    if missing:
        raise ValueError(
            "Annotation dictionary must contain columns: cl_method, cluster, annotation. "
            f"Missing: {sorted(missing)}"
        )

    annotation_dictionary = annotation_dictionary.with_columns([
        pl.col("cl_method").cast(pl.Utf8).str.strip_chars().alias("cl_method"),
        pl.col("cluster").cast(pl.Utf8).str.strip_chars().alias("cluster"),
        pl.col("annotation").cast(pl.Utf8).str.strip_chars().alias("annotation"),
    ])

    # Fill missing/empty annotations with raw cluster labels.
    annotation_dictionary = annotation_dictionary.with_columns(
        pl.when(
            pl.col("annotation").is_null()
            | (pl.col("annotation").str.strip_chars() == "")
        )
        .then(pl.col("cluster"))
        .otherwise(pl.col("annotation"))
        .alias("annotation")
    )

    # Keep a copy in output folder for the frontend/editing loop.
    write_table(annotation_dictionary, str(output_dictionary))

    return annotation_dictionary


def write_annotation_state(annotation_df: pl.DataFrame, output_folder: Path) -> None:
    records = annotation_df.sort(["cl_method", "cluster"]).to_dicts()

    state = {
        "clusters": records,
        "mapping": {
            f"{r['cl_method']}|{r['cluster']}": r["annotation"]
            for r in records
        },
    }

    write_json_file(state, output_folder / "annotation_state.json")


# =============================================================================
# Hierarchical ordering and figure helpers
# =============================================================================

def get_hclust_row_order(matrix_df: pd.DataFrame) -> list[str]:
    matrix_df = matrix_df.copy()
    matrix_df.index = matrix_df.index.astype(str)

    if matrix_df.shape[0] <= 2:
        return matrix_df.index.tolist()

    values = matrix_df.values.astype(float)

    if np.allclose(values, values[0, :], equal_nan=True):
        return matrix_df.index.tolist()

    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    dist = pdist(values, metric="euclidean")

    if np.allclose(dist, 0):
        return matrix_df.index.tolist()

    z = linkage(dist, method="average")
    order = leaves_list(z)

    return matrix_df.index[order].tolist()


def make_hclust_mean_heatmap(
    df_summary: pd.DataFrame,
    cl_method: str,
    label_col: str,
    title_prefix: str,
) -> go.Figure:
    mat = (
        df_summary
        .pivot(index=label_col, columns="marker", values="M")
        .fillna(0.0)
    )

    mat.index = mat.index.astype(str)
    mat.columns = mat.columns.astype(str)

    col_order = mat.mean(axis=0).sort_values(ascending=False).index.tolist()
    row_order = get_hclust_row_order(mat.loc[:, col_order])
    mat = mat.loc[row_order, col_order]

    fig = go.Figure(
        data=go.Heatmap(
            z=mat.values,
            x=mat.columns.tolist(),
            y=mat.index.tolist(),
            colorscale="RdBu_r",
            zmid=0,
            colorbar=dict(title="Mean expression"),
            hovertemplate=(
                f"{label_col}=%{{y}}<br>"
                "Marker=%{x}<br>"
                "Mean=%{z:.3f}<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        template="plotly_white",
        title=f"{title_prefix} - {cl_method}",
        xaxis_title="Marker",
        yaxis_title=label_col,
        width=max(900, 55 * len(col_order)),
        height=max(500, 35 * len(row_order)),
        margin=dict(l=100, r=40, t=70, b=120),
        showlegend=False,
    )

    fig.update_xaxes(tickangle=90)
    fig.update_yaxes(autorange="reversed")

    return fig


def make_scrna_style_dotplot(
    df_summary: pd.DataFrame,
    cl_method: str,
    label_col: str,
    title_prefix: str,
) -> go.Figure:
    mat = (
        df_summary
        .pivot(index=label_col, columns="marker", values="M")
        .fillna(0.0)
    )

    mat.index = mat.index.astype(str)
    mat.columns = mat.columns.astype(str)

    col_order = mat.mean(axis=0).sort_values(ascending=False).index.tolist()
    row_order = get_hclust_row_order(mat.loc[:, col_order])

    tmp = df_summary.copy()
    tmp[label_col] = tmp[label_col].astype(str)
    tmp["marker"] = tmp["marker"].astype(str)
    tmp[label_col] = pd.Categorical(tmp[label_col], categories=row_order, ordered=True)
    tmp["marker"] = pd.Categorical(tmp["marker"], categories=col_order, ordered=True)
    tmp = tmp.sort_values([label_col, "marker"])

    fig = px.scatter(
        tmp,
        x="marker",
        y=label_col,
        size="FractionAboveMidpoint",
        color="M",
        color_continuous_scale="RdBu_r",
        color_continuous_midpoint=0,
        size_max=5,
        category_orders={
            "marker": col_order,
            label_col: row_order[::-1],
        },
        hover_data={
            "marker": True,
            label_col: True,
            "M": ":.3f",
            "FractionAboveMidpoint": ":.3f",
            "NCells": True if "NCells" in tmp.columns else False,
        },
        title=f"{title_prefix} - {cl_method}",
    )

    fig.update_traces(marker=dict(line=dict(width=0.25, color="black"), sizemode="diameter"))

    fig.update_layout(
        template="plotly_white",
        xaxis_title="Marker",
        yaxis_title=label_col,
        width=max(900, 55 * len(col_order)),
        height=max(500, 35 * len(row_order)),
        margin=dict(l=100, r=40, t=70, b=120),
        coloraxis_colorbar=dict(title="Mean expression"),
        legend_title_text="Fraction above midpoint",
    )

    fig.update_xaxes(tickangle=90)

    return fig


# =============================================================================
# Static plots
# =============================================================================

def plot_dr_sample_id(df_dr: pl.DataFrame, output_folder: Path, write_json: int = 0) -> None:
    print("Generating DR plots colored by sample_id")
    output_folder.mkdir(parents=True, exist_ok=True)

    for dr_method in df_dr.select("dr_method").unique().sort("dr_method").to_series().to_list():
        plot_df = df_dr.filter(pl.col("dr_method") == dr_method).to_pandas()

        fig = px.scatter(
            plot_df,
            x="X",
            y="Y",
            color="sample_id",
            hover_data=[c for c in REQUIRED_ID_COLS if c in plot_df.columns],
            title=f"{dr_method} colored by sample_id",
            render_mode="webgl",
        )

        fig.update_traces(marker=dict(size=3, opacity=0.8))
        fig.update_layout(template="plotly_white", legend_title_text="sample_id")

        write_plotly_figure(fig, output_folder / f"dr_sample_id_{dr_method}.html", write_json=write_json)


def plot_dr_clusters_raw(df_clusters: pl.DataFrame, df_dr: pl.DataFrame, output_folder: Path, write_json: int = 0) -> None:
    print("Generating DR plots colored by raw cluster")
    output_folder.mkdir(parents=True, exist_ok=True)

    tmp_plot = df_clusters.join(
        df_dr.select(REQUIRED_ID_COLS + ["dr_method", "X", "Y"]),
        on=REQUIRED_ID_COLS,
        how="inner",
    )

    if tmp_plot.height == 0:
        warnings.warn("No rows available after joining clusters and DR outputs.", RuntimeWarning)
        return

    centroids = (
        tmp_plot
        .group_by(["cl_method", "dr_method", "cluster"])
        .agg([
            pl.col("X").median().alias("X"),
            pl.col("Y").median().alias("Y"),
        ])
    )

    for row in tmp_plot.select(["dr_method", "cl_method"]).unique().sort(["dr_method", "cl_method"]).iter_rows(named=True):
        dr_method = row["dr_method"]
        cl_method = row["cl_method"]

        plot_df = tmp_plot.filter(
            (pl.col("dr_method") == dr_method) & (pl.col("cl_method") == cl_method)
        ).to_pandas()

        centroid_df = centroids.filter(
            (pl.col("dr_method") == dr_method) & (pl.col("cl_method") == cl_method)
        ).to_pandas()

        fig = px.scatter(
            plot_df,
            x="X",
            y="Y",
            color="cluster",
            hover_data=[c for c in REQUIRED_ID_COLS + ["cl_method", "cluster"] if c in plot_df.columns],
            title=f"{dr_method} colored by raw {cl_method} clusters",
            render_mode="webgl",
        )

        for _, c_row in centroid_df.iterrows():
            fig.add_annotation(
                x=c_row["X"],
                y=c_row["Y"],
                text=str(c_row["cluster"]),
                showarrow=False,
                bgcolor="rgba(255,255,255,0.75)",
                bordercolor="black",
                borderwidth=1,
                font=dict(size=10),
            )

        fig.update_layout(template="plotly_white", legend_title_text="Raw cluster")
        write_plotly_figure(fig, output_folder / f"dr_clusters_raw_{dr_method}_{cl_method}.html", write_json=write_json)


def plot_marker_expression(df_data: pl.DataFrame, df_dr: pl.DataFrame, marker_cols: list[str], output_folder: Path, write_json: int = 0) -> None:
    print("Generating marker-expression DR plots")
    output_folder.mkdir(parents=True, exist_ok=True)

    marker_df = df_data.select(REQUIRED_ID_COLS + marker_cols)

    for dr_method in df_dr.select("dr_method").unique().sort("dr_method").to_series().to_list():
        dr_df = df_dr.filter(pl.col("dr_method") == dr_method)

        joined = marker_df.join(
            dr_df.select(REQUIRED_ID_COLS + ["dr_method", "X", "Y"]),
            on=REQUIRED_ID_COLS,
            how="inner",
        )

        if joined.height == 0:
            warnings.warn(f"No rows available for marker plots for {dr_method}.", RuntimeWarning)
            continue

        long_df = joined.unpivot(
            index=REQUIRED_ID_COLS + ["dr_method", "X", "Y"],
            on=marker_cols,
            variable_name="marker",
            value_name="value",
        ).to_pandas()

        fig = px.scatter(
            long_df,
            x="X",
            y="Y",
            color="value",
            facet_col="marker",
            facet_col_wrap=4,
            color_continuous_scale="RdBu_r",
            color_continuous_midpoint=0,
            hover_data=[c for c in REQUIRED_ID_COLS if c in long_df.columns],
            title=f"{dr_method} marker expression",
            render_mode="webgl",
        )

        fig.update_traces(marker=dict(size=3, opacity=0.8))
        fig.update_layout(template="plotly_white")

        write_plotly_figure(fig, output_folder / f"marker_expression_{dr_method}.html", write_json=write_json)


def downsample_for_plotting(pdf: pd.DataFrame, max_points: int, stratify_col: str = "cluster", seed: int = 1234) -> pd.DataFrame:
    if max_points is None or max_points <= 0:
        return pdf

    if len(pdf) <= max_points:
        return pdf

    if stratify_col not in pdf.columns:
        return pdf.sample(n=max_points, random_state=seed)

    parts = []
    counts = pdf[stratify_col].value_counts(dropna=False)
    total = counts.sum()

    for label, n in counts.items():
        k = int(round(max_points * (n / total)))
        k = max(k, 1)
        k = min(k, n)
        tmp = pdf[pdf[stratify_col] == label]
        parts.append(tmp.sample(n=k, random_state=seed))

    out = pd.concat(parts, axis=0)

    if len(out) > max_points:
        out = out.sample(n=max_points, random_state=seed)

    return out


def plot_spatial_mapped_clusters_raw(
    df_mapped: pl.DataFrame,
    output_folder: Path,
    max_points_per_plot: int = 200000,
    selected_seed: int = 1234,
    write_json: int = 0,
) -> None:
    print("Generating raw per-sample spatial cluster scatter plots")
    output_folder.mkdir(parents=True, exist_ok=True)

    if "X" not in df_mapped.columns or "Y" not in df_mapped.columns:
        warnings.warn("Mapped cluster table does not contain X/Y coordinates. Spatial plots skipped.", RuntimeWarning)
        return

    df_mapped = df_mapped.with_columns(pl.col("cluster_mapped").alias("cluster"))

    methods = df_mapped.select("cl_method").unique().sort("cl_method").to_series().to_list()

    for cl_method in methods:
        tmp_method = df_mapped.filter(pl.col("cl_method") == cl_method)
        sample_ids = tmp_method.select("sample_id").unique().sort("sample_id").to_series().to_list()

        for sample_id in sample_ids:
            tmp_sample = tmp_method.filter(pl.col("sample_id") == sample_id)
            pdf_sample = tmp_sample.to_pandas()
            pdf_sample = downsample_for_plotting(
                pdf_sample,
                max_points=max_points_per_plot,
                stratify_col="cluster",
                seed=selected_seed,
            )

            hover_cols = [
                c for c in [
                    "sample_id", "slide_id", "scene_id", "OID", "cluster_mapped",
                    "cluster_second", "cluster_confidence", "cluster_margin",
                    "cluster_prediction_status",
                ]
                if c in pdf_sample.columns
            ]

            fig = px.scatter(
                pdf_sample,
                x="X",
                y="Y",
                color="cluster",
                hover_data=hover_cols,
                render_mode="webgl",
                title=f"Spatial raw cluster map - {cl_method} | sample {sample_id}",
            )

            fig.update_traces(marker=dict(size=3, opacity=0.85))
            fig.update_layout(
                template="plotly_white",
                xaxis_title="X",
                yaxis_title="Y",
                legend_title_text="Raw cluster",
                width=900,
                height=800,
            )
            fig.update_yaxes(autorange="reversed", scaleanchor="x", scaleratio=1)

            safe_id = safe_filename(sample_id)
            write_plotly_figure(fig, output_folder / f"{cl_method}_spatial_raw_{safe_id}.html", write_json=write_json)


# =============================================================================
# Cluster marker summaries and heatmaps
# =============================================================================

def compute_marker_long_with_clusters(df_data: pl.DataFrame, df_clusters: pl.DataFrame, marker_cols: list[str]) -> pl.DataFrame:
    marker_long = df_data.select(REQUIRED_ID_COLS + marker_cols).unpivot(
        index=REQUIRED_ID_COLS,
        on=marker_cols,
        variable_name="marker",
        value_name="value",
    )

    joined = marker_long.join(
        df_clusters.select(REQUIRED_ID_COLS + ["cl_method", "cluster"]),
        on=REQUIRED_ID_COLS,
        how="inner",
    )

    if joined.height == 0:
        raise ValueError("No rows available after joining markers and clusters.")

    return joined


def compute_cluster_marker_summary(df_data: pl.DataFrame, df_clusters: pl.DataFrame, marker_cols: list[str]) -> pl.DataFrame:
    print("Computing cluster-marker summary cache")

    joined = compute_marker_long_with_clusters(df_data=df_data, df_clusters=df_clusters, marker_cols=marker_cols)

    marker_ranges = joined.group_by("marker").agg([
        pl.col("value").min().alias("marker_min"),
        pl.col("value").max().alias("marker_max"),
    ]).with_columns(
        ((pl.col("marker_min") + pl.col("marker_max")) / 2.0).alias("marker_midpoint")
    ).select(["marker", "marker_midpoint"])

    joined = joined.join(marker_ranges, on="marker", how="left").with_columns(
        (pl.col("value") > pl.col("marker_midpoint")).alias("is_above_midpoint")
    )

    return joined.group_by(["cl_method", "cluster", "marker"]).agg([
        pl.col("value").mean().alias("M"),
        pl.col("is_above_midpoint").mean().alias("FractionAboveMidpoint"),
        pl.len().alias("NCells"),
    ]).sort(["cl_method", "cluster", "marker"])


def write_cluster_level_heatmaps(df_summary: pl.DataFrame, output_folder: Path, write_json: int = 0) -> None:
    print("Writing cluster-level heatmaps/dotplots")
    output_folder.mkdir(parents=True, exist_ok=True)

    for cl_method in df_summary.select("cl_method").unique().sort("cl_method").to_series().to_list():
        tmp = df_summary.filter(pl.col("cl_method") == cl_method).to_pandas()
        tmp["cluster"] = tmp["cluster"].astype(str)
        tmp["marker"] = tmp["marker"].astype(str)

        fig_heatmap = make_hclust_mean_heatmap(
            df_summary=tmp[["cluster", "marker", "M"]].copy(),
            cl_method=cl_method,
            label_col="cluster",
            title_prefix="Raw cluster mean expression heatmap",
        )
        write_plotly_figure(fig_heatmap, output_folder / f"{cl_method}_cluster_heatmap_hclust.html", write_json=write_json)

        fig_dotplot = make_scrna_style_dotplot(
            df_summary=tmp[["cluster", "marker", "M", "FractionAboveMidpoint", "NCells"]].copy(),
            cl_method=cl_method,
            label_col="cluster",
            title_prefix="Raw cluster marker dotplot",
        )
        write_plotly_figure(fig_dotplot, output_folder / f"{cl_method}_cluster_dotplot.html", write_json=write_json)


def write_cluster_percentages(df_clusters: pl.DataFrame, output_folder: Path) -> pl.DataFrame:
    print("Computing raw cluster percentages")

    percentages = df_clusters.group_by(["cl_method", "cluster"]).len().rename({"len": "NCells"}).with_columns(
        (100 * pl.col("NCells") / pl.col("NCells").sum().over("cl_method")).alias("Percentage")
    ).sort(["cl_method", "cluster"])

    write_table(percentages, str(output_folder / "cluster_percentages.parquet"))
    write_table(percentages, str(output_folder / "cluster_percentages.csv"))

    return percentages



# =============================================================================
# Annotation-dependent DR plots
# =============================================================================

def cache_dr_cluster_points(df_dr: pl.DataFrame, df_clusters: pl.DataFrame, cache_dir: Path) -> None:
    """
    Cache sampled DR coordinates with raw cluster labels.

    This allows update mode to regenerate annotation-colored DR plots without
    re-reading the original sampled data or clustering files.
    """
    print("Caching DR-cluster points for annotation updates")

    dr_cluster_points = df_clusters.join(
        df_dr.select(REQUIRED_ID_COLS + ["dr_method", "X", "Y"]),
        on=REQUIRED_ID_COLS,
        how="inner",
    )

    if dr_cluster_points.height == 0:
        warnings.warn(
            "No rows available after joining DR and cluster outputs. "
            "Annotation-level DR cache will be empty.",
            RuntimeWarning,
        )
        return

    write_table(dr_cluster_points, str(cache_dir / "dr_cluster_points.parquet"))


def plot_dr_clusters_annotation_from_cache(
    dr_cluster_points: pl.DataFrame,
    annotation_df: pl.DataFrame,
    output_folder: Path,
    write_json: int = 0,
) -> None:
    """
    Regenerate DR plots colored by current annotation labels.

    This is annotation-dependent but relatively small because it uses the cached
    sampled DR/cluster table rather than rebuilding everything from raw data.
    """
    print("Writing annotation-level DR plots")
    output_folder.mkdir(parents=True, exist_ok=True)

    ann = annotation_df.select(["cl_method", "cluster", "annotation"]).with_columns([
        pl.col("cl_method").cast(pl.Utf8).str.strip_chars().alias("cl_method"),
        pl.col("cluster").cast(pl.Utf8).str.strip_chars().alias("cluster"),
        pl.col("annotation").cast(pl.Utf8).str.strip_chars().alias("annotation"),
    ])

    plot_base = (
        dr_cluster_points
        .with_columns([
            pl.col("cl_method").cast(pl.Utf8).str.strip_chars().alias("cl_method"),
            pl.col("cluster").cast(pl.Utf8).str.strip_chars().alias("cluster"),
        ])
        .join(ann, on=["cl_method", "cluster"], how="left")
        .with_columns([
            pl.coalesce(["annotation", "cluster"]).alias("annotation"),
            (
                pl.coalesce(["annotation", "cluster"])
                + pl.lit(" | cluster ")
                + pl.col("cluster")
            ).alias("annotation_detailed"),
        ])
    )

    for row in (
        plot_base
        .select(["dr_method", "cl_method"])
        .unique()
        .sort(["dr_method", "cl_method"])
        .iter_rows(named=True)
    ):
        dr_method = row["dr_method"]
        cl_method = row["cl_method"]

        plot_df = (
            plot_base
            .filter(
                (pl.col("dr_method") == dr_method)
                & (pl.col("cl_method") == cl_method)
            )
            .to_pandas()
        )

        if plot_df.empty:
            continue

        hover_cols = [
            c for c in [
                "sample_id", "OID", "cl_method", "cluster", "annotation",
                "annotation_detailed"
            ]
            if c in plot_df.columns
        ]

        fig = px.scatter(
            plot_df,
            x="X",
            y="Y",
            color="annotation",
            hover_data=hover_cols,
            title=f"{dr_method} colored by {cl_method} annotation",
            render_mode="webgl",
        )

        fig.update_traces(marker=dict(size=3, opacity=0.8))
        fig.update_layout(template="plotly_white", legend_title_text="Annotation")

        out_file = output_folder / f"dr_annotation_{dr_method}_{cl_method}.html"
        write_plotly_figure(fig, out_file, write_json=write_json)


# =============================================================================
# Cluster/sample counts and enrichment statistics
# =============================================================================

def build_cluster_sample_counts(df_clusters: pl.DataFrame, df_mapped_clusters: pl.DataFrame | None) -> pl.DataFrame:
    if df_mapped_clusters is not None:
        print("Computing cluster-sample counts from mapped full-data clusters")
        df = df_mapped_clusters.with_columns(pl.col("cluster_mapped").alias("cluster"))

        agg_exprs = [pl.len().alias("Ncells")]
        if "cluster_confidence" in df.columns:
            agg_exprs.append(pl.col("cluster_confidence").cast(pl.Float64, strict=False).mean().alias("mean_cluster_confidence"))
        if "cluster_prediction_status" in df.columns:
            agg_exprs.append((pl.col("cluster_prediction_status") == "high_confidence").mean().alias("fraction_high_confidence"))

        out = df.group_by(["sample_id", "cl_method", "cluster"]).agg(agg_exprs).with_columns(
            pl.lit("mapped_full_data").alias("source")
        )
    else:
        print("Computing cluster-sample counts from sampled clustering tables")
        out = df_clusters.group_by(["sample_id", "cl_method", "cluster"]).len().rename({"len": "Ncells"}).with_columns([
            pl.lit(None).cast(pl.Float64).alias("mean_cluster_confidence"),
            pl.lit(None).cast(pl.Float64).alias("fraction_high_confidence"),
            pl.lit("sampled_data").alias("source"),
        ])

    return out.sort(["cl_method", "sample_id", "cluster"])


def bh_adjust(p_values: np.ndarray) -> np.ndarray:
    p = np.asarray(p_values, dtype=float)
    n = p.shape[0]
    out = np.ones(n, dtype=float)

    if n == 0:
        return out

    p_clean = np.nan_to_num(p, nan=1.0, posinf=1.0, neginf=1.0)
    order = np.argsort(p_clean)
    ranked = p_clean[order]
    adj = ranked * n / np.arange(1, n + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    out[order] = np.minimum(adj, 1.0)
    return out


def compute_enrichment_from_counts(counts: pl.DataFrame, label_col: str, output_label_col: str) -> pl.DataFrame:
    """
    Compute one-sided hypergeometric enrichment for every sample x label inside each method.

    Output columns include:
        sample_id, clustering_method, <label>, Ncells,
        percentage_wrt_<label>, percentage_wrt_sample,
        p_value, p_adj_BH, enrichment_ratio, log2_enrichment, enrichment_score.
    """
    if counts.height == 0:
        return pl.DataFrame()

    pdf = counts.to_pandas()
    pdf["sample_id"] = pdf["sample_id"].astype(str)
    pdf["cl_method"] = pdf["cl_method"].astype(str)
    pdf[label_col] = pdf[label_col].astype(str)
    pdf["Ncells"] = pd.to_numeric(pdf["Ncells"], errors="coerce").fillna(0).astype(int)

    all_results = []

    for method, mdf in pdf.groupby("cl_method", sort=True):
        samples = sorted(mdf["sample_id"].unique().tolist())
        labels = sorted(mdf[label_col].unique().tolist())

        grid = pd.MultiIndex.from_product(
            [[method], samples, labels],
            names=["cl_method", "sample_id", label_col],
        ).to_frame(index=False)

        base_cols = ["cl_method", "sample_id", label_col, "Ncells"]
        optional_cols = [c for c in ["mean_cluster_confidence", "fraction_high_confidence", "source"] if c in mdf.columns]

        tmp = grid.merge(mdf[base_cols + optional_cols], on=["cl_method", "sample_id", label_col], how="left")
        tmp["Ncells"] = tmp["Ncells"].fillna(0).astype(int)

        N_total = int(tmp["Ncells"].sum())
        sample_totals = tmp.groupby("sample_id")["Ncells"].sum().rename("N_sample")
        label_totals = tmp.groupby(label_col)["Ncells"].sum().rename("N_label")

        tmp = tmp.merge(sample_totals, on="sample_id", how="left")
        tmp = tmp.merge(label_totals, on=label_col, how="left")
        tmp["N_total_method"] = N_total

        tmp["expected_Ncells"] = (tmp["N_sample"] * tmp["N_label"]) / max(N_total, 1)

        pvals = []
        for _, r in tmp.iterrows():
            a = int(r["Ncells"])
            K = int(r["N_label"])
            n = int(r["N_sample"])
            N = int(r["N_total_method"])

            if a <= 0 or K <= 0 or n <= 0 or N <= 0:
                pvals.append(1.0)
            else:
                pvals.append(float(hypergeom.sf(a - 1, N, K, n)))

        tmp["p_value"] = pvals
        tmp["p_adj_BH"] = bh_adjust(tmp["p_value"].values)

        tmp[f"percentage_wrt_{output_label_col}"] = np.where(
            tmp["N_label"] > 0,
            100 * tmp["Ncells"] / tmp["N_label"],
            0.0,
        )
        tmp["percentage_wrt_sample"] = np.where(
            tmp["N_sample"] > 0,
            100 * tmp["Ncells"] / tmp["N_sample"],
            0.0,
        )
        tmp["enrichment_ratio"] = np.where(
            tmp["expected_Ncells"] > 0,
            tmp["Ncells"] / tmp["expected_Ncells"],
            np.nan,
        )
        tmp["log2_enrichment"] = np.log2((tmp["Ncells"] + 0.5) / (tmp["expected_Ncells"] + 0.5))
        tmp["enrichment_score"] = -np.log10(np.maximum(tmp["p_adj_BH"], 1e-300)) * np.maximum(tmp["log2_enrichment"], 0)
        tmp["clustering_method"] = tmp["cl_method"]

        all_results.append(tmp)

    out = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()
    out = out.rename(columns={label_col: output_label_col})

    preferred = [
        "sample_id",
        "clustering_method",
        output_label_col,
        "Ncells",
        "N_sample",
        f"percentage_wrt_{output_label_col}",
        "percentage_wrt_sample",
        "N_label",
        "N_total_method",
        "expected_Ncells",
        "enrichment_ratio",
        "log2_enrichment",
        "p_value",
        "p_adj_BH",
        "enrichment_score",
        "mean_cluster_confidence",
        "fraction_high_confidence",
        "source",
    ]

    cols = [c for c in preferred if c in out.columns] + [c for c in out.columns if c not in preferred + ["cl_method"]]
    out = out[cols]

    out = out.sort_values(
        ["clustering_method", "enrichment_score", "p_adj_BH", "Ncells"],
        ascending=[True, False, True, False],
    )

    return pl.from_pandas(out)


def write_datatable_html(df: pl.DataFrame, output_file: Path, title: str, max_rows: int = 50000) -> None:
    """
    Write a searchable/filterable DataTables HTML.

    Numeric values are rounded for display only. The parquet/csv files written
    next to the HTML remain the complete source tables.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)
    pdf = df.head(max_rows).to_pandas()

    table_id = "datatable"

    string_cols = {
        "sample_id",
        "clustering_method",
        "cluster",
        "annotation",
        "source",
        "clusters_merged",
    }
    int_cols = {
        "Ncells",
        "N_sample",
        "N_label",
        "N_total_method",
    }
    p_cols = {
        "p_value",
        "p_adj_BH",
    }

    def is_sequence_value(v):
        return isinstance(v, (list, tuple, set, np.ndarray))

    def sequence_to_string(v):
        if isinstance(v, np.ndarray):
            v = v.tolist()
        if isinstance(v, set):
            v = sorted(v)
        return ";".join(str(x) for x in v)

    def display_value(col, v):
        # List/array columns, e.g. clusters_merged, must be handled before pd.isna().
        if is_sequence_value(v):
            return sequence_to_string(v)

        try:
            if pd.isna(v):
                return ""
        except Exception:
            return str(v)

        if col in string_cols:
            return str(v)

        try:
            x = float(v)
        except Exception:
            return str(v)

        if col in int_cols:
            return f"{int(round(x)):,}"

        if col.startswith("percentage_wrt"):
            return f"{x:.2f}"

        if col in p_cols:
            if x == 0:
                return "<1e-300"
            if abs(x) < 1e-4:
                return f"{x:.2e}"
            return f"{x:.4g}"

        if col in {"expected_Ncells"}:
            return f"{x:.1f}"

        if col in {"enrichment_ratio", "log2_enrichment", "enrichment_score"}:
            return f"{x:.3f}"

        if col in {"mean_cluster_confidence", "fraction_high_confidence"}:
            return f"{x:.3f}"

        if isinstance(v, (int, np.integer)):
            return f"{int(v):,}"

        return f"{x:.3f}"

    def sort_value(col, v):
        if is_sequence_value(v):
            return sequence_to_string(v)

        try:
            if pd.isna(v):
                return ""
        except Exception:
            return str(v)

        if col in string_cols:
            return str(v)

        try:
            return f"{float(v):.12g}"
        except Exception:
            return str(v)

    header_html = "".join(
        f"<th>{html.escape(str(c))}</th>"
        for c in pdf.columns
    )

    filter_html = "".join(
        (
            f"<th><input type='text' placeholder='Filter {html.escape(str(c))}' "
            f"style='width: 95%; font-size: 11px; box-sizing: border-box;' /></th>"
        )
        for c in pdf.columns
    )

    body_rows = []
    cols = list(pdf.columns)

    for row in pdf.itertuples(index=False, name=None):
        cells = []
        for col, v in zip(cols, row):
            disp = display_value(col, v)
            sortv = sort_value(col, v)
            cells.append(
                f"<td data-order='{html.escape(str(sortv))}'>{html.escape(str(disp))}</td>"
            )
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    body_html = "\n".join(body_rows)

    page = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="https://cdn.datatables.net/1.13.8/css/jquery.dataTables.min.css">
<style>
body {{
  font-family: Arial, sans-serif;
  margin: 24px;
}}
p {{
  max-width: 1400px;
}}
table.dataTable tbody td {{
  white-space: nowrap;
  font-size: 12px;
}}
table.dataTable thead th {{
  white-space: nowrap;
  font-size: 12px;
}}
thead input {{
  width: 100%;
}}
.dataTables_wrapper .dataTables_filter {{
  float: left;
  text-align: left;
  margin-bottom: 8px;
}}
.dataTables_scrollBody {{
  border-bottom: 1px solid #aaa;
}}
.top-scroll {{
  overflow-x: auto;
  overflow-y: hidden;
  height: 16px;
  margin-top: 8px;
  margin-bottom: 4px;
}}
.top-scroll div {{
  height: 1px;
}}
</style>
</head>
<body>
<h2>{html.escape(title)}</h2>
<p>
Rows shown in this interactive table: {len(pdf):,}.
Displayed numeric values are rounded for readability. The complete, full-precision
table is saved next to this file as CSV/parquet. Use the boxes under each column
name to filter specific fields, and the global search box for broad filtering.
A horizontal scrollbar is available at the top and bottom of the table.
</p>

<table id="{table_id}" class="display compact" style="width:100%">
<thead>
<tr>{header_html}</tr>
<tr>{filter_html}</tr>
</thead>
<tbody>
{body_html}
</tbody>
</table>

<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.datatables.net/1.13.8/js/jquery.dataTables.min.js"></script>
<script>
$(document).ready(function() {{
  var table = $('#{table_id}').DataTable({{
    pageLength: 50,
    scrollX: true,
    scrollY: '70vh',
    scrollCollapse: true,
    deferRender: true,
    orderCellsTop: true,
    fixedHeader: false,
    order: []
  }});

  table.columns().eq(0).each(function (colIdx) {{
    $('input', table.column(colIdx).header().parentNode.nextElementSibling.cells[colIdx])
      .on('keyup change clear', function () {{
        if (table.column(colIdx).search() !== this.value) {{
          table.column(colIdx).search(this.value).draw();
        }}
      }});
  }});

  var container = $(table.table().container());
  var scrollBody = container.find('.dataTables_scrollBody');
  var topScroll = $('<div class="top-scroll"><div></div></div>');

  topScroll.insertBefore(scrollBody);
  topScroll.find('div').width(scrollBody.get(0).scrollWidth);

  topScroll.on('scroll', function() {{
    scrollBody.scrollLeft($(this).scrollLeft());
  }});

  scrollBody.on('scroll', function() {{
    topScroll.scrollLeft($(this).scrollLeft());
  }});

  setTimeout(function() {{
    topScroll.find('div').width(scrollBody.get(0).scrollWidth);
  }}, 500);
}});
</script>
</body>
</html>
"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(page)

    print(f"Wrote: {output_file}")

def make_enrichment_heatmap(enrichment_df: pl.DataFrame, cl_method: str, label_col: str, title_prefix: str) -> go.Figure:
    pdf = enrichment_df.filter(pl.col("clustering_method") == cl_method).to_pandas()

    if pdf.empty:
        return go.Figure()

    pdf[label_col] = pdf[label_col].astype(str)
    pdf["sample_id"] = pdf["sample_id"].astype(str)

    mat = pdf.pivot(index="sample_id", columns=label_col, values="log2_enrichment").fillna(0.0)
    mat.index = mat.index.astype(str)
    mat.columns = mat.columns.astype(str)

    # Order samples and labels by hierarchical clustering where possible.
    col_order = mat.mean(axis=0).sort_values(ascending=False).index.tolist()
    row_order = get_hclust_row_order(mat.loc[:, col_order]) if mat.shape[0] > 1 else mat.index.tolist()
    mat = mat.loc[row_order, col_order]

    fig = go.Figure(data=go.Heatmap(
        z=mat.values,
        x=mat.columns.tolist(),
        y=mat.index.tolist(),
        colorscale="RdBu_r",
        zmid=0,
        colorbar=dict(title="log2 enrichment"),
        hovertemplate=(
            "Sample=%{y}<br>"
            f"{label_col}=%{{x}}<br>"
            "log2 enrichment=%{z:.3f}<extra></extra>"
        ),
    ))

    fig.update_layout(
        template="plotly_white",
        title=f"{title_prefix} - {cl_method}",
        xaxis_title=label_col,
        yaxis_title="sample_id",
        width=max(900, 45 * len(col_order)),
        height=max(500, 28 * len(row_order)),
        margin=dict(l=120, r=40, t=70, b=120),
        showlegend=False,
    )
    fig.update_xaxes(tickangle=90)
    fig.update_yaxes(autorange="reversed")

    return fig


def write_enrichment_outputs(
    enrichment_df: pl.DataFrame,
    output_folder: Path,
    label_col: str,
    file_prefix: str,
    title_prefix: str,
    write_json: int = 0,
) -> None:
    """
    Write enrichment outputs.

    Keep this intentionally table-only:
      - parquet: full machine-readable table
      - csv: full human-readable table
      - html: DataTables view with global search and per-column filters

    Heatmaps/barplots are deliberately not generated here because the table
    scales better with many samples and many clusters/annotations.
    """
    output_folder.mkdir(parents=True, exist_ok=True)

    write_table(enrichment_df, str(output_folder / f"{file_prefix}.parquet"))
    write_table(enrichment_df, str(output_folder / f"{file_prefix}.csv"))
    write_datatable_html(
        enrichment_df,
        output_folder / f"{file_prefix}_datatable.html",
        title=title_prefix,
    )


# =============================================================================
# Annotation-dependent summaries
# =============================================================================

def build_annotation_marker_summary(cluster_marker_summary: pl.DataFrame, annotation_df: pl.DataFrame) -> pl.DataFrame:
    print("Computing annotation-level marker summary from cache")

    ann = annotation_df.select(["cl_method", "cluster", "annotation"]).with_columns([
        pl.col("cl_method").cast(pl.Utf8).str.strip_chars().alias("cl_method"),
        pl.col("cluster").cast(pl.Utf8).str.strip_chars().alias("cluster"),
        pl.col("annotation").cast(pl.Utf8).str.strip_chars().alias("annotation"),
    ])

    df = cluster_marker_summary.join(ann, on=["cl_method", "cluster"], how="left").with_columns(
        pl.coalesce(["annotation", "cluster"]).alias("annotation")
    )

    out = df.with_columns([
        (pl.col("M") * pl.col("NCells")).alias("M_weight"),
        (pl.col("FractionAboveMidpoint") * pl.col("NCells")).alias("F_weight"),
    ]).group_by(["cl_method", "annotation", "marker"]).agg([
        (pl.col("M_weight").sum() / pl.col("NCells").sum()).alias("M"),
        (pl.col("F_weight").sum() / pl.col("NCells").sum()).alias("FractionAboveMidpoint"),
        pl.col("NCells").sum().alias("NCells"),
        pl.col("cluster").unique().sort().alias("clusters_merged"),
    ]).sort(["cl_method", "annotation", "marker"])

    return out


def write_annotation_level_heatmaps(annotation_summary: pl.DataFrame, output_folder: Path, write_json: int = 0) -> None:
    print("Writing annotation-level heatmaps/dotplots")
    output_folder.mkdir(parents=True, exist_ok=True)

    for cl_method in annotation_summary.select("cl_method").unique().sort("cl_method").to_series().to_list():
        tmp = annotation_summary.filter(pl.col("cl_method") == cl_method).to_pandas()
        tmp["annotation"] = tmp["annotation"].astype(str)
        tmp["marker"] = tmp["marker"].astype(str)

        fig_heatmap = make_hclust_mean_heatmap(
            df_summary=tmp[["annotation", "marker", "M"]].copy(),
            cl_method=cl_method,
            label_col="annotation",
            title_prefix="Annotation-level mean expression heatmap",
        )
        write_plotly_figure(fig_heatmap, output_folder / f"{cl_method}_annotation_heatmap_hclust.html", write_json=write_json)

        fig_dotplot = make_scrna_style_dotplot(
            df_summary=tmp[["annotation", "marker", "M", "FractionAboveMidpoint", "NCells"]].copy(),
            cl_method=cl_method,
            label_col="annotation",
            title_prefix="Annotation-level marker dotplot",
        )
        write_plotly_figure(fig_dotplot, output_folder / f"{cl_method}_annotation_dotplot.html", write_json=write_json)


def build_annotation_sample_counts(cluster_sample_counts: pl.DataFrame, annotation_df: pl.DataFrame) -> pl.DataFrame:
    print("Computing annotation-sample counts from cache")

    ann = annotation_df.select(["cl_method", "cluster", "annotation"]).with_columns([
        pl.col("cl_method").cast(pl.Utf8).str.strip_chars().alias("cl_method"),
        pl.col("cluster").cast(pl.Utf8).str.strip_chars().alias("cluster"),
        pl.col("annotation").cast(pl.Utf8).str.strip_chars().alias("annotation"),
    ])

    df = cluster_sample_counts.join(ann, on=["cl_method", "cluster"], how="left").with_columns(
        pl.coalesce(["annotation", "cluster"]).alias("annotation")
    )

    # Weighted confidence if the mapped-cluster cache contains confidence columns.
    extra_exprs = []
    if "mean_cluster_confidence" in df.columns:
        extra_exprs.append(
            (pl.col("mean_cluster_confidence") * pl.col("Ncells")).sum() / pl.col("Ncells").sum()
        .alias("mean_cluster_confidence"))
    if "fraction_high_confidence" in df.columns:
        extra_exprs.append(
            (pl.col("fraction_high_confidence") * pl.col("Ncells")).sum() / pl.col("Ncells").sum()
        .alias("fraction_high_confidence"))
    if "source" in df.columns:
        extra_exprs.append(pl.col("source").first().alias("source"))

    out = df.group_by(["sample_id", "cl_method", "annotation"]).agg([
        pl.col("Ncells").sum().alias("Ncells"),
        pl.col("cluster").unique().sort().alias("clusters_merged"),
        *extra_exprs,
    ]).sort(["cl_method", "sample_id", "annotation"])

    return out



# =============================================================================
# Annotation-dependent spatial plots
# =============================================================================

def plot_spatial_mapped_clusters_annotation_from_cache(
    df_mapped: pl.DataFrame,
    annotation_df: pl.DataFrame,
    output_folder: Path,
    max_points_per_plot: int = 200000,
    selected_seed: int = 1234,
    write_json: int = 0,
) -> None:
    """
    Regenerate spatial X/Y plots colored by current annotation labels.

    This uses cached full-data mapped cluster points created during build mode:
        analysis_cache/mapped_cluster_points.parquet

    Raw cluster IDs remain in hover data for traceability.
    """
    print("Writing annotation-level spatial cluster plots")
    output_folder.mkdir(parents=True, exist_ok=True)

    if "X" not in df_mapped.columns or "Y" not in df_mapped.columns:
        warnings.warn(
            "Mapped cluster cache does not contain X/Y coordinates. "
            "Annotation-level spatial plots skipped.",
            RuntimeWarning,
        )
        return

    ann = annotation_df.select(["cl_method", "cluster", "annotation"]).with_columns([
        pl.col("cl_method").cast(pl.Utf8).str.strip_chars().alias("cl_method"),
        pl.col("cluster").cast(pl.Utf8).str.strip_chars().alias("cluster"),
        pl.col("annotation").cast(pl.Utf8).str.strip_chars().alias("annotation"),
    ])

    df_plot = (
        df_mapped
        .with_columns([
            pl.col("cl_method").cast(pl.Utf8).str.strip_chars().alias("cl_method"),
            pl.col("cluster_mapped").cast(pl.Utf8).str.strip_chars().alias("cluster"),
        ])
        .join(ann, on=["cl_method", "cluster"], how="left")
        .with_columns([
            pl.coalesce(["annotation", "cluster"]).alias("annotation"),
            (
                pl.coalesce(["annotation", "cluster"])
                + pl.lit(" | cluster ")
                + pl.col("cluster")
            ).alias("annotation_detailed"),
        ])
    )

    methods = df_plot.select("cl_method").unique().sort("cl_method").to_series().to_list()

    for cl_method in methods:
        tmp_method = df_plot.filter(pl.col("cl_method") == cl_method)
        sample_ids = tmp_method.select("sample_id").unique().sort("sample_id").to_series().to_list()

        for sample_id in sample_ids:
            tmp_sample = tmp_method.filter(pl.col("sample_id") == sample_id)
            pdf_sample = tmp_sample.to_pandas()

            pdf_sample = downsample_for_plotting(
                pdf_sample,
                max_points=int(max_points_per_plot),
                stratify_col="annotation",
                seed=int(selected_seed),
            )

            hover_cols = [
                c for c in [
                    "sample_id", "slide_id", "scene_id", "OID",
                    "cluster_mapped", "cluster_second", "annotation",
                    "annotation_detailed", "cluster_confidence",
                    "cluster_margin", "cluster_prediction_status",
                ]
                if c in pdf_sample.columns
            ]

            fig = px.scatter(
                pdf_sample,
                x="X",
                y="Y",
                color="annotation",
                hover_data=hover_cols,
                render_mode="webgl",
                title=f"Spatial annotation map - {cl_method} | sample {sample_id}",
            )

            fig.update_traces(marker=dict(size=3, opacity=0.85))
            fig.update_layout(
                template="plotly_white",
                xaxis_title="X",
                yaxis_title="Y",
                legend_title_text="Annotation",
                width=900,
                height=800,
            )
            fig.update_yaxes(autorange="reversed", scaleanchor="x", scaleratio=1)

            safe_id = safe_filename(sample_id)
            out_file = output_folder / f"{cl_method}_spatial_annotation_{safe_id}.html"
            write_plotly_figure(fig, out_file, write_json=write_json)

# =============================================================================
# Main public functions
# =============================================================================

def clustering_analysis_build_static(
    marker_list: str,
    input_csv: str,
    input_pca: str,
    input_tsne: str,
    input_umap: str,
    input_phenograph: str,
    input_kmeans: str,
    input_som: str,
    output_folder: str,
    annotation_dictionary: str = "not included",
    marker_plots: int = 1,
    input_mapped_phenograph: str = "not included",
    input_mapped_kmeans: str = "not included",
    input_mapped_som: str = "not included",
    generate_spatial_plots: int = 1,
    spatial_max_points_per_plot: int = 200000,
    selected_seed: int = 1234,
    write_json: int = 0,
    write_html: int = 1,
) -> None:
    """
    Heavy/static step.

    Run this when sampled data, marker list, DR outputs, clustering outputs, or
    MapClusters outputs change. It intentionally keeps raw cluster IDs stable.
    Annotation-dependent merged summaries are generated by
    clustering_analysis_update_annotations().
    """
    global WRITE_HTML_DEFAULT
    WRITE_HTML_DEFAULT = int(write_html)

    print("### ClusteringAnalysis static build ###")
    print(f"### list of markers: {marker_list} ###")
    print(f"### input csv/parquet: {input_csv} ###")
    print(f"### output folder: {output_folder} ###")

    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    figures_dir = out_dir / "figures"
    cache_dir = out_dir / "analysis_cache"

    dr_sample_dir = figures_dir / "dr_sample_id"
    dr_cluster_dir = figures_dir / "dr_clusters_raw"
    marker_dir = figures_dir / "marker_expression"
    heatmap_cluster_dir = figures_dir / "heatmaps_cluster_level"
    spatial_raw_dir = figures_dir / "spatial_clusters_raw"
    enrichment_cluster_dir = figures_dir / "cluster_sample_enrichment"

    for d in [dr_sample_dir, dr_cluster_dir, marker_dir, heatmap_cluster_dir, spatial_raw_dir, enrichment_cluster_dir, cache_dir]:
        d.mkdir(parents=True, exist_ok=True)

    print("Loading marker list")
    marker_ids = load_marker_list(marker_list)

    print("Loading sampled data")
    df_data = read_table(input_csv)
    validate_required_ids(df_data, "sampled data")
    df_data = clean_required_ids(df_data)

    marker_cols = resolve_marker_columns(marker_ids, df_data.columns)
    print(f"{len(marker_cols)} markers found in sampled data")

    df_data = df_data.with_columns([pl.col(c).cast(pl.Float32, strict=False).alias(c) for c in marker_cols])

    n_bad_marker_values = df_data.select(marker_cols).null_count().select(pl.sum_horizontal(pl.all()).alias("n_bad_marker_values")).item()
    if n_bad_marker_values > 0:
        raise ValueError(f"{n_bad_marker_values} marker values could not be converted to numeric.")

    print("Loading DR files")
    df_dr = load_dr_tables(input_pca, input_tsne, input_umap)

    print("Loading clustering files")
    df_clusters = load_cluster_tables(input_phenograph, input_kmeans, input_som)

    # Make sure the annotation dictionary exists, but do not use it to rewrite raw plots.
    annotation_df = load_or_create_annotation_dictionary(annotation_dictionary, df_clusters, out_dir)
    write_annotation_state(annotation_df, out_dir)

    print("Writing static DR/sample and DR/raw-cluster plots")
    plot_dr_sample_id(df_dr=df_dr, output_folder=dr_sample_dir, write_json=write_json)
    plot_dr_clusters_raw(df_clusters=df_clusters, df_dr=df_dr, output_folder=dr_cluster_dir, write_json=write_json)
    cache_dr_cluster_points(df_dr=df_dr, df_clusters=df_clusters, cache_dir=cache_dir)

    if int(marker_plots) == 1:
        plot_marker_expression(df_data=df_data, df_dr=df_dr, marker_cols=marker_cols, output_folder=marker_dir, write_json=write_json)
    else:
        print("Marker-expression plots skipped")

    print("Computing and writing cluster-level summaries")
    cluster_marker_summary = compute_cluster_marker_summary(df_data=df_data, df_clusters=df_clusters, marker_cols=marker_cols)
    write_table(cluster_marker_summary, str(cache_dir / "cluster_marker_summary.parquet"))
    write_table(cluster_marker_summary, str(cache_dir / "cluster_marker_summary.csv"))
    write_cluster_level_heatmaps(cluster_marker_summary, output_folder=heatmap_cluster_dir, write_json=write_json)

    cluster_percentages = write_cluster_percentages(df_clusters, cache_dir)
    # Keep old expected location for compatibility.
    write_table(cluster_percentages, str(out_dir / "cluster_percentages.csv"))

    print("Loading mapped full-data cluster tables, if available")
    df_mapped_clusters = load_mapped_cluster_tables(
        input_mapped_phenograph=input_mapped_phenograph,
        input_mapped_kmeans=input_mapped_kmeans,
        input_mapped_som=input_mapped_som,
    )

    if df_mapped_clusters is not None:
        # Slim but sufficient cache for annotation-level spatial updates.
        mapped_cache_cols = [
            c for c in [
                "sample_id", "OID", "slide_id", "scene_id", "scan_region",
                "X", "Y", "s.area", "cl_method", "cluster_mapped",
                "cluster_second", "cluster_confidence", "cluster_margin",
                "cluster_prediction_status", "n_neighbors", "knn_backend",
            ]
            if c in df_mapped_clusters.columns
        ]
        write_table(
            df_mapped_clusters.select(mapped_cache_cols),
            str(cache_dir / "mapped_cluster_points.parquet"),
        )

    if int(generate_spatial_plots) == 1 and df_mapped_clusters is not None:
        plot_spatial_mapped_clusters_raw(
            df_mapped=df_mapped_clusters,
            output_folder=spatial_raw_dir,
            max_points_per_plot=int(spatial_max_points_per_plot),
            selected_seed=int(selected_seed),
            write_json=write_json,
        )
    elif int(generate_spatial_plots) == 1:
        print("No mapped cluster tables provided. Spatial raw cluster plots skipped.")
    else:
        print("Spatial raw cluster plots skipped")

    print("Computing cluster-sample count/enrichment cache")
    cluster_sample_counts = build_cluster_sample_counts(df_clusters=df_clusters, df_mapped_clusters=df_mapped_clusters)
    write_table(cluster_sample_counts, str(cache_dir / "cluster_sample_counts.parquet"))
    write_table(cluster_sample_counts, str(cache_dir / "cluster_sample_counts.csv"))

    cluster_enrichment = compute_enrichment_from_counts(cluster_sample_counts, label_col="cluster", output_label_col="cluster")
    write_table(cluster_enrichment, str(cache_dir / "raw_cluster_sample_enrichment.parquet"))
    write_table(cluster_enrichment, str(cache_dir / "raw_cluster_sample_enrichment.csv"))
    write_enrichment_outputs(
        enrichment_df=cluster_enrichment,
        output_folder=enrichment_cluster_dir,
        label_col="cluster",
        file_prefix="raw_cluster_sample_enrichment",
        title_prefix="Raw cluster-sample enrichment",
        write_json=write_json,
    )

    print("Static build done")


def clustering_analysis_update_annotations(
    output_folder: str,
    annotation_dictionary: str = "not included",
    update_heatmaps: int = 1,
    update_enrichment: int = 1,
    update_dr_plots: int = 1,
    update_spatial_plots: int = 0,
    spatial_max_points_per_plot: int = 200000,
    selected_seed: int = 1234,
    write_json: int = 0,
    write_html: int = 1,
) -> None:
    """
    Fast/update step.

    Run this when annotation_dictionary.csv changes. It reads cached cluster-level
    summaries and recomputes only outputs whose values change when clusters are
    merged into user annotations.
    """
    global WRITE_HTML_DEFAULT
    WRITE_HTML_DEFAULT = int(write_html)

    print("### ClusteringAnalysis annotation update ###")
    print(f"### output folder: {output_folder} ###")
    print(f"### annotation dictionary: {annotation_dictionary} ###")

    out_dir = Path(output_folder)
    cache_dir = out_dir / "analysis_cache"
    figures_dir = out_dir / "figures"

    annotation_heatmap_dir = figures_dir / "heatmaps_annotation_level"
    annotation_enrichment_dir = figures_dir / "sample_enrichment_annotation_level"

    for d in [annotation_heatmap_dir, annotation_enrichment_dir, cache_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Resolve dictionary path.
    if is_included(annotation_dictionary) and Path(annotation_dictionary).exists():
        annotation_path = Path(annotation_dictionary)
    else:
        annotation_path = out_dir / "annotation_dictionary.csv"

    if not annotation_path.exists():
        raise ValueError(f"Annotation dictionary not found: {annotation_path}")

    annotation_df = read_table(str(annotation_path)).with_columns([
        pl.col("cl_method").cast(pl.Utf8).str.strip_chars().alias("cl_method"),
        pl.col("cluster").cast(pl.Utf8).str.strip_chars().alias("cluster"),
        pl.col("annotation").cast(pl.Utf8).str.strip_chars().alias("annotation"),
    ])

    annotation_df = annotation_df.with_columns(
        pl.when(
            pl.col("annotation").is_null()
            | (pl.col("annotation").str.strip_chars() == "")
        )
        .then(pl.col("cluster"))
        .otherwise(pl.col("annotation"))
        .alias("annotation")
    )

    write_annotation_state(annotation_df, out_dir)
    write_table(annotation_df, str(out_dir / "annotation_dictionary.csv"))
    with open(cache_dir / "annotation_dictionary.sha1", "w", encoding="utf-8") as f:
        f.write(file_sha1(str(annotation_path)))

    update_summary_records = []

    if int(update_dr_plots) == 1:
        dr_cache_path = cache_dir / "dr_cluster_points.parquet"
        if dr_cache_path.exists():
            dr_cluster_points = read_table(str(dr_cache_path))
            plot_dr_clusters_annotation_from_cache(
                dr_cluster_points=dr_cluster_points,
                annotation_df=annotation_df,
                output_folder=figures_dir / "dr_clusters_annotation",
                write_json=write_json,
            )
            update_summary_records.append({"output": "dr_clusters_annotation", "status": "updated"})
        else:
            warnings.warn(
                f"Missing cache file: {dr_cache_path}. Annotation-level DR plots skipped. "
                "Run --mode build once with this updated script to create the cache.",
                RuntimeWarning,
            )
    else:
        print("Annotation-level DR plots skipped")

    if int(update_spatial_plots) == 1:
        mapped_cache_path = cache_dir / "mapped_cluster_points.parquet"
        if mapped_cache_path.exists():
            df_mapped_cache = read_table(str(mapped_cache_path))
            plot_spatial_mapped_clusters_annotation_from_cache(
                df_mapped=df_mapped_cache,
                annotation_df=annotation_df,
                output_folder=figures_dir / "spatial_clusters_annotation",
                max_points_per_plot=int(spatial_max_points_per_plot),
                selected_seed=int(selected_seed),
                write_json=write_json,
            )
            update_summary_records.append({"output": "spatial_clusters_annotation", "status": "updated"})
        else:
            warnings.warn(
                f"Missing cache file: {mapped_cache_path}. Annotation-level spatial plots skipped. "
                "Run --mode build once with this updated script to create the cache.",
                RuntimeWarning,
            )
    else:
        print("Annotation-level spatial plots skipped")

    if int(update_heatmaps) == 1:
        cluster_marker_path = cache_dir / "cluster_marker_summary.parquet"
        if not cluster_marker_path.exists():
            raise ValueError(
                f"Missing cache file: {cluster_marker_path}. Run --mode build first."
            )

        cluster_marker_summary = read_table(str(cluster_marker_path))
        annotation_marker_summary = build_annotation_marker_summary(cluster_marker_summary, annotation_df)

        write_table(annotation_marker_summary, str(cache_dir / "annotation_marker_summary.parquet"))
        write_table(annotation_marker_summary, str(cache_dir / "annotation_marker_summary.csv"))
        write_annotation_level_heatmaps(annotation_marker_summary, output_folder=annotation_heatmap_dir, write_json=write_json)

        update_summary_records.append({"output": "annotation_marker_summary", "status": "updated"})
    else:
        print("Annotation-level heatmaps/dotplots skipped")

    if int(update_enrichment) == 1:
        cluster_counts_path = cache_dir / "cluster_sample_counts.parquet"
        if not cluster_counts_path.exists():
            raise ValueError(
                f"Missing cache file: {cluster_counts_path}. Run --mode build first."
            )

        cluster_sample_counts = read_table(str(cluster_counts_path))
        annotation_sample_counts = build_annotation_sample_counts(cluster_sample_counts, annotation_df)
        write_table(annotation_sample_counts, str(cache_dir / "annotation_sample_counts.parquet"))
        write_table(annotation_sample_counts, str(cache_dir / "annotation_sample_counts.csv"))

        annotation_enrichment = compute_enrichment_from_counts(annotation_sample_counts, label_col="annotation", output_label_col="annotation")

        # Add clusters_merged to the final enrichment table for interpretability.
        clusters_merged = annotation_sample_counts.select(["cl_method", "annotation", "clusters_merged"]).unique().rename({"cl_method": "clustering_method"})
        annotation_enrichment = annotation_enrichment.join(clusters_merged, on=["clustering_method", "annotation"], how="left")

        write_table(annotation_enrichment, str(cache_dir / "annotation_sample_enrichment.parquet"))
        write_table(annotation_enrichment, str(cache_dir / "annotation_sample_enrichment.csv"))

        write_enrichment_outputs(
            enrichment_df=annotation_enrichment,
            output_folder=annotation_enrichment_dir,
            label_col="annotation",
            file_prefix="annotation_sample_enrichment",
            title_prefix="Annotation-sample enrichment",
            write_json=write_json,
        )

        update_summary_records.append({"output": "annotation_sample_enrichment", "status": "updated"})
    else:
        print("Annotation-level enrichment skipped")

    if update_summary_records:
        write_table(pl.DataFrame(update_summary_records), str(out_dir / "annotation_update_summary.csv"))

    print("Annotation update done")


def clustering_analysis(
    marker_list: str,
    input_csv: str,
    input_pca: str,
    input_tsne: str,
    input_umap: str,
    input_phenograph: str,
    input_kmeans: str,
    input_som: str,
    annotation_dictionary: str,
    marker_plots: int,
    output_folder: str,
    input_mapped_phenograph: str = "not included",
    input_mapped_kmeans: str = "not included",
    input_mapped_som: str = "not included",
    generate_spatial_plots: int = 1,
    spatial_max_points_per_plot: int = 200000,
    selected_seed: int = 1234,
    write_json: int = 0,
    write_html: int = 1,
) -> None:
    """Backward-compatible wrapper: build static outputs, then update annotation-dependent outputs."""
    clustering_analysis_build_static(
        marker_list=marker_list,
        input_csv=input_csv,
        input_pca=input_pca,
        input_tsne=input_tsne,
        input_umap=input_umap,
        input_phenograph=input_phenograph,
        input_kmeans=input_kmeans,
        input_som=input_som,
        output_folder=output_folder,
        annotation_dictionary=annotation_dictionary,
        marker_plots=marker_plots,
        input_mapped_phenograph=input_mapped_phenograph,
        input_mapped_kmeans=input_mapped_kmeans,
        input_mapped_som=input_mapped_som,
        generate_spatial_plots=generate_spatial_plots,
        spatial_max_points_per_plot=spatial_max_points_per_plot,
        selected_seed=selected_seed,
        write_json=write_json,
        write_html=write_html,
    )

    clustering_analysis_update_annotations(
        output_folder=output_folder,
        annotation_dictionary=annotation_dictionary,
        update_heatmaps=1,
        update_enrichment=1,
        update_dr_plots=1,
        update_spatial_plots=0,
        spatial_max_points_per_plot=spatial_max_points_per_plot,
        selected_seed=selected_seed,
        write_json=write_json,
        write_html=write_html,
    )


# =============================================================================
# CLI
# =============================================================================

def require_args(args, names: list[str], mode: str) -> None:
    missing = []
    for name in names:
        value = getattr(args, name)
        if value is None or str(value).strip() == "":
            missing.append("--" + name)
    if missing:
        raise ValueError(f"Mode '{mode}' requires arguments: " + ", ".join(missing))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Clustering analysis and annotation-dependent updates. "
            "Use --mode build for the heavy/static run, --mode update after annotation edits, "
            "or --mode full for both."
        )
    )

    parser.add_argument("--mode", default="full", choices=["build", "update", "full"], help="Run static build, annotation update, or both.")

    parser.add_argument("--input.marker.list", default=None, help="Path to selected marker list.")
    parser.add_argument("--path.input.csv", default=None, help="Path to sampled data.")
    parser.add_argument("--path.input.pca", default="not included", help="Path to PCA output.")
    parser.add_argument("--path.input.tsne", default="not included", help="Path to tSNE output.")
    parser.add_argument("--path.input.umap", default="not included", help="Path to UMAP output.")
    parser.add_argument("--path.input.phenograph", default="not included", help="Path to phenograph clustering output.")
    parser.add_argument("--path.input.kmeans", default="not included", help="Path to kmeans clustering output.")
    parser.add_argument("--path.input.som", default="not included", help="Path to som clustering output.")
    parser.add_argument("--path.annotation.dictionary", default="not included", help="Path to annotation dictionary, or 'not included'.")
    parser.add_argument("--generate.marker.plots", type=int, default=1, choices=[0, 1], help="Generate marker-expression DR plots in build mode.")
    parser.add_argument("--path.output.folder", required=True, help="Output directory.")
    parser.add_argument("--path.input.mapped.phenograph", default="not included", help="Path to full-data mapped phenograph clusters from MapClusters.py.")
    parser.add_argument("--path.input.mapped.kmeans", default="not included", help="Path to full-data mapped kmeans clusters from MapClusters.py.")
    parser.add_argument("--path.input.mapped.som", default="not included", help="Path to full-data mapped som clusters from MapClusters.py.")
    parser.add_argument("--generate.spatial.plots", type=int, default=1, choices=[0, 1], help="Generate one spatial X/Y scatter plot per sample_id and clustering method in build mode.")
    parser.add_argument("--spatial.max.points.per.plot", type=int, default=200000, help="Maximum points per spatial Plotly scatter. Use <=0 to disable downsampling.")
    parser.add_argument("--selected.seed", type=int, default=1234, help="Seed used for spatial plot downsampling.")
    parser.add_argument("--update.heatmaps", type=int, default=1, choices=[0, 1], help="Update annotation-level heatmaps/dotplots in update mode.")
    parser.add_argument("--update.enrichment", type=int, default=1, choices=[0, 1], help="Update annotation-level enrichment outputs in update mode.")
    parser.add_argument("--update.dr.plots", type=int, default=1, choices=[0, 1], help="Update annotation-colored DR plots from cached DR-cluster points in update mode.")
    parser.add_argument("--update.spatial.plots", type=int, default=0, choices=[0, 1], help="Update annotation-colored spatial plots from cached MapClusters outputs in update mode. Default: 0 because these plots can be heavy.")
    parser.add_argument("--write.json", type=int, default=1, choices=[0, 1], help="Write Plotly JSON files for frontend consumption. Default: 1.")
    parser.add_argument("--write.html", type=int, default=0, choices=[0, 1], help="Also write standalone Plotly HTML files for manual browser inspection. Default: 0.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    mode = getattr(args, "mode")

    build_required = [
        "input.marker.list",
        "path.input.csv",
    ]

    if mode in {"build", "full"}:
        require_args(args, build_required, mode)

        clustering_analysis_build_static(
            marker_list=getattr(args, "input.marker.list"),
            input_csv=getattr(args, "path.input.csv"),
            input_pca=getattr(args, "path.input.pca"),
            input_tsne=getattr(args, "path.input.tsne"),
            input_umap=getattr(args, "path.input.umap"),
            input_phenograph=getattr(args, "path.input.phenograph"),
            input_kmeans=getattr(args, "path.input.kmeans"),
            input_som=getattr(args, "path.input.som"),
            output_folder=getattr(args, "path.output.folder"),
            annotation_dictionary=getattr(args, "path.annotation.dictionary"),
            marker_plots=getattr(args, "generate.marker.plots"),
            input_mapped_phenograph=getattr(args, "path.input.mapped.phenograph"),
            input_mapped_kmeans=getattr(args, "path.input.mapped.kmeans"),
            input_mapped_som=getattr(args, "path.input.mapped.som"),
            generate_spatial_plots=getattr(args, "generate.spatial.plots"),
            spatial_max_points_per_plot=getattr(args, "spatial.max.points.per.plot"),
            selected_seed=getattr(args, "selected.seed"),
            write_json=getattr(args, "write.json"),
            write_html=getattr(args, "write.html"),
        )

    if mode in {"update", "full"}:
        clustering_analysis_update_annotations(
            output_folder=getattr(args, "path.output.folder"),
            annotation_dictionary=getattr(args, "path.annotation.dictionary"),
            update_heatmaps=getattr(args, "update.heatmaps"),
            update_enrichment=getattr(args, "update.enrichment"),
            update_dr_plots=getattr(args, "update.dr.plots"),
            update_spatial_plots=getattr(args, "update.spatial.plots"),
            spatial_max_points_per_plot=getattr(args, "spatial.max.points.per.plot"),
            selected_seed=getattr(args, "selected.seed"),
            write_json=getattr(args, "write.json"),
            write_html=getattr(args, "write.html"),
        )


if __name__ == "__main__":
    main()
