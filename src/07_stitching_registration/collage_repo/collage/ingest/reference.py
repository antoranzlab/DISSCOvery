"""Per-(slide, scene) reference resolution.

The reference is ONE image per (slide, scene) -- a single (round, version) --
that every other (round, version) of that (slide, scene) registers to.

Resolution rule (see docs/design_version_aware_ingestion.md):
  - global default `reference_round` (+ optional `reference_version`),
  - optional sparse per-(slide, scene) overrides,
  - reference VERSION auto-selects when a round has exactly one version present;
    if multiple versions exist and none was specified -> loud error,
  - the resolved (round, version) must exist in the data -> else loud error
    listing what IS available. Never silently substitute a different version.

This module is pure (operates on a manifest DataFrame); no I/O, no TF, so it is
cheap to unit-test.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd


class ReferenceError(ValueError):
    """Raised when a (slide, scene)'s reference cannot be resolved/validated."""


def norm_round(v: Any) -> int:
    """Normalise a round token to its integer value. Accepts int (1), or
    string tokens 'R01' / 'r1' / '01' / '1'. Padding and case are irrelevant."""
    if isinstance(v, bool):  # guard: bool is an int subclass
        raise ReferenceError(f"invalid round token: {v!r}")
    if isinstance(v, int):
        return v
    s = str(v).strip()
    m = re.fullmatch(r"[Rr]?0*(\d+)", s)
    if not m:
        raise ReferenceError(f"invalid round token: {v!r} (expected e.g. 'R01' or 1)")
    return int(m.group(1))


def norm_version(v: Any) -> str | None:
    """Normalise a version token to canonical 'V<NN>' (zero-padded to 2), or
    None if not given. Accepts 'V01' / 'v1' / '01' / '1' / 1. Empty/None -> None.

    The empty-string sentinel (data with no V token at all) normalises to "" so
    it can still match a manifest whose version column is "".
    """
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return ""
    if isinstance(v, bool):
        raise ReferenceError(f"invalid version token: {v!r}")
    if isinstance(v, int):
        return f"V{v:02d}"
    s = str(v).strip()
    m = re.fullmatch(r"[Vv]?0*(\d+)", s)
    if not m:
        raise ReferenceError(f"invalid version token: {v!r} (expected e.g. 'V01')")
    return f"V{int(m.group(1)):02d}"


def _canon_version_token(tok: Any) -> str:
    """Canonicalise a manifest version cell ('V03', '', 'V3') -> 'V03' or ''."""
    nv = norm_version(tok)
    return "" if nv is None else nv


def resolve_references(
    df: pd.DataFrame,
    *,
    reference_round: Any,
    reference_version: Any = None,
    overrides: list[dict[str, Any]] | None = None,
) -> dict[tuple[str, str], tuple[int, str]]:
    """Resolve, per (slide, scene), the concrete reference (round_int, version).

    Returns {(slide, scene): (round_int, canonical_version)}.
    Raises ReferenceError on ambiguity, a missing reference round/version, or a
    malformed override.
    """
    default_round = norm_round(reference_round)
    default_version = norm_version(reference_version)  # may be None

    # Index overrides by (slide, scene), validating as we go.
    ov_index: dict[tuple[str, str], dict[str, Any]] = {}
    for i, ov in enumerate(overrides or []):
        if not isinstance(ov, dict) or "slide" not in ov or "scene" not in ov:
            raise ReferenceError(
                f"reference_overrides[{i}] must specify at least 'slide' and 'scene' "
                f"(got {ov!r})"
            )
        key = (str(ov["slide"]), str(ov["scene"]))
        if key in ov_index:
            raise ReferenceError(
                f"duplicate reference_overrides entry for slide={key[0]} scene={key[1]}"
            )
        ov_index[key] = ov

    # Pre-compute, per (slide, scene), the set of versions present in each round.
    # versions_by[(slide, scene)][round_int] = sorted list of canonical versions
    versions_by: dict[tuple[str, str], dict[int, list[str]]] = {}
    work = df.copy()
    work["_v"] = work["version"].map(_canon_version_token)
    for (slide, scene), g in work.groupby(["slide", "scene"], dropna=False):
        slide_s, scene_s = str(slide), str(scene)
        per_round: dict[int, set[str]] = {}
        for rnd, gg in g.groupby("round"):
            per_round[int(rnd)] = set(gg["_v"].tolist())
        versions_by[(slide_s, scene_s)] = {r: sorted(vs) for r, vs in per_round.items()}

    resolved: dict[tuple[str, str], tuple[int, str]] = {}
    used_overrides: set[tuple[str, str]] = set()
    for key, rounds in versions_by.items():
        slide_s, scene_s = key
        ov = ov_index.get(key, {})
        if ov:
            used_overrides.add(key)
        rr = norm_round(ov.get("round", default_round))
        rv_raw = ov.get("version", default_version)
        rv = norm_version(rv_raw) if rv_raw is not None else None

        present = rounds.get(rr)
        if not present:
            avail = ", ".join(f"R{r:02d}" for r in sorted(rounds)) or "(none)"
            raise ReferenceError(
                f"reference round R{rr:02d} not found for slide={slide_s} "
                f"scene={scene_s}; available rounds: {avail}"
            )

        if rv is None:
            if len(present) == 1:
                rv = present[0]
            else:
                raise ReferenceError(
                    f"ambiguous reference version for slide={slide_s} scene={scene_s} "
                    f"round R{rr:02d}: versions {present} present. Set reference_version "
                    f"(or a reference_overrides entry) to choose one."
                )
        elif rv not in present:
            raise ReferenceError(
                f"reference version {rv} not found for slide={slide_s} scene={scene_s} "
                f"round R{rr:02d}; available versions: {present}"
            )

        resolved[key] = (rr, rv)

    # Surface overrides that matched no (slide, scene) -- usually a typo.
    unused = set(ov_index) - used_overrides
    if unused:
        pretty = ", ".join(f"slide={s} scene={sc}" for s, sc in sorted(unused))
        raise ReferenceError(
            f"reference_overrides entries matched no data: {pretty}. "
            f"Check the slide/scene tokens against the manifest."
        )

    return resolved


def apply_is_reference(
    df: pd.DataFrame,
    resolved: dict[tuple[str, str], tuple[int, str]],
) -> pd.DataFrame:
    """Set `is_reference` True iff a row's (round, version) equals its
    (slide, scene)'s resolved reference. Returns the same DataFrame (mutated)."""
    def _is_ref(row: pd.Series) -> bool:
        key = (str(row["slide"]), str(row["scene"]))
        target = resolved.get(key)
        if target is None:
            return False
        return int(row["round"]) == target[0] and _canon_version_token(row["version"]) == target[1]

    if len(df) == 0:
        df["is_reference"] = pd.Series(dtype=bool)
        return df
    df["is_reference"] = df.apply(_is_ref, axis=1)
    return df
