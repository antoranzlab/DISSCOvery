"""Shared CZI metadata helpers, built on czifile."""

from pathlib import Path

import czifile
import pandas as pd

def find_czi_files(directory):
    """Find all .czi files within a directory and its subdirectories."""
    return sorted(str(path) for path in Path(directory).rglob("*.czi"))

def read_channel_table(czi_file):
    """Return a channel_number -> channel_id table for a single CZI file."""
    czi = czifile.CziFile(czi_file)
    channels = czi.metadata(asdict=True)["ImageDocument"]["Metadata"]["Information"]["Image"]["Dimensions"]["Channels"]["Channel"]
    if not isinstance(channels, list):
        channels = [channels]
    czi.close()
    return pd.DataFrame(
        {
            "channel_id": [c["Name"] for c in channels],
            "channel_number": range(len(channels)),
            "czi_file": czi_file,
        }
    )

def read_channel_tables(czi_files, verbose=True):
    """Read and concatenate channel tables for a list of CZI files."""
    tables = []
    for index, czi_file in enumerate(czi_files):
        if verbose:
            print(f"{index + 1} out of {len(czi_files)}")
        tables.append(read_channel_table(czi_file))
    if not tables:
        return pd.DataFrame(columns=["channel_id", "channel_number", "czi_file"])
    return pd.concat(tables, ignore_index=True)
