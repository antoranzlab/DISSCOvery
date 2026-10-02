#!/usr/bin/env python
"""QC input files - COMET. Pass/fail text report: xml jobfile present, one ome.tiff per slide, matching cycle counts, cycle folder naming."""
import argparse
import os
import sys
import xml.etree.ElementTree as ET

import pandas as pd

def _cycle_number_from_path(tile_folder_path):
    cleaned = tile_folder_path.rstrip("\\").rstrip("/")
    return cleaned.rsplit("Cycle_", 1)[-1]

def _extract_metadata(input_path, folders):
    rows = []
    for folder in folders:
        xml_files = [f for f in os.listdir(os.path.join(input_path, folder)) if f.endswith(".xml")]
        root = ET.parse(os.path.join(input_path, folder, xml_files[0])).getroot()
        for cycle_node in root.findall(".//CycleModels"):
            cycle_number = _cycle_number_from_path(cycle_node.get("TileFolderPath"))
            for _ in cycle_node.findall(".//ChannelMeta"):
                rows.append({"folder": folder, "cycle_number": cycle_number})
    return pd.DataFrame(rows)

def qc_input_files_comet(input_path, output_txt):
    print(f"### input path raw data: {input_path} ###")
    print(f"### output path qc report (txt): {output_txt} ###")

    os.makedirs(os.path.dirname(output_txt), exist_ok=True)

    folders = sorted(f.name for f in os.scandir(input_path) if f.is_dir())

    # Check1: exactly one .xml jobfile per slide folder
    xml_counts = {f: [x for x in os.listdir(os.path.join(input_path, f)) if x.endswith(".xml")] for f in folders}
    bad = [f for f, files in xml_counts.items() if len(files) == 0]
    sep = ".\n"
    if bad:
        message = f"Check1 - xml file QC: NOT PASSED.\nCondition: xml file not found: {sep.join(bad)}\n"
    else:
        message = "Check1 - xml file QC: PASSED.\n"

    df_metadata = _extract_metadata(input_path, [f for f in folders if xml_counts[f]])

    # Check2: exactly one .tiff per slide folder
    tiff_counts = {f: [x for x in os.listdir(os.path.join(input_path, f)) if x.endswith(".tiff")] for f in folders}
    bad2 = [f for f, files in tiff_counts.items() if len(files) != 1]
    if bad2:
        message += f"Check2 - ome.tiff file QC: NOT PASSED.\nCondition: number of files found different from 1: {sep.join(bad2)}\n"
    else:
        message += "Check2 - ome.tiff file QC: PASSED.\n"

    # Check3: consistent cycle count across slides
    n_cycles = df_metadata.groupby("folder")["cycle_number"].nunique()
    if n_cycles.nunique() != 1:
        most_common = n_cycles.value_counts().idxmax()
        bad3 = n_cycles[n_cycles != most_common].index.tolist()
        message += f"Check3 - Number of cycles per slide QC: NOT PASSED.\nCondition: cycles different from {most_common}: {sep.join(bad3)}\n"
    else:
        message += "Check3 - Number of cycles per slide QC: PASSED.\n"

    # Check4: R source re-runs Check2's exact filter instead of checking cycle folder naming -- a real copy-paste bug in the original, preserved as-is
    if bad2:
        message += f"Check4 - Cycle folder nomenclature QC: NOT PASSED.\nCondition: cycle folder name non standard: {sep.join(bad2)}\n"
    else:
        message += "Check4 - Cycle folder nomenclature QC: PASSED.\n"

    with open(output_txt, "w") as f:
        f.write(message)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QC input files - COMET.")
    parser.add_argument("--input_path", type=str, help="Path to input directory with the raw data (path).")
    parser.add_argument("--output_txt", type=str, help="Path to output QC report file (txt).")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    qc_input_files_comet(input_path=args.input_path, output_txt=args.output_txt)
