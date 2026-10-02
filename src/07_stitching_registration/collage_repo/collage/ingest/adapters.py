"""Ingestion adapters.

Each adapter knows how to read one *kind* of input layout and emit rows in the
canonical manifest schema (see manifest.py). Adding support for a new scanner
means adding an adapter here -- the pipeline core never changes.

An adapter implements:
    name: str
    detect(round_dir) -> bool          # can I handle this round folder?
    tiles(round_dir, ctx) -> list[dict] # canonical rows for this folder

`ctx` carries config-derived options (reference round, column map, overlap, ...).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from . import manifest

# A round folder is recognised by an R<NN> token in its name.
_ROUND_RE = re.compile(r"(?:^|_)R(\d+)(?:_|$|[A-Za-z])")
_SCENE_TILE_RE = re.compile(r"S(\d+)M(\d+)")
# Acquisition version (V<nn>) token, when present in the round-folder name.
# Optional: single-version datasets (e.g. the benchmark) yield "" and the
# version dimension collapses to a no-op.
_VERSION_RE = re.compile(r"(?:^|_)V(\d+)(?:_|$|[A-Za-z])")


@dataclass
class IngestContext:
    reference_round: int = 1
    column_map: dict[str, str] = field(default_factory=dict)
    overlap: float = 0.1
    reference_version: str | None = None
    reference_overrides: list[dict[str, Any]] = field(default_factory=list)


def _round_of(name: str) -> int | None:
    m = _ROUND_RE.search(name)
    return int(m.group(1)) if m else None


def _slide_of(folder_name: str) -> str:
    """Slide token from a round-folder name: everything before the round token.

    Matches the canonical <slide>_<round>_<version>_<project>_<user>_<scene>
    folder convention, e.g. 'MVM001_R01_V01_MVM_MVM_S1M' -> 'MVM001'. This is
    also what step2/3/4's own independent slide parsing already does
    (_parse_srv / get_R_S_M_C), so the manifest's slide column agrees with the
    steps' internal grouping. A dataset with no distinct per-slide prefix (e.g.
    the single-slide benchmark 'BM_R01_V02_BENCHMARK_ND_S10M') just yields a
    constant non-empty token ('BM') -- still a single group, so reference
    resolution is unaffected. Single-slide data with no round token at all
    (shouldn't happen -- round is required) yields "".
    """
    rm = _ROUND_RE.search(folder_name)
    return folder_name[:rm.start()].rstrip("_") if rm else ""


def _version_of(folder_name: str) -> str:
    """Version token from a round-folder name: '..._V03_...' -> 'V03'. "" if none."""
    m = _VERSION_RE.search(folder_name)
    return f"V{int(m.group(1)):02d}" if m else ""


def _sample_of(filename: str) -> str:
    return filename.split("_")[0]


def _channel_of(filename: str) -> str:
    stem = re.sub(r"\.tiff?$", "", filename, flags=re.IGNORECASE)
    return stem.split("_")[-1]


def _scene_tile_of(filename: str) -> tuple[str | None, int | None]:
    m = _SCENE_TILE_RE.search(filename)
    if m:
        return m.group(1), int(m.group(2))
    return None, None


def _list_tiffs(round_dir: str) -> list[str]:
    return [f for f in os.listdir(round_dir) if re.search(r"\.tiff?$", f, re.IGNORECASE)]


def _find_csv(round_dir: str) -> str | None:
    csvs = [f for f in os.listdir(round_dir) if f.lower().endswith(".csv")]
    return os.path.join(round_dir, csvs[0]) if len(csvs) == 1 else None


# ---------------------------------------------------------------------------
# Zeiss Axioscan
# ---------------------------------------------------------------------------
class ZeissAdapter:
    name = "zeiss"
    # Columns that identify a Zeiss Axioscan metadata CSV.
    _SIGNATURE = {"StageXPosition", "StageYPosition", "Frame", "ImagePixelSize", "tile_filename"}

    def detect(self, round_dir: str) -> bool:
        csv = _find_csv(round_dir)
        if not csv:
            return False
        try:
            cols = set(pd.read_csv(csv, nrows=0).columns)
        except Exception:
            return False
        return self._SIGNATURE.issubset(cols)

    def tiles(self, round_dir: str, ctx: IngestContext) -> list[dict[str, Any]]:
        csv = _find_csv(round_dir)
        df = pd.read_csv(csv)
        folder = os.path.basename(round_dir)
        rnd = _round_of(folder) or _round_of(str(df["tile_filename"].iloc[0]))
        slide = _slide_of(folder)
        version = _version_of(folder)
        rows: list[dict[str, Any]] = []
        for _, r in df.iterrows():
            fname = str(r["tile_filename"])
            path = os.path.join(round_dir, fname)
            pixel_size = _first_float(r["ImagePixelSize"])
            width, height = _frame_wh(r["Frame"])
            scene = str(r["S"]) if "S" in df.columns and not pd.isna(r.get("S")) else _scene_tile_of(fname)[0]
            tile = int(r["M"]) if "M" in df.columns and not pd.isna(r.get("M")) else _scene_tile_of(fname)[1]
            rows.append({
                "sample": _sample_of(fname),
                "slide": slide,
                "round": rnd,
                "version": version,
                "scene": scene,
                "tile": tile,
                "channel": _channel_of(fname),
                "filename": fname,
                "path": path,
                "stage_x_um": _to_float(r["StageXPosition"]),
                "stage_y_um": _to_float(r["StageYPosition"]),
                "pixel_size_um": pixel_size,
                "width_px": width,
                "height_px": height,
                "is_reference": rnd == ctx.reference_round,
            })
        return rows


# ---------------------------------------------------------------------------
# Generic CSV (user declares the column mapping in config)
# ---------------------------------------------------------------------------
class GenericCsvAdapter:
    """For any CSV-with-stage-positions layout. The user supplies a column map:

        input:
          adapter: generic_csv
          column_map:
            tile_filename: file
            stage_x: pos_x
            stage_y: pos_y
            pixel_size: um_per_px
            width: w
            height: h
    """
    name = "generic_csv"

    def detect(self, round_dir: str) -> bool:
        return _find_csv(round_dir) is not None

    def tiles(self, round_dir: str, ctx: IngestContext) -> list[dict[str, Any]]:
        cmap = ctx.column_map
        if not cmap:
            raise ValueError(
                "adapter 'generic_csv' requires input.column_map in the config "
                "(see GenericCsvAdapter docstring)."
            )
        csv = _find_csv(round_dir)
        df = pd.read_csv(csv)
        folder = os.path.basename(round_dir)
        rnd = _round_of(folder)
        slide = _slide_of(folder)
        version = _version_of(folder)
        rows: list[dict[str, Any]] = []
        for _, r in df.iterrows():
            fname = str(r[cmap["tile_filename"]])
            scene, tile = _scene_tile_of(fname)
            rows.append({
                "sample": _sample_of(fname),
                "slide": slide,
                "round": rnd,
                "version": version,
                "scene": scene,
                "tile": tile,
                "channel": _channel_of(fname),
                "filename": fname,
                "path": os.path.join(round_dir, fname),
                "stage_x_um": _to_float(r[cmap["stage_x"]]) if "stage_x" in cmap else None,
                "stage_y_um": _to_float(r[cmap["stage_y"]]) if "stage_y" in cmap else None,
                "pixel_size_um": _to_float(r[cmap["pixel_size"]]) if "pixel_size" in cmap else None,
                "width_px": int(r[cmap["width"]]) if "width" in cmap else None,
                "height_px": int(r[cmap["height"]]) if "height" in cmap else None,
                "is_reference": rnd == ctx.reference_round,
            })
        return rows


# ---------------------------------------------------------------------------
# Filename grid (no stage metadata at all)
# ---------------------------------------------------------------------------
class FilenameGridAdapter:
    """Last-resort adapter for data with NO stage metadata. Tile dimensions are
    read from the images; stage positions are left empty and a grid is inferred
    later from the filename tile index + the configured overlap. Less accurate
    than real stage positions -- this is a degraded mode."""
    name = "filename_grid"

    def detect(self, round_dir: str) -> bool:
        return len(_list_tiffs(round_dir)) > 0

    def tiles(self, round_dir: str, ctx: IngestContext) -> list[dict[str, Any]]:
        import tifffile
        folder = os.path.basename(round_dir)
        rnd = _round_of(folder)
        slide = _slide_of(folder)
        version = _version_of(folder)
        rows: list[dict[str, Any]] = []
        for fname in _list_tiffs(round_dir):
            scene, tile = _scene_tile_of(fname)
            path = os.path.join(round_dir, fname)
            try:
                shape = tifffile.TiffFile(path).pages[0].shape
                h, w = int(shape[0]), int(shape[1])
            except Exception:
                h = w = None
            rows.append({
                "sample": _sample_of(fname),
                "slide": slide,
                "round": rnd,
                "version": version,
                "scene": scene,
                "tile": tile,
                "channel": _channel_of(fname),
                "filename": fname,
                "path": path,
                "stage_x_um": None,
                "stage_y_um": None,
                "pixel_size_um": None,
                "width_px": w,
                "height_px": h,
                "is_reference": rnd == ctx.reference_round,
            })
        return rows


_ADAPTERS = {
    a.name: a for a in (ZeissAdapter(), GenericCsvAdapter(), FilenameGridAdapter())
}
# Order matters for auto-detect: most specific first.
_AUTO_ORDER = ["zeiss", "generic_csv", "filename_grid"]


def get_adapter(name: str):
    if name == "auto":
        return None  # resolved per-folder in build_manifest
    if name not in _ADAPTERS:
        raise ValueError(f"unknown adapter '{name}'. Available: {sorted(_ADAPTERS)} or 'auto'.")
    return _ADAPTERS[name]


def _auto_detect(round_dir: str, ctx: IngestContext):
    for name in _AUTO_ORDER:
        ad = _ADAPTERS[name]
        # generic_csv only auto-selects if a column_map was provided.
        if name == "generic_csv" and not ctx.column_map:
            continue
        if ad.detect(round_dir):
            return ad
    return None


def discover_round_dirs(input_dir: str) -> list[str]:
    """Find round folders (those whose name carries an R<NN> token).

    Handles both layouts seen in the wild: rounds directly under input_dir, or
    nested inside an `output_FFC_corrected/` subfolder.
    """
    candidates = [input_dir]
    ffc = os.path.join(input_dir, "output_FFC_corrected")
    if os.path.isdir(ffc):
        candidates.insert(0, ffc)
    for base in candidates:
        dirs = [
            os.path.join(base, d) for d in sorted(os.listdir(base))
            if os.path.isdir(os.path.join(base, d)) and _round_of(d) is not None
        ]
        if dirs:
            return dirs
    return []


def _is_empty_round_dir(round_dir: str) -> bool:
    """A round folder with no images (and no metadata CSV) to ingest. Empty
    folders should not exist by design, but digest must tolerate them rather
    than crash on the first one."""
    if _list_tiffs(round_dir):
        return False
    if any(f.lower().endswith(".csv") for f in os.listdir(round_dir)):
        return False
    return True


def build_manifest(input_dir: str, adapter_name: str, ctx: IngestContext) -> pd.DataFrame:
    """Scan input_dir, pick adapter(s), and assemble the canonical manifest.

    Empty round folders are skipped with a warning. After rows are assembled,
    the per-(slide, scene) reference is resolved and validated, and the
    `is_reference` column is set authoritatively (see reference.py).
    """
    from . import reference

    round_dirs = discover_round_dirs(input_dir)
    if not round_dirs:
        raise FileNotFoundError(
            f"No round folders (named with an R<NN> token) found under {input_dir}."
        )

    forced = get_adapter(adapter_name)
    all_rows: list[dict] = []
    skipped: list[str] = []
    for rd in round_dirs:
        if _is_empty_round_dir(rd):
            skipped.append(os.path.basename(rd))
            continue
        ad = forced or _auto_detect(rd, ctx)
        if ad is None:
            raise ValueError(f"Could not auto-detect an input adapter for {rd}.")
        all_rows.extend(ad.tiles(rd, ctx))

    for name in skipped:
        print(f"  WARNING: skipping empty round folder (no images): {name}")

    if not all_rows:
        raise FileNotFoundError(
            f"No images found in any round folder under {input_dir} "
            f"({len(skipped)} folder(s) were empty)."
        )

    df = pd.DataFrame(all_rows, columns=manifest.COLUMNS)
    # Stable, human-friendly ordering. NOTE: keep this key as-is (do not prepend
    # slide/version) so single-slide/single-version data keeps byte-identical
    # row order vs. the pre-version pipeline.
    df = df.sort_values(["round", "scene", "tile", "channel"]).reset_index(drop=True)

    # Resolve + validate the reference per (slide, scene), then mark is_reference.
    resolved = reference.resolve_references(
        df,
        reference_round=ctx.reference_round,
        reference_version=ctx.reference_version,
        overrides=ctx.reference_overrides,
    )
    df = reference.apply_is_reference(df, resolved)
    return df


# --- small parsing helpers ---------------------------------------------------
def _to_float(v) -> float | None:
    try:
        return float(str(v).replace(",", ".")) if not pd.isna(v) else None
    except (ValueError, TypeError):
        return None


def _first_float(v) -> float | None:
    """ImagePixelSize is like '6.52,6.52' (x,y). Take the first value."""
    s = str(v)
    first = s.split(",")[0] if "," in s else s
    try:
        return float(first)
    except ValueError:
        return None


def _frame_wh(v) -> tuple[int | None, int | None]:
    """Frame is like '4,4,2040,2040' (x, y, width, height)."""
    parts = str(v).split(",")
    if len(parts) >= 4:
        try:
            return int(parts[2]), int(parts[3])
        except ValueError:
            pass
    return None, None
