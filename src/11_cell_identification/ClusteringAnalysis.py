#!/usr/bin/env python3

import argparse
import csv
import warnings
from pathlib import Path

import numpy as np
import polars as pl
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from scipy.cluster.hierarchy import linkage, leaves_list
from scipy.spatial.distance import pdist


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


def safe_filename(x: str) -> str:
    return (
        str(x)
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
        .replace(":", "_")
    )


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


def load_dr_tables(
    input_pca: str,
    input_tsne: str,
    input_umap: str,
) -> pl.DataFrame:
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

        dfs.append(df)

    if len(dfs) == 0:
        raise ValueError("No dimensionality-reduction files were provided.")

    return pl.concat(dfs, how="vertical_relaxed")


def load_cluster_tables(
    input_phenograph: str,
    input_kmeans: str,
    input_som: str,
) -> pl.DataFrame:
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
    """
    Load mapped full-data cluster tables produced by MapClusters.py.

    Expected columns:
        sample_id, OID, X, Y, cl_method, cluster_mapped
    """
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
                df = df.with_columns(
                    pl.col(col).cast(pl.Utf8).str.strip_chars().alias(col)
                )

        dfs.append(df)

    if len(dfs) == 0:
        return None

    return pl.concat(dfs, how="vertical_relaxed")


def annotate_mapped_clusters_for_visualization(
    df_mapped: pl.DataFrame,
    annotation_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Add partial/manual annotations to mapped clusters for visualization only.

    The mapped cluster is preserved as cluster_mapped.
    """
    ann = annotation_df.select(["cl_method", "cluster", "annotation"]).with_columns([
        pl.col("cl_method").cast(pl.Utf8).str.strip_chars().alias("cl_method"),
        pl.col("cluster").cast(pl.Utf8).str.strip_chars().alias("cluster"),
        pl.col("annotation").cast(pl.Utf8).str.strip_chars().alias("annotation"),
    ])

    df = (
        df_mapped
        .with_columns(pl.col("cluster_mapped").alias("cluster"))
        .join(ann, on=["cl_method", "cluster"], how="left")
        .with_columns([
            pl.coalesce(["annotation", "cluster_mapped"]).alias("cluster_label"),
            (
                pl.col("cluster_mapped")
                + pl.lit(" | ")
                + pl.coalesce(["annotation", pl.lit("unannotated")])
            ).alias("cluster_label_detailed"),
        ])
        .drop(["cluster", "annotation"])
    )

    return df


def downsample_for_plotting(
    pdf: pd.DataFrame,
    max_points: int,
    stratify_col: str = "cluster_label",
    seed: int = 1234,
) -> pd.DataFrame:
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


def make_spatial_cluster_scatter(
    plot_df: pd.DataFrame,
    cl_method: str,
    sample_id: str,
) -> go.Figure:
    hover_cols = [
        c for c in [
            "sample_id",
            "slide_id",
            "scene_id",
            "OID",
            "cluster_mapped",
            "cluster_reference",
            "cluster_second",
            "cluster_confidence",
            "cluster_margin",
            "cluster_prediction_status",
        ]
        if c in plot_df.columns
    ]

    fig = px.scatter(
        plot_df,
        x="X",
        y="Y",
        color="cluster_label",
        hover_data=hover_cols,
        render_mode="webgl",
        title=f"Spatial cluster map - {cl_method} | sample {sample_id}",
    )

    fig.update_traces(
        marker=dict(
            size=3,
            opacity=0.85,
        )
    )

    fig.update_layout(
        template="plotly_white",
        xaxis_title="X",
        yaxis_title="Y",
        legend_title_text="Cluster / annotation",
        showlegend=True,
        width=900,
        height=800,
    )

    # For image coordinates, origin is usually top-left.
    # Remove this line if your coordinates are Cartesian.
    fig.update_yaxes(autorange="reversed", scaleanchor="x", scaleratio=1)

    return fig


def plot_spatial_mapped_clusters(
    df_mapped_annotated: pl.DataFrame,
    output_folder: Path,
    max_points_per_plot: int = 200000,
    selected_seed: int = 1234,
) -> None:
    """
    Generate one spatial X/Y scatter plot per sample_id and clustering method.

    No global all-samples plot is generated.
    """
    print("Generating per-sample spatial cluster scatter plots")

    output_folder.mkdir(parents=True, exist_ok=True)

    if "X" not in df_mapped_annotated.columns or "Y" not in df_mapped_annotated.columns:
        warnings.warn(
            "Mapped cluster table does not contain X/Y coordinates. "
            "Spatial plots will be skipped.",
            RuntimeWarning,
        )
        return

    methods = (
        df_mapped_annotated
        .select("cl_method")
        .unique()
        .sort("cl_method")
        .to_series()
        .to_list()
    )

    for cl_method in methods:
        tmp_method = df_mapped_annotated.filter(pl.col("cl_method") == cl_method)

        if tmp_method.height == 0:
            continue

        sample_ids = (
            tmp_method
            .select("sample_id")
            .unique()
            .sort("sample_id")
            .to_series()
            .to_list()
        )

        for sample_id in sample_ids:
            tmp_sample = tmp_method.filter(pl.col("sample_id") == sample_id)

            if tmp_sample.height == 0:
                continue

            pdf_sample = tmp_sample.to_pandas()

            pdf_sample = downsample_for_plotting(
                pdf_sample,
                max_points=max_points_per_plot,
                stratify_col="cluster_label",
                seed=selected_seed,
            )

            fig_sample = make_spatial_cluster_scatter(
                plot_df=pdf_sample,
                cl_method=cl_method,
                sample_id=str(sample_id),
            )

            safe_id = safe_filename(sample_id)

            write_plotly_figure(
                fig_sample,
                output_folder / f"{cl_method}_spatial_{safe_id}.html",
            )


def load_or_create_annotation_dictionary(
    annotation_dictionary_path: str,
    df_clusters: pl.DataFrame,
    output_folder: Path,
) -> pl.DataFrame:
    print("Mapping annotation dictionary")

    output_dictionary = output_folder / "annotation_dictionary.csv"

    if is_included(annotation_dictionary_path):
        try:
            annotation_dictionary = read_table(annotation_dictionary_path)
        except Exception:
            warnings.warn(
                "Could not read annotation dictionary. A new one will be created.",
                RuntimeWarning,
            )
            annotation_dictionary = None
    else:
        annotation_dictionary = None

    if annotation_dictionary is None:
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

    return annotation_dictionary


def write_plotly_figure(fig, output_file: Path) -> None:
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    html_file = output_file.with_suffix(".html")
    json_file = output_file.with_suffix(".json")

    fig.write_html(html_file, include_plotlyjs="cdn")
    fig.write_json(json_file, pretty=True)

    print(f"Wrote: {html_file}")
    print(f"Wrote: {json_file}")


def get_hclust_row_order(matrix_df: pd.DataFrame) -> list[str]:
    """
    Hierarchical row ordering.

    matrix_df:
        rows = clusters
        columns = markers
    """
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
) -> go.Figure:
    """
    New full marker heatmap:
        rows = clusters ordered by hierarchical clustering
        columns = markers ordered by overall mean expression
        color = mean expression
    """
    mat = (
        df_summary
        .pivot(index="cluster", columns="marker", values="M")
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
                "Cluster=%{y}<br>"
                "Marker=%{x}<br>"
                "Mean=%{z:.3f}<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        template="plotly_white",
        title=f"Cluster mean expression heatmap - {cl_method}",
        xaxis_title="Marker",
        yaxis_title="Cluster",
        width=max(900, 55 * len(col_order)),
        height=max(500, 35 * len(row_order)),
        margin=dict(l=80, r=40, t=70, b=120),
        showlegend=False,
    )

    fig.update_xaxes(tickangle=90)
    fig.update_yaxes(autorange="reversed")

    return fig


def make_scrna_style_dotplot(
    df_summary: pd.DataFrame,
    cl_method: str,
) -> go.Figure:
    """
    scRNA-seq-style dotplot:
        x = marker
        y = cluster
        color = mean expression
        size = fraction above marker midpoint
    """
    mat = (
        df_summary
        .pivot(index="cluster", columns="marker", values="M")
        .fillna(0.0)
    )

    mat.index = mat.index.astype(str)
    mat.columns = mat.columns.astype(str)

    col_order = mat.mean(axis=0).sort_values(ascending=False).index.tolist()
    row_order = get_hclust_row_order(mat.loc[:, col_order])

    tmp = df_summary.copy()
    tmp["cluster"] = tmp["cluster"].astype(str)
    tmp["marker"] = tmp["marker"].astype(str)

    tmp["cluster"] = pd.Categorical(tmp["cluster"], categories=row_order, ordered=True)
    tmp["marker"] = pd.Categorical(tmp["marker"], categories=col_order, ordered=True)

    tmp = tmp.sort_values(["cluster", "marker"])

    fig = px.scatter(
        tmp,
        x="marker",
        y="cluster",
        size="FractionAboveMidpoint",
        color="M",
        color_continuous_scale="RdBu_r",
        color_continuous_midpoint=0,
        size_max=5,
        category_orders={
            "marker": col_order,
            "cluster": row_order[::-1],
        },
        hover_data={
            "marker": True,
            "cluster": True,
            "M": ":.3f",
            "FractionAboveMidpoint": ":.3f",
        },
        title=f"Cluster marker dotplot - {cl_method}",
    )

    fig.update_traces(
        marker=dict(
            line=dict(width=0.25, color="black"),
            sizemode="diameter",
        )
    )

    fig.update_layout(
        template="plotly_white",
        xaxis_title="Marker",
        yaxis_title="Cluster",
        width=max(900, 55 * len(col_order)),
        height=max(500, 35 * len(row_order)),
        margin=dict(l=80, r=40, t=70, b=120),
        coloraxis_colorbar=dict(title="Mean expression"),
        legend_title_text="Fraction above midpoint",
    )

    fig.update_xaxes(tickangle=90)

    return fig


def plot_dr_clusters(
    df_clusters_annotated: pl.DataFrame,
    df_dr: pl.DataFrame,
    output_folder: Path,
) -> None:
    print("Generating DR cluster plots")

    tmp_plot = (
        df_clusters_annotated
        .join(
            df_dr.select(REQUIRED_ID_COLS + ["dr_method", "X", "Y"]),
            on=REQUIRED_ID_COLS,
            how="inner",
        )
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

    for row in (
        tmp_plot
        .select(["dr_method", "cl_method"])
        .unique()
        .sort(["dr_method", "cl_method"])
        .iter_rows(named=True)
    ):
        dr_method = row["dr_method"]
        cl_method = row["cl_method"]

        plot_df = (
            tmp_plot
            .filter(
                (pl.col("dr_method") == dr_method)
                & (pl.col("cl_method") == cl_method)
            )
            .to_pandas()
        )

        centroid_df = (
            centroids
            .filter(
                (pl.col("dr_method") == dr_method)
                & (pl.col("cl_method") == cl_method)
            )
            .to_pandas()
        )

        fig = px.scatter(
            plot_df,
            x="X",
            y="Y",
            color="cluster",
            hover_data=[c for c in REQUIRED_ID_COLS if c in plot_df.columns],
            title=f"{dr_method} colored by {cl_method} annotation",
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

        fig.update_layout(
            template="plotly_white",
            legend_title_text="Cluster / annotation",
        )

        out_file = output_folder / f"dr_clusters_{dr_method}_{cl_method}.html"
        write_plotly_figure(fig, out_file)

    for dr_method in tmp_plot.select("dr_method").unique().to_series().to_list():
        plot_df = tmp_plot.filter(pl.col("dr_method") == dr_method).to_pandas()

        fig = px.scatter(
            plot_df,
            x="X",
            y="Y",
            color="cluster",
            facet_col="cl_method",
            hover_data=[c for c in REQUIRED_ID_COLS if c in plot_df.columns],
            title=f"{dr_method} colored by clustering method annotations",
            render_mode="webgl",
        )

        fig.update_layout(
            template="plotly_white",
            legend_title_text="Cluster / annotation",
        )

        out_file = output_folder / f"dr_clusters_{dr_method}_all_methods.html"
        write_plotly_figure(fig, out_file)


def plot_marker_expression(
    df_data: pl.DataFrame,
    df_dr: pl.DataFrame,
    marker_cols: list[str],
    output_folder: Path,
) -> None:
    print("Generating marker-expression DR plots")

    marker_df = df_data.select(REQUIRED_ID_COLS + marker_cols)

    for dr_method in df_dr.select("dr_method").unique().to_series().to_list():
        dr_df = df_dr.filter(pl.col("dr_method") == dr_method)

        joined = marker_df.join(
            dr_df.select(REQUIRED_ID_COLS + ["dr_method", "X", "Y"]),
            on=REQUIRED_ID_COLS,
            how="inner",
        )

        if joined.height == 0:
            warnings.warn(f"No rows available for marker plots for {dr_method}.", RuntimeWarning)
            continue

        long_df = (
            joined
            .unpivot(
                index=REQUIRED_ID_COLS + ["dr_method", "X", "Y"],
                on=marker_cols,
                variable_name="marker",
                value_name="value",
            )
            .to_pandas()
        )

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

        out_file = output_folder / f"clustering_{dr_method}_markers.html"
        write_plotly_figure(fig, out_file)


def write_cluster_percentages(
    df_clusters_annotated: pl.DataFrame,
    output_folder: Path,
) -> pl.DataFrame:
    print("Evaluating cluster percentages")

    percentages = (
        df_clusters_annotated
        .group_by(["cl_method", "cluster"])
        .len()
        .rename({"len": "NCells"})
        .with_columns(
            (
                100 * pl.col("NCells") / pl.col("NCells").sum().over("cl_method")
            ).alias("Percentage")
        )
        .sort(["cl_method", "cluster"])
    )

    out_file = output_folder / "cluster_percentages.csv"
    write_table(percentages, str(out_file))
    print(f"Wrote: {out_file}")

    return percentages


def compute_marker_long_with_clusters(
    df_data: pl.DataFrame,
    df_clusters_annotated: pl.DataFrame,
    marker_cols: list[str],
) -> pl.DataFrame:
    marker_long = (
        df_data
        .select(REQUIRED_ID_COLS + marker_cols)
        .unpivot(
            index=REQUIRED_ID_COLS,
            on=marker_cols,
            variable_name="marker",
            value_name="value",
        )
    )

    joined = marker_long.join(
        df_clusters_annotated.select(REQUIRED_ID_COLS + ["cl_method", "cluster"]),
        on=REQUIRED_ID_COLS,
        how="inner",
    )

    if joined.height == 0:
        raise ValueError("No rows available after joining markers and clusters.")

    return joined


def plot_marker_heatmaps(
    df_data: pl.DataFrame,
    df_clusters_annotated: pl.DataFrame,
    percentages: pl.DataFrame,
    marker_cols: list[str],
    output_folder: Path,
    top_n: int = 15,
) -> None:
    """
    Original-style top-marker heatmaps, but rows are now ordered by hierarchical clustering
    using the full cluster x marker mean-expression profile.
    """
    print("Generating original-style heatmaps with hierarchical row ordering")

    joined = compute_marker_long_with_clusters(
        df_data=df_data,
        df_clusters_annotated=df_clusters_annotated,
        marker_cols=marker_cols,
    )

    df_heatmap = (
        joined
        .group_by(["cl_method", "cluster", "marker"])
        .agg(pl.col("value").mean().alias("M"))
    )

    for cl_method in df_heatmap.select("cl_method").unique().to_series().to_list():
        tmp = df_heatmap.filter(pl.col("cl_method") == cl_method)

        # Full mean matrix used only for row ordering
        tmp_matrix_pdf = tmp.to_pandas()
        mean_mat = (
            tmp_matrix_pdf
            .pivot(index="cluster", columns="marker", values="M")
            .fillna(0.0)
        )
        mean_mat.index = mean_mat.index.astype(str)
        mean_mat.columns = mean_mat.columns.astype(str)

        marker_order_for_hclust = mean_mat.mean(axis=0).sort_values(ascending=False).index.tolist()
        cluster_order = get_hclust_row_order(mean_mat.loc[:, marker_order_for_hclust])

        tmp_top = (
            tmp
            .sort(["cluster", "M"], descending=[False, True])
            .with_columns(
                (pl.arange(0, pl.len()).over("cluster") + 1).alias("rank")
            )
            .filter(pl.col("rank") <= top_n)
            .with_columns(pl.col("rank").cast(pl.Utf8).alias("rank_label"))
        )

        tmp_pct = (
            percentages
            .filter(pl.col("cl_method") == cl_method)
            .select([
                pl.col("cl_method"),
                pl.col("cluster"),
                pl.lit("Percentage").alias("marker"),
                pl.lit(0.0).alias("M"),
                pl.lit(top_n + 1).alias("rank"),
                pl.lit("Percentage").alias("rank_label"),
                pl.col("Percentage").round(2).cast(pl.Utf8).alias("text"),
            ])
        )

        tmp_top = tmp_top.with_columns(
            pl.col("marker").cast(pl.Utf8).alias("text")
        )

        tmp_plot = pl.concat(
            [
                tmp_top.select(["cl_method", "cluster", "marker", "M", "rank", "rank_label", "text"]),
                tmp_pct.select(["cl_method", "cluster", "marker", "M", "rank", "rank_label", "text"]),
            ],
            how="vertical_relaxed",
        )

        pdf = tmp_plot.to_pandas()

        rank_order = [str(i) for i in range(1, top_n + 1)] + ["Percentage"]
        pdf["rank_label"] = pd.Categorical(
            pdf["rank_label"],
            categories=rank_order,
            ordered=True,
        )

        pdf["cluster"] = pdf["cluster"].astype(str)
        pdf["cluster"] = pd.Categorical(
            pdf["cluster"],
            categories=cluster_order,
            ordered=True,
        )

        pdf = pdf.sort_values(["cluster", "rank_label"])

        clusters = cluster_order
        ranks = rank_order

        z = []
        text = []

        for cluster in clusters:
            row_z = []
            row_text = []

            for rank in ranks:
                sub = pdf[(pdf["cluster"].astype(str) == cluster) & (pdf["rank_label"] == rank)]

                if sub.empty:
                    row_z.append(None)
                    row_text.append("")
                else:
                    row_z.append(float(sub["M"].iloc[0]))
                    row_text.append(str(sub["text"].iloc[0]))

            z.append(row_z)
            text.append(row_text)

        fig = go.Figure(
            data=go.Heatmap(
                z=z,
                x=ranks,
                y=clusters,
                text=text,
                texttemplate="%{text}",
                colorscale="RdBu_r",
                zmid=0,
                colorbar=dict(title="Mean"),
                hovertemplate=(
                    "Cluster=%{y}<br>"
                    "Rank=%{x}<br>"
                    "Value=%{z}<br>"
                    "Label=%{text}<extra></extra>"
                ),
            )
        )

        fig.update_layout(
            template="plotly_white",
            title=f"Top {top_n} expressed markers per cluster ({cl_method})",
            xaxis_title=None,
            yaxis_title=None,
            height=max(500, 35 * len(clusters)),
            width=max(900, 55 * len(ranks)),
            showlegend=False,
        )

        fig.update_yaxes(autorange="reversed")

        out_file = output_folder / f"{cl_method}_heatmap.html"
        write_plotly_figure(fig, out_file)


def plot_marker_heatmaps_new(
    df_data: pl.DataFrame,
    df_clusters_annotated: pl.DataFrame,
    marker_cols: list[str],
    output_folder: Path,
) -> None:
    """
    New heatmap folder:
      1. full cluster x marker mean-expression heatmap with hierarchical row ordering
      2. scRNA-seq-style dotplot:
            color = mean expression
            size = fraction of cells above marker midpoint
    """
    print("Generating new heatmaps and scRNA-seq-style dotplots")

    joined = compute_marker_long_with_clusters(
        df_data=df_data,
        df_clusters_annotated=df_clusters_annotated,
        marker_cols=marker_cols,
    )

    marker_ranges = (
        joined
        .group_by("marker")
        .agg([
            pl.col("value").min().alias("marker_min"),
            pl.col("value").max().alias("marker_max"),
        ])
        .with_columns(
            ((pl.col("marker_min") + pl.col("marker_max")) / 2.0).alias("marker_midpoint")
        )
        .select(["marker", "marker_midpoint"])
    )

    joined = (
        joined
        .join(marker_ranges, on="marker", how="left")
        .with_columns(
            (pl.col("value") > pl.col("marker_midpoint")).alias("is_above_midpoint")
        )
    )

    df_summary = (
        joined
        .group_by(["cl_method", "cluster", "marker"])
        .agg([
            pl.col("value").mean().alias("M"),
            pl.col("is_above_midpoint").mean().alias("FractionAboveMidpoint"),
            pl.len().alias("NCells"),
        ])
    )

    write_table(df_summary, str(output_folder / "cluster_marker_dotplot_summary.parquet"))
    write_table(df_summary, str(output_folder / "cluster_marker_dotplot_summary.csv"))

    for cl_method in df_summary.select("cl_method").unique().to_series().to_list():
        tmp = (
            df_summary
            .filter(pl.col("cl_method") == cl_method)
            .to_pandas()
        )

        tmp["cluster"] = tmp["cluster"].astype(str)
        tmp["marker"] = tmp["marker"].astype(str)

        fig_heatmap = make_hclust_mean_heatmap(
            df_summary=tmp[["cluster", "marker", "M"]].copy(),
            cl_method=cl_method,
        )

        write_plotly_figure(
            fig_heatmap,
            output_folder / f"{cl_method}_heatmap_hclust.html",
        )

        fig_dotplot = make_scrna_style_dotplot(
            df_summary=tmp[["cluster", "marker", "M", "FractionAboveMidpoint"]].copy(),
            cl_method=cl_method,
        )

        write_plotly_figure(
            fig_dotplot,
            output_folder / f"{cl_method}_dotplot.html",
        )


# marker_list = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/phenotypic_markers_n01_v01.csv'
# input_csv = "/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/df_data_sampled.parquet"
# input_pca = "/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/PCA.parquet"
# input_tsne = "/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/tsne.parquet"
# input_umap = "/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/uMap.parquet"
# input_phenograph = "/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/phenograph.parquet"
# input_kmeans = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/kmeans.parquet'
# input_som = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/som.parquet'
# annotation_dictionary = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/annotation_dictionary.csv'
# marker_plots = 1
# output_folder = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01'
# input_mapped_phenograph = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/cluster_mapping/phenograph_mapped_clusters.parquet'
# input_mapped_kmeans = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/cluster_mapping/kmeans_mapped_clusters.parquet'
# input_mapped_som = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/cluster_mapping/som_mapped_clusters.parquet'

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
) -> None:
    print(f"### list of markers: {marker_list} ###")
    print(f"### input csv/parquet: {input_csv} ###")
    print(f"### input pca: {input_pca} ###")
    print(f"### input tsne: {input_tsne} ###")
    print(f"### input umap: {input_umap} ###")
    print(f"### input phenograph: {input_phenograph} ###")
    print(f"### input kmeans: {input_kmeans} ###")
    print(f"### input som: {input_som} ###")
    print(f"### annotation dictionary: {annotation_dictionary} ###")
    print(f"### marker plots: {marker_plots} ###")
    print(f"### output folder: {output_folder} ###")
    print(f"### input mapped phenograph: {input_mapped_phenograph} ###")
    print(f"### input mapped kmeans: {input_mapped_kmeans} ###")
    print(f"### input mapped som: {input_mapped_som} ###")
    print(f"### generate spatial plots: {generate_spatial_plots} ###")
    print(f"### spatial max points per plot: {spatial_max_points_per_plot} ###")

    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    figures_dir = out_dir / "figures"
    dr_figures_dir = figures_dir / "dr_clusters"
    marker_figures_dir = figures_dir / "marker_expression"
    heatmap_figures_dir = figures_dir / "heatmaps"
    heatmap_new_figures_dir = figures_dir / "heatmaps_new"
    spatial_figures_dir = figures_dir / "spatial_clusters"
    
    dr_figures_dir.mkdir(parents=True, exist_ok=True)
    marker_figures_dir.mkdir(parents=True, exist_ok=True)
    heatmap_figures_dir.mkdir(parents=True, exist_ok=True)
    heatmap_new_figures_dir.mkdir(parents=True, exist_ok=True)
    spatial_figures_dir.mkdir(parents=True, exist_ok=True)

    print("Loading marker list")
    marker_ids = load_marker_list(marker_list)

    print("Loading sampled data")
    df_data = read_table(input_csv)
    validate_required_ids(df_data, "sampled data")
    df_data = clean_required_ids(df_data)

    marker_cols = resolve_marker_columns(marker_ids, df_data.columns)

    print(f"{len(marker_cols)} markers found in sampled data")

    df_data = df_data.with_columns([
        pl.col(c).cast(pl.Float32, strict=False).alias(c)
        for c in marker_cols
    ])

    n_bad_marker_values = (
        df_data
        .select(marker_cols)
        .null_count()
        .select(pl.sum_horizontal(pl.all()).alias("n_bad_marker_values"))
        .item()
    )

    if n_bad_marker_values > 0:
        raise ValueError(
            f"{n_bad_marker_values} marker values could not be converted to numeric."
        )

    print("Loading DR files")
    df_dr = load_dr_tables(input_pca, input_tsne, input_umap)

    print("Loading clustering files")
    df_clusters = load_cluster_tables(input_phenograph, input_kmeans, input_som)

    annotation_df = load_or_create_annotation_dictionary(
        annotation_dictionary,
        df_clusters,
        out_dir,
    )

    df_clusters_annotated = (
        df_clusters
        .join(
            annotation_df.select(["cl_method", "cluster", "annotation"]),
            on=["cl_method", "cluster"],
            how="left",
        )
        .with_columns(
            pl.coalesce(["annotation", "cluster"]).alias("cluster")
        )
        .drop("annotation")
    )

    if int(generate_spatial_plots) == 1:
        print("Loading mapped full-data cluster tables for spatial plots")

        df_mapped_clusters = load_mapped_cluster_tables(
            input_mapped_phenograph=input_mapped_phenograph,
            input_mapped_kmeans=input_mapped_kmeans,
            input_mapped_som=input_mapped_som,
        )

        if df_mapped_clusters is None:
            print("No mapped cluster tables provided. Spatial cluster plots skipped.")
        else:
            df_mapped_annotated = annotate_mapped_clusters_for_visualization(
                df_mapped=df_mapped_clusters,
                annotation_df=annotation_df,
            )

            plot_spatial_mapped_clusters(
                df_mapped_annotated=df_mapped_annotated,
                output_folder=spatial_figures_dir,
                max_points_per_plot=int(spatial_max_points_per_plot),
                selected_seed=int(selected_seed),
            )
    else:
        print("Spatial cluster plots skipped")

    plot_dr_clusters(
        df_clusters_annotated=df_clusters_annotated,
        df_dr=df_dr,
        output_folder=dr_figures_dir,
    )

    if int(marker_plots) == 1:
        plot_marker_expression(
            df_data=df_data,
            df_dr=df_dr,
            marker_cols=marker_cols,
            output_folder=marker_figures_dir,
        )
    else:
        print("Marker-expression plots skipped")

    percentages = write_cluster_percentages(
        df_clusters_annotated=df_clusters_annotated,
        output_folder=out_dir,
    )

    plot_marker_heatmaps(
        df_data=df_data,
        df_clusters_annotated=df_clusters_annotated,
        percentages=percentages,
        marker_cols=marker_cols,
        output_folder=heatmap_figures_dir,
        top_n=min(len(marker_cols), 15),
    )

    plot_marker_heatmaps_new(
        df_data=df_data,
        df_clusters_annotated=df_clusters_annotated,
        marker_cols=marker_cols,
        output_folder=heatmap_new_figures_dir,
    )

    print("Done")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clustering analysis and Plotly visualization.")

    parser.add_argument("--input.marker.list", required=True, help="Path to selected marker list.")
    parser.add_argument("--path.input.csv", required=True, help="Path to sampled data.")
    parser.add_argument("--path.input.pca", default="not included", help="Path to PCA output.")
    parser.add_argument("--path.input.tsne", default="not included", help="Path to tSNE output.")
    parser.add_argument("--path.input.umap", default="not included", help="Path to UMAP output.")
    parser.add_argument("--path.input.phenograph", default="not included", help="Path to phenograph clustering output.")
    parser.add_argument("--path.input.kmeans", default="not included", help="Path to kmeans clustering output.")
    parser.add_argument("--path.input.som", default="not included", help="Path to som clustering output.")
    parser.add_argument("--path.annotation.dictionary", default="not included", help="Path to annotation dictionary, or 'not included'.")
    parser.add_argument("--generate.marker.plots", type=int, default=1, choices=[0, 1], help="Generate marker-expression DR plots.")
    parser.add_argument("--path.output.folder", required=True, help="Output directory for html plots and annotation dictionary.")
    parser.add_argument("--path.input.mapped.phenograph", default="not included", help="Path to full-data mapped phenograph clusters from MapClusters.py.")
    parser.add_argument("--path.input.mapped.kmeans", default="not included", help="Path to full-data mapped kmeans clusters from MapClusters.py.")
    parser.add_argument("--path.input.mapped.som", default="not included", help="Path to full-data mapped som clusters from MapClusters.py.")
    parser.add_argument("--generate.spatial.plots", type=int, default=1, choices=[0, 1], help="Generate one spatial X/Y scatter plot per sample_id and clustering method.")
    parser.add_argument("--spatial.max.points.per.plot", type=int, default=200000, help="Maximum number of points per spatial Plotly scatter plot. Use <=0 to disable downsampling.")
    parser.add_argument("--selected.seed", type=int, default=1234, help="Seed used for spatial plot downsampling.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    clustering_analysis(
        marker_list=getattr(args, "input.marker.list"),
        input_csv=getattr(args, "path.input.csv"),
        input_pca=getattr(args, "path.input.pca"),
        input_tsne=getattr(args, "path.input.tsne"),
        input_umap=getattr(args, "path.input.umap"),
        input_phenograph=getattr(args, "path.input.phenograph"),
        input_kmeans=getattr(args, "path.input.kmeans"),
        input_som=getattr(args, "path.input.som"),
        annotation_dictionary=getattr(args, "path.annotation.dictionary"),
        marker_plots=getattr(args, "generate.marker.plots"),
        output_folder=getattr(args, "path.output.folder"),
        input_mapped_phenograph=getattr(args, "path.input.mapped.phenograph"),
        input_mapped_kmeans=getattr(args, "path.input.mapped.kmeans"),
        input_mapped_som=getattr(args, "path.input.mapped.som"),
        generate_spatial_plots=getattr(args, "generate.spatial.plots"),
        spatial_max_points_per_plot=getattr(args, "spatial.max.points.per.plot"),
        selected_seed=getattr(args, "selected.seed"),
    )


if __name__ == "__main__":
    main()
