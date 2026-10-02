#!/usr/bin/env python3
"""
ClusterDensityPlot.py
=====================

On-demand flow-cytometry-style 2D density plot for a single marker pair and a
single cluster -- or a whole cell type spanning several clusters.

Given the sampled data and a clustering result, this builds a biaxial
(marker A vs marker B) plot where:

  * the SELECTED population is drawn as a 2D histogram coloured by density
    (the highlighted population), and
  * the REST of the cells are drawn faintly in the background, so you can see
    where that population sits inside the global distribution.

The highlighted population is either:

  * a single cluster (``--cluster 7``), or
  * a cell type (``--annotation Tcells``), in which case the annotation
    dictionary (cl_method, cluster, annotation) is used to combine *every*
    cluster mapped to that cell type for the chosen method. This closes the
    gap noted for PreComputePairWiseDensity (where annotating clusters 3, 7,
    12 all as "Tcells" gave you no single "Tcells" density plot).

This is the focused, interactive sibling of ``PreComputePairWiseDensity.py``:
that script precomputes every top-marker pair for every cluster, whereas this
one renders exactly one pair / one population on demand, which is what an
interactive UI needs.

It returns a Plotly figure and writes both ``.html`` (self-contained, plotly
from CDN) and ``.json`` (Plotly figure JSON) so it can be embedded in an
interactive application, matching the I/O conventions used elsewhere in the
pipeline (see ``ClusteringAnalysis.write_plotly_figure``).

The clustering method can be given in two equivalent ways:

  1. point straight at a clustering file:
       --path.input.cluster .../phenograph.parquet
  2. give a folder + method name and let the script resolve the file:
       --path.cluster.folder .../v01  --clustering.method phenograph
     (loads ``<folder>/<method>.parquet``)

Example
-------
python ClusterDensityPlot.py \\
    --path.input.csv      .../n01/df_data_sampled.parquet \\
    --path.cluster.folder .../n01/v01 \\
    --clustering.method   phenograph \\
    --marker.a            CD3 \\
    --marker.b            CD8 \\
    --cluster             7 \\
    --path.output.file    .../n01/v01/density/phenograph_cluster7_CD3_CD8
"""

import argparse
import csv
import warnings
from pathlib import Path

import numpy as np
import polars as pl

import plotly.graph_objects as go


# Join keys shared across the pipeline (see Clustering.py / PreComputePairWiseDensity.py)
REQUIRED_ID_COLS = ["sample_id", "OID"]

# Methods recognised when resolving <folder>/<method>.parquet
KNOWN_METHODS = ["phenograph", "kmeans", "som"]


# --------------------------------------------------------------------------- #
# I/O helpers (kept consistent with the rest of the pipeline)
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Marker-name resolution (same rules as Clustering.py / PreComputePairWiseDensity.py)
# --------------------------------------------------------------------------- #
def normalize_name(s: str) -> str:
    return str(s).replace("-", ".").upper()


def build_norm_lookup(data_columns: list[str]) -> dict[str, str]:
    normalized_to_real: dict[str, str] = {}
    for col in data_columns:
        norm = normalize_name(col)
        if norm in normalized_to_real:
            raise ValueError(
                f"Ambiguous normalized column name '{norm}' maps to both "
                f"'{normalized_to_real[norm]}' and '{col}'."
            )
        normalized_to_real[norm] = col
    return normalized_to_real


def resolve_one_marker(marker: str, lookup: dict[str, str]) -> str:
    norm = normalize_name(marker)
    if norm not in lookup:
        available = ", ".join(sorted(lookup.values()))
        raise ValueError(
            f"Marker '{marker}' was not found in the input data.\n"
            f"Available columns: {available}"
        )
    return lookup[norm]


# --------------------------------------------------------------------------- #
# Clustering-file resolution
# --------------------------------------------------------------------------- #
def resolve_cluster_path(
    cluster_file: str | None,
    cluster_folder: str | None,
    method: str | None,
) -> str:
    """Either a direct file is given, or <folder>/<method>.parquet is built."""
    if cluster_file:
        return cluster_file

    if cluster_folder and method:
        candidate = Path(cluster_folder) / f"{method}.parquet"
        if not candidate.exists():
            alt = Path(cluster_folder) / f"{method}.csv"
            if alt.exists():
                return str(alt)
            raise ValueError(
                f"Could not find clustering file for method '{method}' in "
                f"{cluster_folder} (looked for {candidate.name} / {alt.name})."
            )
        return str(candidate)

    raise ValueError(
        "Provide either --path.input.cluster, or both --path.cluster.folder "
        "and --clustering.method."
    )


# --------------------------------------------------------------------------- #
# Annotation dictionary (cl_method, cluster, annotation) -> cell-type mapping
# --------------------------------------------------------------------------- #
def load_annotation_dictionary(path: str) -> pl.DataFrame:
    """Load the annotation dictionary, matching ClusteringAnalysis conventions.

    Required columns: cl_method, cluster, annotation (all treated as strings).
    Several clusters may share one annotation (e.g. 3, 7, 12 -> 'Tcells').
    """
    ad = read_table(path)
    required = {"cl_method", "cluster", "annotation"}
    missing = required - set(ad.columns)
    if missing:
        raise ValueError(
            "Annotation dictionary must contain columns: cl_method, cluster, "
            f"annotation. Missing: {sorted(missing)}"
        )
    return ad.with_columns([
        pl.col("cl_method").cast(pl.Utf8).str.strip_chars().alias("cl_method"),
        pl.col("cluster").cast(pl.Utf8).str.strip_chars().alias("cluster"),
        pl.col("annotation").cast(pl.Utf8).str.strip_chars().alias("annotation"),
    ])


def resolve_clusters_for_annotation(
    ad: pl.DataFrame, cl_method: str, annotation: str
) -> list[str]:
    """Return every cluster id mapped to `annotation` for the given method."""
    cl_method = str(cl_method).strip()
    annotation = str(annotation).strip()

    rows = ad.filter(
        (pl.col("cl_method") == cl_method)
        & (pl.col("annotation") == annotation)
    )
    clusters = rows.select(pl.col("cluster")).unique().to_series().to_list()

    if not clusters:
        available = (
            ad.filter(pl.col("cl_method") == cl_method)
              .select(pl.col("annotation"))
              .unique()
              .sort("annotation")
              .to_series()
              .to_list()
        )
        raise ValueError(
            f"Annotation '{annotation}' not found for method '{cl_method}'.\n"
            f"Available annotations for {cl_method}: "
            f"{', '.join(map(str, available)) if available else '(none)'}"
        )
    return clusters


# --------------------------------------------------------------------------- #
# Density computation
# --------------------------------------------------------------------------- #
def compute_axis_range(values: np.ndarray, q_low: float, q_high: float) -> list[float]:
    """Percentile-based range, with the same fallbacks as compute_marker_ranges."""
    vals = values[np.isfinite(values)]
    if vals.size == 0:
        return [0.0, 1.0]

    lo = float(np.quantile(vals, q_low))
    hi = float(np.quantile(vals, q_high))

    if not np.isfinite(lo) or not np.isfinite(hi) or lo == hi:
        lo = float(np.min(vals))
        hi = float(np.max(vals))
        if lo == hi:
            hi = lo + 1e-6
    return [lo, hi]


def density2d(x, y, x_range, y_range, bins, log_density: bool, smooth_sigma: float):
    """2D histogram on a fixed grid. Optionally log1p-compressed and smoothed.

    Returns x/y bin centres and the density matrix already transposed for
    Plotly heatmap orientation (z[row=y, col=x]), matching the convention in
    PreComputePairWiseDensity.density2d.
    """
    H, x_edges, y_edges = np.histogram2d(
        x, y, bins=bins, range=[x_range, y_range]
    )

    if smooth_sigma and smooth_sigma > 0:
        try:
            from scipy.ndimage import gaussian_filter
            H = gaussian_filter(H, sigma=float(smooth_sigma), mode="nearest")
        except ImportError:
            warnings.warn(
                "scipy not available; skipping smoothing.", RuntimeWarning
            )

    if log_density:
        H = np.log1p(H)

    x_centers = (x_edges[:-1] + x_edges[1:]) / 2
    y_centers = (y_edges[:-1] + y_edges[1:]) / 2

    return x_centers, y_centers, H.T  # transpose for plotly orientation


# --------------------------------------------------------------------------- #
# Figure construction (importable: an interactive app can call this directly)
# --------------------------------------------------------------------------- #
def build_density_figure(
    df: pl.DataFrame,
    x_col: str,
    y_col: str,
    target_values,                          # str | iterable of cluster ids to highlight
    selection_label: str | None = None,     # title/colorbar label (e.g. "Tcells")
    cl_method: str = "clustering",
    bins: int = 96,
    background: str = "density",          # density | contour | points | none
    background_population: str = "others",  # others | all
    colorscale: str = "Viridis",
    q_low: float = 0.01,
    q_high: float = 0.99,
    log_density: bool = True,
    smooth_sigma: float = 0.0,
    point_size: float = 2.0,
) -> go.Figure:
    """Build the flow-cytometry-style figure for one marker pair.

    The highlighted population is the union of every cluster id in
    `target_values`. Pass a single cluster id to highlight one cluster, or the
    several cluster ids that share a cell-type annotation to highlight a whole
    cell type. `df` must contain columns x_col, y_col and a string 'cluster'
    column.
    """
    # Normalise the target into a set of strings.
    if isinstance(target_values, (str, int)):
        target_set = {str(target_values)}
    else:
        target_set = {str(v) for v in target_values}
    if not target_set:
        raise ValueError("No target cluster(s) to highlight.")

    if selection_label is None:
        selection_label = (
            f"cluster {next(iter(target_set))}" if len(target_set) == 1
            else "selection"
        )

    df = df.with_columns(pl.col("cluster").cast(pl.Utf8).alias("cluster"))

    x_all = df.select(pl.col(x_col).cast(pl.Float32)).to_series().to_numpy()
    y_all = df.select(pl.col(y_col).cast(pl.Float32)).to_series().to_numpy()

    is_cluster = (
        df.select(pl.col("cluster").is_in(list(target_set)).alias("m"))
        .to_series()
        .to_numpy()
    )

    n_in = int(is_cluster.sum())
    n_out = int((~is_cluster).sum())
    if n_in == 0:
        available = (
            df.select(pl.col("cluster")).unique().sort("cluster").to_series().to_list()
        )
        raise ValueError(
            f"Selection {sorted(target_set)} has no cells. "
            f"Available clusters: {', '.join(map(str, available))}"
        )

    # Shared axis ranges computed over ALL cells so the view is stable
    # regardless of which population is highlighted.
    x_range = compute_axis_range(x_all, q_low, q_high)
    y_range = compute_axis_range(y_all, q_low, q_high)

    x_in, y_in = x_all[is_cluster], y_all[is_cluster]
    x_bg_pts, y_bg_pts = x_all[~is_cluster], y_all[~is_cluster]

    # Background population for the density/contour layers
    if background_population == "all":
        x_bg, y_bg = x_all, y_all
    else:  # "others" -> the rest of the cells (default; matches the request)
        x_bg, y_bg = x_bg_pts, y_bg_pts

    fig = go.Figure()

    # ---- Background layer: the rest of the cells ----
    if background != "none" and x_bg.size > 0:
        xc_bg, yc_bg, z_bg = density2d(
            x_bg, y_bg, x_range, y_range, bins, log_density, smooth_sigma
        )

        if background == "points":
            fig.add_trace(
                go.Scattergl(
                    x=x_bg_pts,
                    y=y_bg_pts,
                    mode="markers",
                    marker=dict(size=point_size, color="lightgrey", opacity=0.5),
                    name="other cells",
                    hoverinfo="skip",
                )
            )
        elif background == "contour":
            z = z_bg.copy()
            z[z <= 0] = np.nan
            zmax = np.nanmax(z) if np.isfinite(z).any() else 0
            if zmax > 0:
                z = z / zmax
                fig.add_trace(
                    go.Contour(
                        x=xc_bg,
                        y=yc_bg,
                        z=z,
                        contours=dict(
                            coloring="none",
                            showlabels=False,
                            start=0.1,
                            end=0.95,
                            size=0.15,
                        ),
                        line=dict(color="rgba(80,80,80,0.7)", width=1),
                        showscale=False,
                        hoverinfo="skip",
                        name="other cells",
                    )
                )
        else:  # "density" (default): grey heatmap of the rest
            z = z_bg.copy()
            z[z <= 0] = np.nan  # empty bins transparent -> white background
            fig.add_trace(
                go.Heatmap(
                    x=xc_bg,
                    y=yc_bg,
                    z=z,
                    colorscale=[[0.0, "rgba(220,220,220,0.0)"],
                                [0.15, "rgba(200,200,200,0.55)"],
                                [1.0, "rgba(120,120,120,0.9)"]],
                    showscale=False,
                    hoverinfo="skip",
                    name="other cells",
                )
            )

    # ---- Foreground layer: the highlighted population (2D histogram by density) ----
    xc, yc, z_cluster = density2d(
        x_in, y_in, x_range, y_range, bins, log_density, smooth_sigma
    )
    z_cluster = z_cluster.astype(float)
    z_cluster[z_cluster <= 0] = np.nan  # empty bins transparent so bg shows through

    density_label = "log<sub>1p</sub> count" if log_density else "count"
    fig.add_trace(
        go.Heatmap(
            x=xc,
            y=yc,
            z=z_cluster,
            colorscale=colorscale,
            colorbar=dict(title=f"{selection_label}<br>{density_label}"),
            zsmooth=False,
            hovertemplate=(
                f"{x_col}: %{{x:.3f}}<br>"
                f"{y_col}: %{{y:.3f}}<br>"
                f"{density_label}: %{{z:.3f}}<extra></extra>"
            ),
            name=selection_label,
        )
    )

    pct = 100.0 * n_in / max(n_in + n_out, 1)
    members = sorted(target_set)
    member_note = (
        f" (clusters {', '.join(members)})" if len(members) > 1 else ""
    )
    fig.update_layout(
        title=(
            f"{cl_method} — {selection_label} highlighted{member_note} "
            f"({n_in:,} cells, {pct:.1f}% of {n_in + n_out:,})<br>"
            f"<sup>{x_col} vs {y_col}</sup>"
        ),
        xaxis=dict(title=x_col, range=x_range, zeroline=False,
                   showgrid=False, constrain="domain"),
        yaxis=dict(title=y_col, range=y_range, zeroline=False,
                   showgrid=False, scaleanchor=None),
        template="plotly_white",
        width=720,
        height=640,
        font=dict(size=12),
        showlegend=False,
    )
    return fig


# --------------------------------------------------------------------------- #
# Output (mirrors ClusteringAnalysis.write_plotly_figure: .html + .json)
# --------------------------------------------------------------------------- #
def write_plotly_figure(fig: go.Figure, output_file: str) -> tuple[Path, Path]:
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    html_file = output_file.with_suffix(".html")
    json_file = output_file.with_suffix(".json")

    fig.write_html(html_file, include_plotlyjs="cdn")
    fig.write_json(json_file, pretty=True)

    print(f"Wrote: {html_file}")
    print(f"Wrote: {json_file}")
    return html_file, json_file


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def cluster_density_plot(
    input_csv: str,
    marker_a: str,
    marker_b: str,
    cluster_value: str | None = None,
    annotation: str | None = None,
    annotation_dict_path: str | None = None,
    output_file: str | None = None,
    cluster_file: str | None = None,
    cluster_folder: str | None = None,
    clustering_method: str | None = None,
    bins: int = 96,
    background: str = "density",
    background_population: str = "others",
    colorscale: str = "Viridis",
    q_low: float = 0.01,
    q_high: float = 0.99,
    log_density: bool = True,
    smooth_sigma: float = 0.0,
) -> go.Figure:
    # Exactly one of cluster / annotation must be given.
    if (cluster_value is None) == (annotation is None):
        raise ValueError(
            "Provide exactly one of --cluster (single cluster) or "
            "--annotation (cell type, requires --path.annotation.dictionary)."
        )
    if annotation is not None and not annotation_dict_path:
        raise ValueError(
            "--annotation requires --path.annotation.dictionary."
        )

    cluster_path = resolve_cluster_path(cluster_file, cluster_folder, clustering_method)

    print(f"### sampled data: {input_csv} ###")
    print(f"### cluster file: {cluster_path} ###")
    print(f"### marker A (x): {marker_a} | marker B (y): {marker_b} ###")
    if annotation is not None:
        print(f"### cell type to highlight: {annotation} ###")
    else:
        print(f"### cluster to highlight: {cluster_value} ###")

    df_data = read_table(input_csv)
    df_clusters = read_table(cluster_path)

    for c in REQUIRED_ID_COLS:
        if c not in df_data.columns:
            raise ValueError(f"Sampled data missing required column: {c}")
        if c not in df_clusters.columns:
            raise ValueError(f"Cluster data missing required column: {c}")
    if "cluster" not in df_clusters.columns:
        raise ValueError("Cluster file must contain a 'cluster' column.")

    # Resolve marker names against the actual data columns.
    lookup = build_norm_lookup(df_data.columns)
    x_col = resolve_one_marker(marker_a, lookup)
    y_col = resolve_one_marker(marker_b, lookup)

    # Method label: prefer the file's own cl_method, else the CLI value.
    if "cl_method" in df_clusters.columns:
        cl_method = df_clusters.select(pl.col("cl_method").cast(pl.Utf8).first()).item()
    else:
        cl_method = clustering_method or "clustering"

    # Resolve which cluster id(s) to highlight, and the label to display.
    if annotation is not None:
        ad = load_annotation_dictionary(annotation_dict_path)
        target_values = resolve_clusters_for_annotation(ad, cl_method, annotation)
        selection_label = annotation
        print(f"### '{annotation}' maps to clusters: "
              f"{', '.join(map(str, sorted(target_values)))} ###")
    else:
        target_values = [str(cluster_value)]
        selection_label = f"cluster {cluster_value}"

    # Keep only what we need, then inner-join on the shared IDs.
    df_data = df_data.select(REQUIRED_ID_COLS + list({x_col, y_col}))
    keep_cluster_cols = [c for c in df_clusters.columns
                         if c in REQUIRED_ID_COLS + ["cluster"]]
    df_clusters = df_clusters.select(keep_cluster_cols)

    df = df_data.join(df_clusters, on=REQUIRED_ID_COLS, how="inner")
    if df.height == 0:
        raise ValueError(
            "Join between sampled data and clustering produced 0 rows. "
            "Check that both come from the same sampling run."
        )

    fig = build_density_figure(
        df=df,
        x_col=x_col,
        y_col=y_col,
        target_values=target_values,
        selection_label=selection_label,
        cl_method=cl_method,
        bins=bins,
        background=background,
        background_population=background_population,
        colorscale=colorscale,
        q_low=q_low,
        q_high=q_high,
        log_density=log_density,
        smooth_sigma=smooth_sigma,
    )

    if output_file:
        write_plotly_figure(fig, output_file)

    return fig


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Flow-cytometry-style 2D density plot highlighting one "
                    "cluster, or a whole cell type (several clusters), for one "
                    "marker pair.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--path.input.csv", required=True,
                   help="Sampled data (csv/parquet) with sample_id, OID and markers.")

    # Two ways to point at the clustering result.
    p.add_argument("--path.input.cluster", default=None,
                   help="Direct path to a clustering file (csv/parquet).")
    p.add_argument("--path.cluster.folder", default=None,
                   help="Folder containing <method>.parquet (used with --clustering.method).")
    p.add_argument("--clustering.method", default=None,
                   help="phenograph | kmeans | som. Resolves <folder>/<method>.parquet "
                        "and/or labels the plot.")

    p.add_argument("--marker.a", required=True, help="Marker on the x axis.")
    p.add_argument("--marker.b", required=True, help="Marker on the y axis.")

    # Highlight EITHER one cluster OR a cell type (several clusters).
    sel = p.add_mutually_exclusive_group(required=True)
    sel.add_argument("--cluster", default=None,
                     help="Single cluster value to highlight.")
    sel.add_argument("--annotation", default=None,
                     help="Cell type to highlight; all clusters mapped to this "
                          "annotation (for the chosen method) are combined. "
                          "Requires --path.annotation.dictionary.")
    p.add_argument("--path.annotation.dictionary", default=None,
                   help="Annotation dictionary (csv/parquet) with columns "
                        "cl_method, cluster, annotation. Required with --annotation.")

    p.add_argument("--path.output.file", default=None,
                   help="Output base path; .html and .json are written. "
                        "If omitted, nothing is written (figure built only).")

    p.add_argument("--bins", type=int, default=96, help="Number of bins per axis.")
    p.add_argument("--background", default="density",
                   choices=["density", "contour", "points", "none"],
                   help="How the rest of the cells are drawn.")
    p.add_argument("--background.population", default="others",
                   choices=["others", "all"],
                   help="Background uses the rest of the cells, or all cells.")
    p.add_argument("--colorscale", default="Viridis",
                   help="Plotly colorscale for the highlighted population.")
    p.add_argument("--q.low", type=float, default=0.01,
                   help="Lower quantile for axis ranges.")
    p.add_argument("--q.high", type=float, default=0.99,
                   help="Upper quantile for axis ranges.")
    p.add_argument("--log.density", type=int, default=1, choices=[0, 1],
                   help="Apply log1p to histogram counts (1=yes).")
    p.add_argument("--smooth.sigma", type=float, default=0.0,
                   help="Gaussian smoothing sigma (0=off; ~0.8 gives a smoother "
                        "flow-cytometry look).")
    return p


def main() -> None:
    args = build_parser().parse_args()
    cluster_density_plot(
        input_csv=getattr(args, "path.input.csv"),
        marker_a=getattr(args, "marker.a"),
        marker_b=getattr(args, "marker.b"),
        cluster_value=getattr(args, "cluster"),
        annotation=getattr(args, "annotation"),
        annotation_dict_path=getattr(args, "path.annotation.dictionary"),
        output_file=getattr(args, "path.output.file"),
        cluster_file=getattr(args, "path.input.cluster"),
        cluster_folder=getattr(args, "path.cluster.folder"),
        clustering_method=getattr(args, "clustering.method"),
        bins=getattr(args, "bins"),
        background=getattr(args, "background"),
        background_population=getattr(args, "background.population"),
        colorscale=getattr(args, "colorscale"),
        q_low=getattr(args, "q.low"),
        q_high=getattr(args, "q.high"),
        log_density=bool(getattr(args, "log.density")),
        smooth_sigma=getattr(args, "smooth.sigma"),
    )


if __name__ == "__main__":
    main()
