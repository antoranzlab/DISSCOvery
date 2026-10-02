import argparse
import os
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go

def calculate_iou_matrix(ref_boxes, query_boxes):
    """Pairwise IoU between every reference box and every query box."""
    minr_ref, minc_ref, maxr_ref, maxc_ref = (ref_boxes[c].to_numpy()[:, None] for c in ("minr", "minc", "maxr", "maxc"))
    minr_query, minc_query, maxr_query, maxc_query = (
        query_boxes[c].to_numpy()[None, :] for c in ("minr", "minc", "maxr", "maxc")
    )

    intersect_width = np.maximum(0, np.minimum(maxr_ref, maxr_query) - np.maximum(minr_ref, minr_query))
    intersect_height = np.maximum(0, np.minimum(maxc_ref, maxc_query) - np.maximum(minc_ref, minc_query))
    intersection_area = intersect_width * intersect_height

    area_ref = (maxr_ref - minr_ref) * (maxc_ref - minc_ref)
    area_query = (maxr_query - minr_query) * (maxc_query - minc_query)
    union_area = area_ref + area_query - intersection_area

    return intersection_area / union_area

def evaluate_concordance(input_path_BB, output_heatmap_path_html, output_heatmap_path_json, reference_round, reference_version):
    """Compute per-region IoU between the reference round and every other round/version, save an interactive heatmap."""
    print(f"### input path bounding boxes: {input_path_BB} ###")
    print(f"### output heatmap path (html): {output_heatmap_path_html} ###")
    print(f"### output heatmap path (json): {output_heatmap_path_json} ###")
    print(f"### reference round: {reference_round} ###")
    print(f"### reference version: {reference_version} ###")

    os.makedirs(os.path.dirname(output_heatmap_path_html), exist_ok=True)
    os.makedirs(os.path.dirname(output_heatmap_path_json), exist_ok=True)

    files = sorted(f for f in os.listdir(input_path_BB) if f.endswith(".csv"))
    df_files = pd.DataFrame({"ofile": files})
    df_files[["slide_id", "round_id", "version_id", "project_id", "user_id", "channel_id"]] = (
        df_files["ofile"].str.replace(".csv", "", regex=False).str.split("_", expand=True)
    )

    ref_file = df_files[(df_files["round_id"] == reference_round) & (df_files["version_id"] == reference_version)]
    if len(ref_file) != 1:
        raise ValueError("reference not found.")
    ref_file = ref_file.iloc[0]

    query_files = df_files[df_files["ofile"] != ref_file["ofile"]]
    if len(query_files) < 1:
        raise ValueError("no query files.")

    ref_objects = pd.read_csv(os.path.join(input_path_BB, ref_file["ofile"]))

    rows = []
    for _, query_file in query_files.iterrows():
        query_objects = pd.read_csv(os.path.join(input_path_BB, query_file["ofile"]))
        iou_matrix = calculate_iou_matrix(ref_objects, query_objects)
        tmp_df_iou = pd.DataFrame(iou_matrix, index=ref_objects["scan_region"], columns=query_objects["scan_region"])
        tmp_df_iou = tmp_df_iou.stack().rename("IoU").rename_axis(["Sref", "Squery"]).reset_index()
        tmp_df_iou["ofile"] = query_file["ofile"]
        rows.append(tmp_df_iou)

    contingency_matrix = pd.concat(rows, ignore_index=True)

    # for each reference object, keep every query match tied for the best IoU
    best_match = contingency_matrix[
        contingency_matrix["IoU"] == contingency_matrix.groupby(["ofile", "Sref"])["IoU"].transform("max")
    ].copy()
    best_match["ofile"] = best_match["ofile"].str.replace(".csv", "", regex=False)
    best_match["S"] = best_match["Sref"].str.replace("S", "", regex=False).astype(int)
    best_match = best_match.sort_values("S")
    sref_order = best_match["Sref"].drop_duplicates().tolist()
    best_match = best_match.drop(columns="S")

    fig = go.Figure(
        data=go.Heatmap(
            x=best_match["Sref"],
            y=best_match["ofile"],
            z=best_match["IoU"],
            colorscale=[[0, "white"], [1, "indianred"]],
            text=[f"Squery: {s} <br>IoU: {iou}" for s, iou in zip(best_match["Squery"], best_match["IoU"])],
            hoverinfo="text",
        )
    )
    fig.update_layout(
        xaxis=dict(title="", categoryorder="array", categoryarray=sref_order),
        yaxis=dict(title=""),
        hoverlabel=dict(bgcolor="white"),
    )

    fig.write_html(output_heatmap_path_html)
    fig.write_json(output_heatmap_path_json.replace(".html", ".json"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate concordance between bounding boxes belonging to the same slide.")
    parser.add_argument("--input_path_BB", type=str, help="Path to input directory with the bounding boxes (path).")
    parser.add_argument("--output_heatmap_path_html", type=str, help="Path to output path where the html plot will be saved (html).")
    parser.add_argument("--output_heatmap_path_json", type=str, help="Path to output path where the json plot will be saved (json).")
    parser.add_argument("--reference_round", type=str, help="Identifier for the round used as reference.")
    parser.add_argument("--reference_version", type=str, help="Identifier for the version used as reference.")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    evaluate_concordance(
        input_path_BB=args.input_path_BB,
        output_heatmap_path_html=args.output_heatmap_path_html,
        output_heatmap_path_json=args.output_heatmap_path_json,
        reference_round=args.reference_round,
        reference_version=args.reference_version,
    )
