"""The canonical tile manifest.

The manifest is the single source of truth that the rest of the pipeline consumes.
Ingestion adapters (see adapters.py) are responsible for translating
vendor-specific, heterogeneous inputs into this one table. The registration and
stitching code reads ONLY these columns and never parses a filename or a vendor
metadata file itself.

One row per image file (round x scene x tile x channel).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

# Canonical columns. Everything downstream depends on these names and nothing else.
COLUMNS = [
    "sample",          # str  - experiment/sample id (e.g. "BM")
    "slide",           # str  - slide token (e.g. "FR2"); "" when absent (single-slide data)
    "round",           # int  - imaging cycle (R01 -> 1)
    "version",         # str  - acquisition version token (e.g. "V03"); "" when absent
    "scene",           # str  - scene / sample on the slide (e.g. "10")
    "tile",            # int  - mosaic tile index within the scene
    "channel",         # str  - marker channel (e.g. "DAPI")
    "filename",        # str  - basename of the image file
    "path",            # str  - absolute path to the image file
    "stage_x_um",      # float - stage X position, micrometres
    "stage_y_um",      # float - stage Y position, micrometres
    "pixel_size_um",   # float - micrometres per pixel
    "width_px",        # int  - tile width in pixels
    "height_px",       # int  - tile height in pixels
    "is_reference",    # bool - True iff this row IS the resolved reference image
                       #        for its (slide, scene): its (round, version) equals
                       #        the resolved reference (round, version).
]

# Columns the geometric steps strictly require to be present and non-null.
# (slide/version may be the empty string "" for single-slide / single-version
# data; "" is a present value, so they are not listed here.)
REQUIRED_NONNULL = [
    "sample", "round", "scene", "tile", "channel", "path",
    "width_px", "height_px",
]
# Stage positions are required for accurate stitching but may be absent for the
# filename_grid adapter, which synthesises them.
STAGE_COLUMNS = ["stage_x_um", "stage_y_um", "pixel_size_um"]


@dataclass
class ValidationReport:
    ok: bool
    errors: list[str]
    warnings: list[str]
    summary: dict[str, int]

    def render(self) -> str:
        lines = []
        s = self.summary
        lines.append(
            f"Manifest: {s.get('rows', 0)} files | "
            f"{s.get('slides', 0)} slides | "
            f"{s.get('rounds', 0)} rounds | {s.get('scenes', 0)} scenes | "
            f"{s.get('tiles', 0)} tiles | {s.get('channels', 0)} channels"
        )
        for w in self.warnings:
            lines.append(f"  WARNING: {w}")
        for e in self.errors:
            lines.append(f"  ERROR:   {e}")
        lines.append("  -> OK" if self.ok else "  -> NOT OK (fix errors above)")
        return "\n".join(lines)


def empty() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in COLUMNS})


def save(df: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    df.to_csv(path, index=False)


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Manifest {path} is missing columns: {missing}")
    return df


def validate(
    df: pd.DataFrame,
    *,
    require_stage: bool = True,
    register_channel: str = "DAPI",
) -> ValidationReport:
    """Check the manifest is internally consistent before any heavy compute.

    Hard errors are reserved for things that make the manifest unusable (missing
    required fields, missing files, no reference). Structural oddities -- coverage
    gaps, uneven rounds across slides, a version lacking the registration channel,
    single-round groups -- are reported as WARNINGS only: COLLAGE can register
    whenever a (slide, scene) has a reference plus at least one other round/version,
    and can still stitch a lone round/version. The user decides what is right for
    their project.
    """
    errors: list[str] = []
    warnings: list[str] = []

    for col in REQUIRED_NONNULL:
        if df[col].isnull().any():
            n = int(df[col].isnull().sum())
            errors.append(f"{n} row(s) have a missing '{col}'")

    # Files must exist on disk.
    missing_files = [p for p in df["path"] if not os.path.exists(str(p))]
    if missing_files:
        errors.append(f"{len(missing_files)} image file(s) listed in the manifest do not exist on disk")

    # Stage positions.
    stage_missing = df[STAGE_COLUMNS].isnull().any(axis=1).sum()
    if stage_missing:
        msg = f"{int(stage_missing)} row(s) have no stage position (stitching will be less accurate)"
        (errors if require_stage else warnings).append(msg)

    if not df.empty:
        if not (df["is_reference"] == True).any():  # noqa: E712
            errors.append("no rows are marked is_reference=True (check reference_round / reference_version)")

        # Per-(slide, round) tile-set and channel consistency. Grouping by slide
        # keeps these meaningful on multi-slide data; for single-slide data
        # (slide == "") it is identical to the previous per-round behaviour.
        for slide, sdf in df.groupby("slide", dropna=False):
            per_round_tiles = sdf.groupby("round").apply(
                lambda g: set(zip(g["scene"], g["tile"]))
            )
            if len(per_round_tiles) > 1:
                ref_set = per_round_tiles.iloc[0]
                first_round = per_round_tiles.index[0]
                for rnd, tiles in per_round_tiles.items():
                    if tiles != ref_set:
                        where = f"slide {slide} " if slide else ""
                        warnings.append(
                            f"{where}round {rnd} has a different (scene,tile) set than round {first_round}"
                        )
            chans_per_round = sdf.groupby("round")["channel"].apply(lambda s: set(s))
            all_chans = set().union(*chans_per_round) if len(chans_per_round) else set()
            for rnd, chans in chans_per_round.items():
                if chans != all_chans:
                    where = f"slide {slide} " if slide else ""
                    warnings.append(f"{where}round {rnd} is missing channels: {sorted(all_chans - chans)}")

        # New structural QC (all advisory).
        warnings.extend(_qc_structure(df, register_channel))

    summary = {
        "rows": len(df),
        "slides": df["slide"].nunique() if not df.empty else 0,
        "rounds": df["round"].nunique() if not df.empty else 0,
        "scenes": df["scene"].nunique() if not df.empty else 0,
        "tiles": df[["scene", "tile"]].drop_duplicates().shape[0] if not df.empty else 0,
        "channels": df["channel"].nunique() if not df.empty else 0,
    }
    return ValidationReport(ok=not errors, errors=errors, warnings=warnings, summary=summary)


def _rnd_token(r) -> str:
    try:
        return f"R{int(r):02d}"
    except (ValueError, TypeError):
        return f"R{r}"


def _qc_structure(df: pd.DataFrame, register_channel: str) -> list[str]:
    """Advisory structural checks on the assembled manifest. Returns a list of
    aggregated warning strings (empty when nothing is odd). Never errors.

    Checks:
      1. Scenes of the same slide that are missing a round other scenes have.
      2. Slides with differing numbers of distinct rounds.
      3. (slide, scene, round, version) groups lacking the registration channel.
      4. (slide, scene) groups with only a single round/version (stitch-only).
    """
    out: list[str] = []

    # 1. Per-slide round-coverage gaps across scenes.
    gap_msgs: list[str] = []
    for slide, sdf in df.groupby("slide", dropna=False):
        expected = set(sdf["round"].unique())
        for scene, scdf in sdf.groupby("scene", dropna=False):
            missing = expected - set(scdf["round"].unique())
            if missing:
                toks = ", ".join(_rnd_token(r) for r in sorted(missing))
                label = f"{slide}/" if slide else ""
                gap_msgs.append(f"{label}{scene} missing {toks}")
    if gap_msgs:
        out.append(
            f"{len(gap_msgs)} (slide,scene) group(s) have round-coverage gaps vs. "
            f"other scenes of the same slide: " + "; ".join(gap_msgs)
        )

    # 2. Slides with differing distinct-round counts.
    if df["slide"].nunique() > 1:
        counts = df.groupby("slide")["round"].nunique()
        if counts.nunique() > 1:
            tally = ", ".join(f"{s}={int(c)}" for s, c in counts.sort_index().items())
            out.append(f"slides have differing round counts: {tally}")

    # 3. Versions lacking the registration channel.
    no_ref_chan: list[str] = []
    for (slide, scene, rnd, ver), g in df.groupby(["slide", "scene", "round", "version"], dropna=False):
        if register_channel not in set(g["channel"]):
            label = f"{slide}/" if slide else ""
            no_ref_chan.append(f"{label}{scene}/{_rnd_token(rnd)}/{ver or '-'}")
    if no_ref_chan:
        shown = "; ".join(no_ref_chan[:8])
        more = f" (+{len(no_ref_chan) - 8} more)" if len(no_ref_chan) > 8 else ""
        out.append(
            f"{len(no_ref_chan)} (slide,scene,round,version) group(s) lack the "
            f"registration channel '{register_channel}' and cannot be registered "
            f"(other channels, if any, can still be carried): {shown}{more}"
        )

    # 4. Single round/version (slide, scene): stitch-only, nothing to register to.
    single: list[str] = []
    for (slide, scene), g in df.groupby(["slide", "scene"], dropna=False):
        n_rv = g[["round", "version"]].drop_duplicates().shape[0]
        if n_rv <= 1:
            label = f"{slide}/" if slide else ""
            single.append(f"{label}{scene}")
    if single:
        out.append(
            f"{len(single)} (slide,scene) group(s) have only one round/version "
            f"(can stitch, but nothing to register against): " + "; ".join(single)
        )

    return out
