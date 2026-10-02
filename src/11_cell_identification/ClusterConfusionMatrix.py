#!/usr/bin/env python3

import argparse
import csv
from pathlib import Path

import polars as pl


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


# ============================================================
# Core: one function, usable for both raw numeric clusters
# (multiple clustering_method values) and consensus/annotated
# labels (a single constant clustering_method value).
# ============================================================

def build_confusion_matrix(
    df: pl.DataFrame,
    method_col: str,
    label_col: str,
    sample_col: str = "sample_id",
    id_col: str = "OID",
) -> pl.DataFrame:
    """Dense (cluster x sample) confusion matrix, one block per method_col value.

    N = cells carrying both this label and this sample_id. J (Jaccard) and dice measure
    overlap between "cells with this label" and "cells in this sample" as two sets --
    same convention as make_jaccard_matrix() in ClusteringStability.py -- so a small
    cluster that's fully confined to one sample still scores high, which is the point
    (catching sample/batch-driven clusters), not just a raw proportion of the sample.

    Dense: every (label, sample) pair observed for a given method is included, even
    combinations with N=0 (that label exists under this method, but not in this sample).
    """
    df = df.select([method_col, label_col, sample_col, id_col]).rename({
        method_col: "clustering_method",
        label_col: "cluster",
        sample_col: "sample_id",
        id_col: "_id",
    })

    # OID is only unique within a sample (a per-scene object index, not a global cell id) --
    # e.g. real MVM data has 40,405 rows but only 25,014 distinct raw OID values, because
    # OID=1 in one sample and OID=1 in another are different cells. Counting n_unique("_id")
    # alone silently undercounts any total that spans more than one sample (N_cluster below),
    # since it dedupes across samples where it shouldn't. sample_id+OID together are the real
    # unique cell key (confirmed: unique (sample_id, OID) pairs == row count on real data).
    df = df.with_columns(pl.struct(["sample_id", "_id"]).alias("_cell_id"))

    clusters = df.select(["clustering_method", "cluster"]).unique()
    samples = df.select(["clustering_method", "sample_id"]).unique()
    grid = clusters.join(samples, on="clustering_method", how="inner")

    observed = (
        df.group_by(["clustering_method", "cluster", "sample_id"])
        .agg(pl.col("_cell_id").n_unique().alias("N"))
    )

    cluster_totals = (
        df.group_by(["clustering_method", "cluster"])
        .agg(pl.col("_cell_id").n_unique().alias("N_cluster"))
    )

    sample_totals = (
        df.group_by(["clustering_method", "sample_id"])
        .agg(pl.col("_cell_id").n_unique().alias("N_sample"))
    )

    out = (
        grid
        .join(observed, on=["clustering_method", "cluster", "sample_id"], how="left")
        .with_columns(pl.col("N").fill_null(0))
        .join(cluster_totals, on=["clustering_method", "cluster"], how="left")
        .join(sample_totals, on=["clustering_method", "sample_id"], how="left")
    )

    union_n = pl.col("N_cluster") + pl.col("N_sample") - pl.col("N")
    sum_n = pl.col("N_cluster") + pl.col("N_sample")

    out = out.with_columns([
        pl.when(union_n == 0).then(0.0).otherwise(pl.col("N") / union_n).alias("J"),
        pl.when(sum_n == 0).then(0.0).otherwise(2 * pl.col("N") / sum_n).alias("dice"),
    ])

    return (
        out
        .select(["clustering_method", "cluster", "sample_id", "N", "J", "dice"])
        .sort(["clustering_method", "cluster", "sample_id"])
    )


# ============================================================
# Mode-specific loaders
# ============================================================

def load_mapped_clusters(paths: list) -> pl.DataFrame:
    """Stack MapClusters.py outputs (one file per clustering method). Each file already
    carries its own 'cl_method' column (phenograph/kmeans/som), so no relabeling needed --
    just concatenate. Entries that are None/empty/'not included' (a method that wasn't run)
    are skipped, matching run_cell_identification_pipeline.py's own sentinel convention."""
    frames = []

    for p in paths:
        if not p or p == "not included":
            continue

        df = read_table(p)
        required = ["cl_method", "cluster_mapped", "sample_id", "OID"]
        missing = [c for c in required if c not in df.columns]

        if missing:
            raise ValueError(f"{p} is missing required columns: {', '.join(missing)}")

        frames.append(df.select(required))

    if not frames:
        raise ValueError("No input files given (all were empty or 'not included').")

    return pl.concat(frames, how="vertical_relaxed")


def load_annotated(path: str, label_col: str, method_label: str) -> pl.DataFrame:
    """A single consensus/fingerprint-annotated full-dataset file. There's no per-cell
    clustering method anymore at this point, so every row gets the same constant
    clustering_method value (method_label) instead."""
    df = read_table(path)
    required = ["sample_id", "OID", label_col]
    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")

    return (
        df.select(required)
        .with_columns(pl.lit(method_label).alias("cl_method"))
    )


# ============================================================
# CLI
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a (cluster x sample) confusion matrix -- N, Jaccard, Dice -- from either "
            "raw numeric cluster assignments (per clustering method) or a single consensus/"
            "annotated label set. Same underlying function either way."
        )
    )

    parser.add_argument(
        "--mode", required=True, choices=["clusters", "annotated"],
        help=(
            "'clusters': stack the numeric per-method mapped-cluster files (phenograph/kmeans/som). "
            "'annotated': use a single consensus- or fingerprint-annotated file instead, with a "
            "constant clustering_method value in place of the per-method column."
        ),
    )

    parser.add_argument("--path.input.phenograph", default=None,
                        help="[clusters mode] Path to phenograph_mapped_clusters.parquet, or omit/'not included' to skip.")
    parser.add_argument("--path.input.kmeans", default=None,
                        help="[clusters mode] Path to kmeans_mapped_clusters.parquet, or omit/'not included' to skip.")
    parser.add_argument("--path.input.som", default=None,
                        help="[clusters mode] Path to som_mapped_clusters.parquet, or omit/'not included' to skip.")

    parser.add_argument("--path.input.annotated", default=None,
                        help="[annotated mode] Path to the consensus/fingerprint-annotated full-dataset file (e.g. fingerprint_predictions.parquet).")
    parser.add_argument("--label.col", default="CellType",
                        help="[annotated mode] Column holding the annotation label (default: CellType).")
    parser.add_argument("--method.label", default="consensus",
                        help="[annotated mode] Constant value used in place of clustering_method (default: consensus).")

    parser.add_argument("--path.output.csv", required=True,
                        help="Path to output csv/parquet for the confusion matrix.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    mode = args.mode

    print(f"### mode: {mode} ###")

    if mode == "clusters":
        paths = [
            getattr(args, "path.input.phenograph"),
            getattr(args, "path.input.kmeans"),
            getattr(args, "path.input.som"),
        ]
        df = load_mapped_clusters(paths)
        result = build_confusion_matrix(df, method_col="cl_method", label_col="cluster_mapped")
    else:
        annotated_path = getattr(args, "path.input.annotated")

        if not annotated_path:
            raise ValueError("--path.input.annotated is required in 'annotated' mode.")

        label_col = getattr(args, "label.col")
        method_label = getattr(args, "method.label")
        df = load_annotated(annotated_path, label_col=label_col, method_label=method_label)
        result = build_confusion_matrix(df, method_col="cl_method", label_col=label_col)

    print(f"{result.height} (clustering_method, cluster, sample_id) rows")

    output_csv = getattr(args, "path.output.csv")
    write_table(result, output_csv)

    print("Done")


if __name__ == "__main__":
    main()
