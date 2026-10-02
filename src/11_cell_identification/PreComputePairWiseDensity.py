#!/usr/bin/env python3

import argparse
import csv
import json
import warnings
from itertools import combinations
from pathlib import Path

import numpy as np
import polars as pl

import plotly.graph_objects as go
from plotly.subplots import make_subplots

REQUIRED_ID_COLS = ["sample_id", "OID"]


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


def compute_marker_ranges(df: pl.DataFrame, marker_cols: list[str], q_low=0.01, q_high=0.99):
    ranges = {}

    for marker in marker_cols:
        vals = (
            df.select(pl.col(marker).cast(pl.Float32, strict=False))
              .drop_nulls()
              .to_series()
              .to_numpy()
        )

        if vals.size == 0:
            ranges[marker] = [0.0, 1.0]
            continue

        lo = float(np.quantile(vals, q_low))
        hi = float(np.quantile(vals, q_high))

        if not np.isfinite(lo) or not np.isfinite(hi) or lo == hi:
            lo = float(np.nanmin(vals))
            hi = float(np.nanmax(vals))
            if lo == hi:
                hi = lo + 1e-6

        ranges[marker] = [lo, hi]

    return ranges


def select_top_markers(df_all: pl.DataFrame, marker_cols: list[str], cluster_col: str, cluster_value: str, top_n=10):
    tmp = df_all.with_columns(
        (pl.col(cluster_col).cast(pl.Utf8) == str(cluster_value)).alias("__is_cluster")
    )

    stats = []

    for marker in marker_cols:
        mean_in = (
            tmp.filter(pl.col("__is_cluster"))
               .select(pl.col(marker).cast(pl.Float32).mean())
               .item()
        )
        mean_out = (
            tmp.filter(~pl.col("__is_cluster"))
               .select(pl.col(marker).cast(pl.Float32).mean())
               .item()
        )

        mean_in = float(mean_in) if mean_in is not None else np.nan
        mean_out = float(mean_out) if mean_out is not None else np.nan
        delta = mean_in - mean_out if np.isfinite(mean_in) and np.isfinite(mean_out) else np.nan

        stats.append({
            "marker": marker,
            "mean_in_cluster": mean_in,
            "mean_out_cluster": mean_out,
            "delta": delta,
        })

    # Rank by mean expression in cluster, as requested
    stats_sorted = sorted(
        stats,
        key=lambda x: (-np.inf if not np.isfinite(x["mean_in_cluster"]) else -x["mean_in_cluster"])
    )

    selected = [x["marker"] for x in stats_sorted[:min(top_n, len(stats_sorted))]]

    return selected, stats_sorted


def density2d(x, y, x_range, y_range, bins=96):
    H, x_edges, y_edges = np.histogram2d(
        x, y,
        bins=bins,
        range=[x_range, y_range]
    )
    H = np.log1p(H)
    return {
        "x_edges": x_edges.tolist(),
        "y_edges": y_edges.tolist(),
        "z": H.T.tolist(),  # transpose for plotly heatmap orientation
    }


def save_json(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def write_cluster_pairwise_html(cluster_payload: dict, output_html: str) -> None:
    import numpy as np
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from pathlib import Path

    output_html = Path(output_html)
    output_html.parent.mkdir(parents=True, exist_ok=True)

    pairs = cluster_payload["pairs"]
    n_pairs = len(pairs)

    if n_pairs == 0:
        return

    if n_pairs == 45:
        n_cols = 9
    else:
        n_cols = min(6, int(np.ceil(np.sqrt(n_pairs))))

    n_rows = int(np.ceil(n_pairs / n_cols))

    vertical_spacing = min(0.08, 0.9 / max(n_rows - 1, 1))
    horizontal_spacing = min(0.06, 0.9 / max(n_cols - 1, 1))

    subplot_titles = [
        f"{p['x_marker']} vs {p['y_marker']}"
        for p in pairs
    ]

    fig = make_subplots(
        rows=n_rows,
        cols=n_cols,
        subplot_titles=subplot_titles,
        horizontal_spacing=horizontal_spacing,
        vertical_spacing=vertical_spacing,
    )

    for idx, pair in enumerate(pairs):
        row = idx // n_cols + 1
        col = idx % n_cols + 1

        cluster_density = pair["cluster_density"]

        # Prefer whole-population contour if available.
        # Fall back to "other cells" contour for compatibility with older JSON.
        contour_density = pair.get("all_density", pair.get("other_density", None))

        x_edges = np.asarray(cluster_density["x_edges"], dtype=float)
        y_edges = np.asarray(cluster_density["y_edges"], dtype=float)

        x_centers = (x_edges[:-1] + x_edges[1:]) / 2
        y_centers = (y_edges[:-1] + y_edges[1:]) / 2

        z_cluster = np.asarray(cluster_density["z"], dtype=float)
        z_cluster[z_cluster <= 0] = np.nan

        # Selected-cluster density as heatmap
        fig.add_trace(
            go.Heatmap(
                x=x_centers,
                y=y_centers,
                z=z_cluster,
                colorscale="Viridis",
                showscale=(idx == 0),
                colorbar=dict(title="cluster<br>log1p count") if idx == 0 else None,
                hovertemplate=(
                    f"{pair['x_marker']}: %{{x:.3f}}<br>"
                    f"{pair['y_marker']}: %{{y:.3f}}<br>"
                    "cluster log1p count: %{z:.3f}<extra></extra>"
                ),
            ),
            row=row,
            col=col,
        )

        # Whole-population contour overlay
        if contour_density is not None:
            z_contour = np.asarray(contour_density["z"], dtype=float)

            # Hide empty bins and very low background.
            z_contour[z_contour <= 0] = np.nan

            # Normalize contour only for visualization, so contour levels are comparable
            # across marker pairs even if total counts differ.
            if np.isfinite(z_contour).any():
                z_max = np.nanmax(z_contour)
                if z_max > 0:
                    z_contour = z_contour / z_max

                fig.add_trace(
                    go.Contour(
                        x=x_centers,
                        y=y_centers,
                        z=z_contour,
                        contours=dict(
                            coloring="none",
                            showlabels=False,
                            start=0.2,
                            end=0.95,
                            size=0.15,
                        ),
                        line=dict(
                            color="black",
                            width=1,
                        ),
                        opacity=0.65,
                        showscale=False,
                        hoverinfo="skip",
                    ),
                    row=row,
                    col=col,
                )

        fig.update_xaxes(title_text=pair["x_marker"], row=row, col=col)
        fig.update_yaxes(title_text=pair["y_marker"], row=row, col=col)

    fig.update_layout(
        width=max(1400, 260 * n_cols),
        height=max(900, 260 * n_rows),
        title=(
            f"{cluster_payload.get('cl_method', 'clustering')} "
            f"cluster {cluster_payload.get('cluster', '')} "
            "pairwise marker densities"
        ),
        template="plotly_white",
        font=dict(size=10),
        showlegend=False,
    )

    fig.write_html(str(output_html), include_plotlyjs="cdn")


def precompute_pairwise_density(
    marker_list_csv: str,
    input_csv: str,
    cluster_csv: str,
    output_folder: str,
    top_n_markers: int = 10,
    bins: int = 96,
):
    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    df_data = read_table(input_csv)
    df_clusters = read_table(cluster_csv)

    for c in REQUIRED_ID_COLS:
        if c not in df_data.columns:
            raise ValueError(f"Input data missing required column: {c}")
        if c not in df_clusters.columns:
            raise ValueError(f"Cluster data missing required column: {c}")

    marker_ids = load_marker_list(marker_list_csv)
    marker_cols = resolve_marker_columns(marker_ids, df_data.columns)

    df_data = df_data.select(REQUIRED_ID_COLS + marker_cols)
    df_clusters = df_clusters.select([c for c in df_clusters.columns if c in REQUIRED_ID_COLS + ["cl_method", "cluster"]])

    df = df_data.join(df_clusters, on=REQUIRED_ID_COLS, how="inner")

    if "cl_method" not in df.columns or "cluster" not in df.columns:
        raise ValueError("Cluster file must contain 'cl_method' and 'cluster' columns.")

    marker_ranges = compute_marker_ranges(df, marker_cols)

    cl_method = df.select(pl.col("cl_method").cast(pl.Utf8).first()).item()
    cluster_values = (
        df.select(pl.col("cluster").cast(pl.Utf8))
          .unique()
          .sort("cluster")
          .to_series()
          .to_list()
    )

    manifest = {
        "cl_method": cl_method,
        "clusters": [],
    }

    for cluster_value in cluster_values:
        df_cluster = df.with_columns(pl.col("cluster").cast(pl.Utf8).alias("cluster"))

        selected_markers, marker_stats = select_top_markers(
            df_all=df_cluster,
            marker_cols=marker_cols,
            cluster_col="cluster",
            cluster_value=cluster_value,
            top_n=top_n_markers,
        )

        pairs_data = []

        df_in = df_cluster.filter(pl.col("cluster") == str(cluster_value))
        df_out = df_cluster.filter(pl.col("cluster") != str(cluster_value))

        n_in = df_in.height
        n_out = df_out.height

        for x_marker, y_marker in combinations(selected_markers, 2):
            x_range = marker_ranges[x_marker]
            y_range = marker_ranges[y_marker]

            x_all = df_cluster.select(pl.col(x_marker).cast(pl.Float32)).to_series().to_numpy()
            y_all = df_cluster.select(pl.col(y_marker).cast(pl.Float32)).to_series().to_numpy()

            all_density = density2d(x_all, y_all, x_range, y_range, bins=bins)

            x_in = df_in.select(pl.col(x_marker).cast(pl.Float32)).to_series().to_numpy()
            y_in = df_in.select(pl.col(y_marker).cast(pl.Float32)).to_series().to_numpy()

            x_out = df_out.select(pl.col(x_marker).cast(pl.Float32)).to_series().to_numpy()
            y_out = df_out.select(pl.col(y_marker).cast(pl.Float32)).to_series().to_numpy()

            cluster_density = density2d(x_in, y_in, x_range, y_range, bins=bins)
            other_density = density2d(x_out, y_out, x_range, y_range, bins=bins)

            z_cluster = np.array(cluster_density["z"], dtype=np.float32)
            z_other = np.array(other_density["z"], dtype=np.float32)
            z_diff = (z_cluster - z_other).tolist()

            pairs_data.append({
                "x_marker": x_marker,
                "y_marker": y_marker,
                "x_range": x_range,
                "y_range": y_range,
                "n_cluster": n_in,
                "n_other": n_out,
                "cluster_density": cluster_density,
                "other_density": other_density,
                "all_density": all_density,
                "diff_density": z_diff,
            })

        cluster_payload = {
            "cl_method": cl_method,
            "cluster": str(cluster_value),
            "selected_markers": selected_markers,
            "marker_stats": marker_stats,
            "pairs": pairs_data,
        }

        cluster_file = out_dir / f"cluster_{cluster_value}.json"
        save_json(cluster_payload, cluster_file)
        
        html_file = out_dir / f"cluster_{cluster_value}.html"
        write_cluster_pairwise_html(cluster_payload, html_file)

        manifest["clusters"].append({
            "cluster": str(cluster_value),
            "file": cluster_file.name,
            "selected_markers": selected_markers,
            "n_pairs": len(pairs_data),
            "n_cells_cluster": n_in,
            "n_cells_other": n_out,
        })

    save_json(manifest, out_dir / "index.json")


def build_parser():
    p = argparse.ArgumentParser(description="Precompute pairwise density plots per cluster.")
    p.add_argument("--input.marker.list", required=True, help="Path to marker list csv/parquet.")
    p.add_argument("--path.input.csv", required=True, help="Path to sampled input data csv/parquet.")
    p.add_argument("--path.input.cluster", required=True, help="Path to one clustering file csv/parquet.")
    p.add_argument("--path.output.folder", required=True, help="Output folder for JSON files.")
    p.add_argument("--top.n.markers", type=int, default=10, help="Maximum number of markers per cluster.")
    p.add_argument("--bins", type=int, default=96, help="Number of bins for 2D density.")
    return p


def main():
    args = build_parser().parse_args()

    precompute_pairwise_density(
        marker_list_csv=getattr(args, "input.marker.list"),
        input_csv=getattr(args, "path.input.csv"),
        cluster_csv=getattr(args, "path.input.cluster"),
        output_folder=getattr(args, "path.output.folder"),
        top_n_markers=getattr(args, "top.n.markers"),
        bins=getattr(args, "bins"),
    )


if __name__ == "__main__":
    main()
