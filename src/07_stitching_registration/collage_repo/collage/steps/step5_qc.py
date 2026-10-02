"""Step 5 - Registration QC (optional).

For each scene, compares the registered reference-round slide against every other
round's registered slide (on the QC channel, typically DAPI) and produces a
patch-wise AlignQC score map:

  - a sparse CSV (tmp_row, tmp_column, score) at 256-px patch granularity,
  - an interactive Plotly heatmap as HTML, and
  - the heatmap as JSON.

Based on the user-provided evaluate_registration_algnqc.py and the R job-list
generator, with two improvements: the AlignQC model is loaded once per run (not
once per image pair), and reconstructed filenames are parsed robustly by token
role (round / channel / scene) instead of a fixed positional split.

Inputs are the reconstructed slides from step 4 (cfg.output_registration, or
qc.input_dir to override). Outputs go to cfg.qc_dir/<scene>/.
"""
from __future__ import annotations

import os
import re
import json
import time
import platform
import warnings
from datetime import datetime, timezone

import numpy as np
from ._model_input import pack_pair
from .. import _compat  # noqa: F401  -- numpy alias shim for legacy libs
import pandas as pd
import tifffile

warnings.filterwarnings("ignore")

from ..config import CollageConfig
from ..errors import require_prior_step

_ROUND_RE = re.compile(r"^R\d+$")
_VERSION_RE = re.compile(r"^V\d+$")
_PATCH = 256


def range_x1_q(image: np.ndarray, q: float = 0.99) -> np.ndarray:
    """Percentile-clip normalise to [0, 1] using the q / (1-q) quantiles of the
    non-zero pixels (matches the provided script)."""
    nz = image[image > 0]
    if nz.size == 0:
        return image.astype(np.float32)
    q_high = np.quantile(nz, q)
    q_low = np.quantile(nz, 1 - q)
    denom = (q_high - q_low) if (q_high - q_low) != 0 else 1.0
    image = (image - q_low) / denom
    return np.clip(image, 0, 1)


def _parse_recon_name(fname: str):
    """Parse a reconstructed slide filename into (round, version, channel, scene_key).

    Robust to varying token counts: round = the R<NN> token, version = the
    V<NN> token, channel = the last token before the extension, scene_key =
    everything else -- so the same physical scene matches across both rounds
    AND versions (a version is just a different acquisition of the same
    scene, not a distinct scene identity)."""
    stem = re.sub(r"\.tiff?$", "", fname, flags=re.IGNORECASE)
    toks = stem.split("_")
    rnd = next((t for t in toks if _ROUND_RE.match(t)), None)
    ver = next((t for t in toks if _VERSION_RE.match(t)), None)
    channel = toks[-1]
    scene_key = "_".join(t for t in toks if t != rnd and t != ver and t != channel)
    return rnd, ver, channel, scene_key


def evaluate_registration(path_ref_image, path_query_image, model,
                          path_csv, path_html, path_json) -> int:
    """Patch-wise AlignQC of a query slide vs the reference. Writes CSV + HTML +
    JSON. Returns the number of scored (non-empty) patches."""
    import plotly.graph_objects as go
    from patchify import patchify

    for p in (path_csv, path_html, path_json):
        os.makedirs(os.path.dirname(p), exist_ok=True)

    ref = np.squeeze(tifffile.imread(path_ref_image))
    qry = np.squeeze(tifffile.imread(path_query_image))
    if ref.max() > 0:
        ref = range_x1_q(ref, 0.99)
    if qry.max() > 0:
        qry = range_x1_q(qry, 0.99)

    h, w = ref.shape
    ph = int(np.ceil(h / _PATCH) * _PATCH - h)
    pw = int(np.ceil(w / _PATCH) * _PATCH - w)
    ref = np.pad(ref, ((0, ph), (0, pw)), "constant", constant_values=0)
    qry = np.pad(qry, ((0, ph), (0, pw)), "constant", constant_values=0)

    ref_p = patchify(ref, (_PATCH, _PATCH), step=_PATCH)
    qry_p = patchify(qry, (_PATCH, _PATCH), step=_PATCH)
    patch_rows, patch_cols = ref_p.shape[0], ref_p.shape[1]
    ref_p = ref_p.reshape(-1, _PATCH, _PATCH)
    qry_p = qry_p.reshape(-1, _PATCH, _PATCH)

    scores = np.zeros(len(ref_p), dtype=np.float32)
    batch = 32
    for i in range(0, len(ref_p), batch):
        rb = ref_p[i:i + batch]
        qb = qry_p[i:i + batch]
        keep = [j for j, p in enumerate(rb) if not np.all(p == 0)]
        if not keep:
            continue
        inp = pack_pair(rb[keep], qb[keep], model)
        out = model.predict(inp, verbose=0)
        for k, j in enumerate(keep):
            scores[i + j] = float(np.squeeze(out[k][0]))

    score_map = scores.reshape(patch_rows, patch_cols)
    rows, cols = np.nonzero(score_map)
    df = pd.DataFrame(
        np.stack([rows, cols, score_map[rows, cols]], axis=1),
        columns=["tmp_row", "tmp_column", "score"],
    )
    df.to_csv(path_csv, index=False)

    df = df.sort_values(["tmp_row", "tmp_column"])
    color_scale = [[0, "indianred"], [0.5, "gold"], [1, "seagreen"]]
    fig = go.Figure(data=go.Heatmap(
        x=df["tmp_column"], y=-df["tmp_row"], z=df["score"],
        colorscale=color_scale, zmin=0, zmax=1,
        colorbar=dict(title="AlignQC"),
    ))
    fig.update_layout(
        title=None,
        xaxis=dict(title="", tickvals=[], showticklabels=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(title="", tickvals=[], showticklabels=False),
        hoverlabel=dict(bgcolor="white"),
    )
    fig.write_html(path_html)
    with open(path_json, "w") as fh:
        fh.write(fig.to_json())
    return int(len(df))


def _discover_slides(input_dir: str, channel: str):
    """Map scene_key -> {(round, version): filepath} for slides on the QC channel.

    Keyed by the (round, version) pair, not round alone -- a scene can have
    multiple versions of the same round (e.g. R02/V01 and R02/V02), and both
    need to be scored against the single reference independently. Keying by
    round alone silently collapsed them, keeping only whichever file the
    directory scan happened to visit last."""
    scenes: dict = {}
    if not os.path.isdir(input_dir):
        return scenes
    for folder in sorted(os.listdir(input_dir)):
        fdir = os.path.join(input_dir, folder)
        if not os.path.isdir(fdir):
            continue
        for f in os.listdir(fdir):
            if not re.search(r"\.tiff?$", f, re.IGNORECASE):
                continue
            rnd, ver, chan, scene_key = _parse_recon_name(f)
            if rnd is None or chan != channel:
                continue
            scenes.setdefault(scene_key, {})[(rnd, ver)] = os.path.join(fdir, f)
    return scenes


def _json_safe(o):
    """Coerce run-manifest values JSON can't handle (sets, numpy scalars)."""
    import numpy as _np
    if isinstance(o, set):
        return sorted(o)
    if isinstance(o, _np.integer):
        return int(o)
    if isinstance(o, _np.floating):
        return float(o)
    if isinstance(o, _np.ndarray):
        return o.tolist()
    return str(o)


def run(cfg: CollageConfig) -> None:
    qc = cfg.qc if isinstance(cfg.qc, dict) else {}
    channel = qc.get("channel", cfg.channel)
    ref_round = qc.get("ref_round", f"R{cfg.reference_round:02d}")
    ref_version = qc.get("ref_version", cfg.reference_version)
    input_dir = qc.get("input_dir", cfg.output_registration)
    out_base = cfg.qc_dir
    path_to_model = cfg.model_path

    # Precondition: when scoring the pipeline's own reconstructions (default
    # input), step 4 must have completed (O(1) manifest check). Skipped if the
    # user pointed qc.input_dir at some other directory deliberately.
    if not qc.get("input_dir"):
        require_prior_step(cfg.step_manifest_path(4),
                           step="5 (qc)", prior="4 (reconstruct)")

    if not os.path.isdir(input_dir):
        raise FileNotFoundError(
            f"Reconstructed slides not found at {input_dir}. Run step 4 first, "
            f"or set qc.input_dir."
        )
    if not os.path.exists(path_to_model):
        raise FileNotFoundError(
            f"AlignQC model not found at {path_to_model}. Run scripts/download_model.py."
        )

    print(f"  QC channel = {channel} | reference = {ref_round}_{ref_version} | input = {input_dir}")
    from collage.steps._tf_env import quiet_tf
    quiet_tf()
    from tensorflow.keras.models import load_model
    model = load_model(path_to_model, compile=False)

    scenes = _discover_slides(input_dir, channel)
    t0 = time.time()
    n_pairs = n_fail = 0
    ref_key = (ref_round, ref_version)
    for scene_key, roundver2path in sorted(scenes.items()):
        if ref_key not in roundver2path:
            print(f"  WARNING: scene {scene_key} has no reference slide ({ref_round}_{ref_version}); skipping.")
            continue
        ref_path = roundver2path[ref_key]
        for (rnd, ver), qpath in sorted(roundver2path.items()):
            if (rnd, ver) == ref_key:
                continue
            base = os.path.splitext(os.path.basename(qpath))[0]
            sdir = os.path.join(out_base, scene_key)
            try:
                evaluate_registration(
                    ref_path, qpath, model,
                    os.path.join(sdir, base + ".csv"),
                    os.path.join(sdir, base + ".html"),
                    os.path.join(sdir, base + ".json"),
                )
                n_pairs += 1
            except Exception as e:  # surface, don't swallow (item 3)
                n_fail += 1
                print(f"  ERROR QC {scene_key} {rnd}: {e}")

    os.makedirs(out_base, exist_ok=True)
    rm = {
        "step": "5_qc",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "reference_round": ref_round, "channel": channel,
        "pairs_scored": n_pairs, "pairs_failed": n_fail,
        "duration_sec": round(time.time() - t0, 1),
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
    }
    with open(os.path.join(out_base, "run_manifest_step5.json"), "w") as fh:
        json.dump(rm, fh, indent=2, default=_json_safe)
    print(f"  QC score maps written for {n_pairs} round-pairs"
          + (f" ({n_fail} failed)" if n_fail else "") + f" -> {out_base}")
