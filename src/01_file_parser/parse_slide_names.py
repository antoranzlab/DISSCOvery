#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import re
import pandas as pd
import unicodedata

def normalize_folder(x):
    if pd.isna(x):
        return None
    x = str(x)
    x = unicodedata.normalize("NFKC", x)
    x = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", x)   # dash variants
    x = re.sub(r"[\u00A0\u2000-\u200B\u202F\u205F\u3000]", " ", x)       # weird spaces
    x = re.sub(r"\s+", " ", x).strip()
    return x
  

def parse_slide_names(path_input_exp_design_rounds, path_input_exp_design_slides, path_output_exp_design_merged):
    path_input_exp_design_rounds = Path(path_input_exp_design_rounds)
    path_input_exp_design_slides = Path(path_input_exp_design_slides)
    path_output_exp_design_merged = Path(path_output_exp_design_merged)

    print(f"### path exp design rounds: {path_input_exp_design_rounds} ###")
    print(f"### path exp design slides: {path_input_exp_design_slides} ###")
    print(f"### path exp design merged: {path_output_exp_design_merged} ###")

    if not path_output_exp_design_merged.parent.exists():
        print(f"### creating folder: {path_output_exp_design_merged.parent} ###")
        path_output_exp_design_merged.parent.mkdir(parents=True, exist_ok=True)

    # Read files
    print("Reading files")

    tmp_exp_design_rounds = pd.read_csv(path_input_exp_design_rounds, sep=",")
    tmp_exp_design_slides = pd.read_csv(path_input_exp_design_slides, sep=",")

    if "folder" not in tmp_exp_design_rounds.columns:
        raise ValueError("Column 'folder' not found in exp_design_rounds CSV")
    if "folder" not in tmp_exp_design_slides.columns:
        raise ValueError("Column 'folder' not found in exp_design_slides CSV")

    tmp_exp_design_rounds["folder"] = tmp_exp_design_rounds["folder"].map(lambda x: normalize_folder(str(x)))
    tmp_exp_design_slides["folder"] = tmp_exp_design_slides["folder"].map(lambda x: normalize_folder(str(x)))

    # Merge files
    print("Merging files")

    common_cols = list(set(tmp_exp_design_rounds.columns).intersection(set(tmp_exp_design_slides.columns)))
    
    if not common_cols:
        raise ValueError("No common columns found between rounds and slides tables for merging")

    tmp_exp_design_merged = tmp_exp_design_rounds.merge(
        tmp_exp_design_slides,
        how="left",
        on=common_cols,
    )

    if "folder" in tmp_exp_design_merged.columns:
        tmp_exp_design_merged = tmp_exp_design_merged.drop(columns=["folder"])

    # Generate csv
    print("Creating csv file")
    tmp_exp_design_merged.to_csv(path_output_exp_design_merged, index=False)

def main() -> None:
    parser = argparse.ArgumentParser(description="Parse slide names to exp design rounds.")

    parser.add_argument(
        "--path_input_exp_design_rounds",
        required=True,
        help="Path to the exp design rounds (csv).",
    )
    parser.add_argument(
        "--path_input_exp_design_slides",
        required=True,
        help="Path to the exp design slides (csv).",
    )
    parser.add_argument(
        "--path_output_exp_design_merged",
        required=True,
        help="Path to the exp design merged (csv).",
    )

    args = parser.parse_args()

    parse_slide_names(
        path_input_exp_design_rounds=args.path_input_exp_design_rounds,
        path_input_exp_design_slides=args.path_input_exp_design_slides,
        path_output_exp_design_merged=args.path_output_exp_design_merged,
    )


if __name__ == "__main__":
    main()
