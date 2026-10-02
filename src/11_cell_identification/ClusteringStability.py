#!/usr/bin/env python3

import argparse
import csv
import itertools
import warnings
from pathlib import Path

import polars as pl
import pandas as pd
import plotly.graph_objects as go


REQUIRED_ID_COLS = ["sample_id", "OID"]


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


def write_plotly_figure(fig, output_file: Path) -> None:
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    html_file = output_file.with_suffix(".html")
    json_file = output_file.with_suffix(".json")

    fig.write_html(html_file, include_plotlyjs="cdn")
    fig.write_json(json_file, pretty=True)

    print(f"Wrote: {html_file}")
    print(f"Wrote: {json_file}")


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


def load_optional_cluster_table(path: str | None, label: str) -> pl.DataFrame | None:
    if not is_included(path):
        return None

    df = read_table(path)
    validate_required_ids(df, label)

    required = {"cl_method", "cluster"}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(f"{label} is missing columns: {sorted(missing)}")

    df = clean_required_ids(df)

    df = df.with_columns([
        pl.col("cl_method").cast(pl.Utf8).str.strip_chars().alias("cl_method"),
        pl.col("cluster").cast(pl.Utf8).str.strip_chars().alias("cluster"),
    ])

    return df


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
        df = load_optional_cluster_table(path, label)

        if df is not None:
            dfs.append(df)

    if len(dfs) == 0:
        raise ValueError("No clustering files were provided.")

    return pl.concat(dfs, how="vertical_relaxed")


def load_annotation_dictionary(annotation_dictionary: str) -> pl.DataFrame:
    if not is_included(annotation_dictionary):
        raise ValueError("An annotation dictionary is required for clustering stability.")

    df = read_table(annotation_dictionary)

    required = {"cl_method", "cluster", "annotation"}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "Annotation dictionary must contain cl_method, cluster, annotation. "
            f"Missing: {sorted(missing)}"
        )

    df = df.with_columns([
        pl.col("cl_method").cast(pl.Utf8).str.strip_chars().alias("cl_method"),
        pl.col("cluster").cast(pl.Utf8).str.strip_chars().alias("cluster"),
        pl.col("annotation").cast(pl.Utf8).str.strip_chars().alias("annotation"),
    ])

    return df.select(["cl_method", "cluster", "annotation"])


def annotate_clusters(df_clusters: pl.DataFrame, annotation_df: pl.DataFrame) -> pl.DataFrame:
    df = (
        df_clusters
        .join(
            annotation_df,
            on=["cl_method", "cluster"],
            how="left",
        )
        .with_columns(
            pl.coalesce(["annotation", "cluster"]).alias("annotation")
        )
        .drop("cluster")
        .with_columns(
            pl.col("annotation").cast(pl.Utf8).str.strip_chars().alias("annotation")
        )
    )

    n_missing = df.filter(pl.col("annotation").is_null()).height

    if n_missing > 0:
        warnings.warn(
            f"{n_missing} rows have missing annotation after dictionary mapping.",
            RuntimeWarning,
        )

    return df


def make_jaccard_matrix(
    df_annotated: pl.DataFrame,
    method_x: str,
    method_y: str,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    x_df = (
        df_annotated
        .filter(pl.col("cl_method") == method_x)
        .select(REQUIRED_ID_COLS + [pl.col("annotation").alias("X")])
        .unique()
    )

    y_df = (
        df_annotated
        .filter(pl.col("cl_method") == method_y)
        .select(REQUIRED_ID_COLS + [pl.col("annotation").alias("Y")])
        .unique()
    )

    paired = x_df.join(y_df, on=REQUIRED_ID_COLS, how="inner")

    if paired.height == 0:
        raise ValueError(f"No overlapping cells between {method_x} and {method_y}.")

    labels = (
        pl.concat(
            [
                paired.select(pl.col("X").alias("annotation")),
                paired.select(pl.col("Y").alias("annotation")),
            ],
            how="vertical",
        )
        .unique()
        .sort("annotation")
        .to_series()
        .to_list()
    )

    records = []

    for x_lab in labels:
        x_set = paired.filter(pl.col("X") == x_lab).select(REQUIRED_ID_COLS)
        x_n = x_set.height

        for y_lab in labels:
            y_set = paired.filter(pl.col("Y") == y_lab).select(REQUIRED_ID_COLS)
            y_n = y_set.height

            intersection_n = (
                x_set
                .join(y_set, on=REQUIRED_ID_COLS, how="inner")
                .height
            )

            union_n = x_n + y_n - intersection_n

            if union_n == 0:
                jaccard = 0.0
            else:
                jaccard = intersection_n / union_n

            records.append({
                "ClusterX": str(x_lab),
                "ClusterY": str(y_lab),
                "Jaccard": float(jaccard),
                "N": int(intersection_n),
                "method_x": method_x,
                "method_y": method_y,
            })

    # Add totals like the R code.
    for x_lab in labels:
        n = paired.filter(pl.col("X") == x_lab).height
        records.append({
            "ClusterX": str(x_lab),
            "ClusterY": "Total",
            "Jaccard": 0.0,
            "N": int(n),
            "method_x": method_x,
            "method_y": method_y,
        })

    for y_lab in labels:
        n = paired.filter(pl.col("Y") == y_lab).height
        records.append({
            "ClusterX": "Total",
            "ClusterY": str(y_lab),
            "Jaccard": 0.0,
            "N": int(n),
            "method_x": method_x,
            "method_y": method_y,
        })

    plot_df = pl.DataFrame(records)

    best_records = []

    no_total = plot_df.filter(
        (pl.col("ClusterX") != "Total") &
        (pl.col("ClusterY") != "Total")
    )

    for x_lab in labels:
        tmp = (
            no_total
            .filter(pl.col("ClusterX") == x_lab)
            .sort("Jaccard", descending=True)
            .head(1)
        )

        if tmp.height > 0 and tmp["Jaccard"][0] > 0:
            best_records.append({
                "method_x": method_x,
                "method_y": method_y,
                "source_method": method_x,
                "target_method": method_y,
                "source_annotation": str(x_lab),
                "target_annotation": tmp["ClusterY"][0],
                "Jaccard": float(tmp["Jaccard"][0]),
                "N": int(tmp["N"][0]),
            })

    for y_lab in labels:
        tmp = (
            no_total
            .filter(pl.col("ClusterY") == y_lab)
            .sort("Jaccard", descending=True)
            .head(1)
        )

        if tmp.height > 0 and tmp["Jaccard"][0] > 0:
            best_records.append({
                "method_x": method_y,
                "method_y": method_x,
                "source_method": method_y,
                "target_method": method_x,
                "source_annotation": str(y_lab),
                "target_annotation": tmp["ClusterX"][0],
                "Jaccard": float(tmp["Jaccard"][0]),
                "N": int(tmp["N"][0]),
            })

    best_df = pl.DataFrame(best_records) if best_records else pl.DataFrame()

    return plot_df, best_df


def plot_jaccard_matrix(
    plot_df: pl.DataFrame,
    method_x: str,
    method_y: str,
    output_folder: Path,
) -> None:
    pdf = plot_df.to_pandas()

    x_labels = list(dict.fromkeys(pdf["ClusterX"].tolist()))
    y_labels = list(dict.fromkeys(pdf["ClusterY"].tolist()))

    x_order = [x for x in x_labels if x != "Total"] + ["Total"]
    y_order = list(reversed([y for y in y_labels if y != "Total"] + ["Total"]))

    z = []
    text = []

    for y_lab in y_order:
        row_z = []
        row_text = []

        for x_lab in x_order:
            sub = pdf[(pdf["ClusterX"] == x_lab) & (pdf["ClusterY"] == y_lab)]

            if sub.empty:
                row_z.append(None)
                row_text.append("")
            else:
                row_z.append(float(sub["Jaccard"].iloc[0]))
                row_text.append(str(int(sub["N"].iloc[0])))

        z.append(row_z)
        text.append(row_text)

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=x_order,
            y=y_order,
            text=text,
            texttemplate="%{text}",
            colorscale=[
                [0.0, "white"],
                [1.0, "firebrick"],
            ],
            zmin=0,
            zmax=1,
            colorbar=dict(title="Jaccard"),
            hovertemplate=(
                f"{method_x}: %{{x}}<br>"
                f"{method_y}: %{{y}}<br>"
                "Jaccard: %{z:.3f}<br>"
                "N: %{text}<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        template="plotly_white",
        title=f"Cluster intersection: {method_x} vs {method_y}",
        xaxis_title=method_x,
        yaxis_title=method_y,
        width=max(700, 50 * len(x_order)),
        height=max(700, 50 * len(y_order)),
        showlegend=False,
    )

    fig.update_xaxes(tickangle=90)

    out_file = output_folder / "figures" / "stability" / f"jaccard_matrix_{method_x}_{method_y}.html"
    write_plotly_figure(fig, out_file)


def build_consensus(df_annotated: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    methods = (
        df_annotated
        .select("cl_method")
        .unique()
        .sort("cl_method")
        .to_series()
        .to_list()
    )

    if len(methods) < 2:
        raise ValueError("At least two clustering methods are required for consensus.")

    per_method = []

    for method in methods:
        tmp = (
            df_annotated
            .filter(pl.col("cl_method") == method)
            .select(REQUIRED_ID_COLS + [pl.col("annotation").alias(method)])
            .unique()
        )

        per_method.append(tmp)

    wide = per_method[0]

    for tmp in per_method[1:]:
        wide = wide.join(tmp, on=REQUIRED_ID_COLS, how="inner")

    if wide.height == 0:
        raise ValueError("No overlapping cells across clustering methods.")

    # Group by annotation combination across methods.
    combo_counts = (
        wide
        .group_by(methods)
        .len()
        .rename({"len": "N"})
        .sort("N", descending=True)
    )

    consensus_records = []
    noise_records = []

    for row in combo_counts.iter_rows(named=True):
        annotations = [str(row[m]) for m in methods]

        # Match R behavior: split at "_" and use first token.
        base_names = [a.split("_")[0] for a in annotations]

        counts = {}
        for name in base_names:
            counts[name] = counts.get(name, 0) + 1

        best_name, best_count = sorted(counts.items(), key=lambda x: x[1], reverse=True)[0]
        agreement_fraction = best_count / len(methods)

        out_row = {m: row[m] for m in methods}
        out_row["N"] = int(row["N"])
        out_row["agreement_fraction"] = float(agreement_fraction)

        if agreement_fraction > 0.5:
            out_row["CellType"] = best_name
            consensus_records.append(out_row)
        else:
            out_row["CellType"] = "NOISE"
            noise_records.append(out_row)

    agreements = pl.DataFrame(consensus_records) if consensus_records else pl.DataFrame()
    noise = pl.DataFrame(noise_records) if noise_records else pl.DataFrame()

    if agreements.height == 0:
        consensus_cells = pl.DataFrame(
            schema={
                **{c: pl.Utf8 for c in REQUIRED_ID_COLS},
                "CellType": pl.Utf8,
            }
        )
    else:
        mapping_cols = methods + ["CellType"]

        consensus_cells = (
            wide
            .join(
                agreements.select(mapping_cols),
                on=methods,
                how="inner",
            )
            .select(REQUIRED_ID_COLS + ["CellType"])
        )

    return consensus_cells, agreements, noise

# input_phenograph = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/phenograph.parquet'
# input_kmeans = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/kmeans.parquet'
# input_som = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/som.parquet'
# annotation_dictionary = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01/annotation_dictionary.csv'
# output_folder = '/mnt/check_jon/cell_identification_flow_cytometry/Data/output_cell_identification/n01/v01'

def clustering_stability(
    input_phenograph: str,
    input_kmeans: str,
    input_som: str,
    annotation_dictionary: str,
    output_folder: str,
) -> None:
    print(f"### input phenograph: {input_phenograph} ###")
    print(f"### input kmeans: {input_kmeans} ###")
    print(f"### input som: {input_som} ###")
    print(f"### annotation dictionary: {annotation_dictionary} ###")
    print(f"### output folder: {output_folder} ###")

    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading clustering files")
    df_clusters = load_cluster_tables(input_phenograph=input_phenograph, input_kmeans=input_kmeans, input_som=input_som)

    print("Loading annotation dictionary")
    annotation_df = load_annotation_dictionary(annotation_dictionary)

    print("Mapping annotation dictionary")
    df_annotated = annotate_clusters(df_clusters, annotation_df)

    annotated_path = out_dir / "df_clusters_annotated.parquet"
    write_table(df_annotated, str(annotated_path))

    methods = (
        df_annotated
        .select("cl_method")
        .unique()
        .sort("cl_method")
        .to_series()
        .to_list()
    )

    print(f"Methods detected: {methods}")

    if len(methods) < 2:
        print(
            "Only one clustering method detected. "
            "Skipping stability analysis and using its annotations as consensus."
        )

        consensus_cells = (
            df_annotated
            .select(REQUIRED_ID_COLS + [pl.col("annotation").alias("CellType")])
            .unique()
        )

        write_table(consensus_cells, str(out_dir / "df_data_consensus.parquet"))
        write_table(consensus_cells, str(out_dir / "df_data_consensus.csv"))

        consensus_celltypes = (
            consensus_cells
            .select("CellType")
            .unique()
            .sort("CellType")
        )

        write_table(consensus_celltypes, str(out_dir / "df_consensus_celltypes.csv"))

        print(f"Consensus cells written: {consensus_cells.height}")
        print("Done")

        return

    print("Generating Jaccard matrices")

    all_jaccard = []
    all_best = []

    for method_x, method_y in itertools.combinations(methods, 2):
        print(f"Comparing {method_x} vs {method_y}")

        plot_df, best_df = make_jaccard_matrix(
            df_annotated=df_annotated,
            method_x=method_x,
            method_y=method_y,
        )

        all_jaccard.append(plot_df)

        if best_df.height > 0:
            all_best.append(best_df)

        plot_jaccard_matrix(
            plot_df=plot_df,
            method_x=method_x,
            method_y=method_y,
            output_folder=out_dir,
        )

    # if all_jaccard:
    #     df_jaccard = pl.concat(all_jaccard, how="vertical_relaxed")
    #     write_table(df_jaccard, str(out_dir / "df_jaccard_all.parquet"))
    #     write_table(df_jaccard, str(out_dir / "df_jaccard_all.csv"))
    # 
    # if all_best:
    #     df_best = pl.concat(all_best, how="vertical_relaxed")
    #     write_table(df_best, str(out_dir / "df_jaccard_best_matches.csv"))

    print("Building consensus")

    consensus_cells, agreements, noise = build_consensus(df_annotated)

    print(f"Agreement cells: {consensus_cells.height}")

    if noise.height > 0:
        print(f"Inconsistent combinations: {noise.select(pl.col('N').sum()).item()}")
    else:
        print("Inconsistent combinations: 0")

    write_table(consensus_cells, str(out_dir / "df_data_consensus.parquet"))
    # write_table(consensus_cells, str(out_dir / "df_data_consensus.csv"))

    consensus_celltypes = consensus_cells.select("CellType").unique().sort("CellType")
    write_table(consensus_celltypes, str(out_dir / "df_consensus_celltypes.csv"))

    # if agreements.height > 0:
    #     write_table(agreements, str(out_dir / "df_consensus_agreements.csv"))
    # 
    # if noise.height > 0:
    #     write_table(noise, str(out_dir / "df_consensus_noise.csv"))

    print("Done")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clustering stability and consensus analysis.")

    parser.add_argument(
        "--path.input.phenograph",
        default="not included",
        help="Path to phenograph clustering output csv/parquet.",
    )

    parser.add_argument(
        "--path.input.kmeans",
        default="not included",
        help="Path to kmeans clustering output csv/parquet.",
    )

    parser.add_argument(
        "--path.input.som",
        default="not included",
        help="Path to som clustering output csv/parquet.",
    )

    parser.add_argument(
        "--path.annotation.dictionary",
        required=True,
        help="Path to annotation dictionary csv/parquet.",
    )

    parser.add_argument(
        "--path.output.folder",
        required=True,
        help="Output folder.",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    clustering_stability(
        input_phenograph=getattr(args, "path.input.phenograph"),
        input_kmeans=getattr(args, "path.input.kmeans"),
        input_som=getattr(args, "path.input.som"),
        annotation_dictionary=getattr(args, "path.annotation.dictionary"),
        output_folder=getattr(args, "path.output.folder"),
    )


if __name__ == "__main__":
    main()
