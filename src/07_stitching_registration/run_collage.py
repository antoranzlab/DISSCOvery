#!/usr/bin/env python
"""Drive the COLLAGE registration pipeline (stage 07) directly from stage 06's split_scenes
output, via direct calls into the Python COLLAGE package at collage_repo/ (replaces the old
R-script chain in legacy/, which existed only for a legacy COLLAGE build's limitations that no
longer apply). split_scenes.py's naming/metadata already match COLLAGE's 'zeiss' adapter, and
disscovery's reference_map_slide_round_version.json is translated into COLLAGE's config schema."""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import tifffile
import yaml
from PIL import Image
from scipy.stats import wasserstein_distance_nd

def _norm_round(token):
    """'R01' -> 1"""
    return int(str(token).lstrip("Rr").lstrip("0") or "0")

def _scan_regions_for_slide(input_path_tiles, slide):
    """Scene tokens (e.g. 'S1') actually present for a slide, scanned from its split_scenes folder names."""
    scenes = set()
    for name in os.listdir(input_path_tiles):
        if not os.path.isdir(os.path.join(input_path_tiles, name)):
            continue
        parts = name.split("_")
        if len(parts) != 6 or parts[0] != slide:
            continue
        scan_region = parts[5]  # e.g. "S1M"
        if scan_region.endswith("M"):
            scenes.add(scan_region[:-1])  # -> "S1", matches manifest's scene column
    return sorted(scenes)

def build_config(input_path_tiles, project_dir, reference_map, channel, model_path,
                  n_cores, run_qc):
    """Build a COLLAGE config dict from disscovery's reference map (the format of reference_map_slide_round_version.json)."""
    resolved = {slide: (_norm_round(v["reference_round"]), v["reference_version"])
                for slide, v in reference_map.items()}
    distinct = set(resolved.values())

    if len(distinct) == 1:
        # every slide agrees -- a single global default, no overrides needed
        # (this is also what keeps single-slide/benchmark-style data a no-op).
        default_round, default_version = distinct.pop()
        reference_overrides = []
    else:
        # slides disagree -- global default is arbitrary (every slide gets its
        # own override below), pick the most common for readability.
        default_round, default_version = sorted(distinct)[0]
        reference_overrides = []
        for slide, (rnd, ver) in resolved.items():
            for scene in _scan_regions_for_slide(input_path_tiles, slide):
                reference_overrides.append({
                    "slide": slide, "scene": scene,
                    "round": f"R{rnd:02d}", "version": ver,
                })

    return {
        "project_dir": project_dir,
        "input": {"dir": input_path_tiles, "adapter": "auto", "manifest": "manifest.csv"},
        "reference_round": default_round,
        "reference_version": default_version,
        "reference_overrides": reference_overrides,
        "channel": channel,
        "n_cores": n_cores,
        "steps": {
            "stitch": True, "register": True, "pseudotiles": True,
            "reconstruct": True, "qc": run_qc,
        },
        "register": {"do_ai_consensus": True, "export_consensus_images": True, "seed": 0},
        "stitch": {"seed": 0},
        # n_cores here is concurrent reconstruction JOBS, each forked as its own multiprocessing.Process
        # AFTER this driver's parent process has already loaded a TF model on the GPU (steps 1-3 use
        # it too) -- CUDA contexts are not fork-safe, so n_cores>1 here reliably crashes children with
        # CUDA_ERROR_NOT_INITIALIZED, and forcing those children to CPU instead (tried) deadlocks them
        # in TF's own init (observed: 0s CPU time, stuck on a futex, for 2+ hours). Keep at 1 -- the
        # reference-round pass already proves this same reconstruction code works reliably at n_cores=1
        # (no fork ever happens there either). RAM-heavy either way per the step's own docstring.
        "reconstruct": {"n_cores": 1},
        "model": {"path": model_path},
    }

def _coarse_tissue_grid(img, n_bins):
    """Bin an image into an n_bins x n_bins grid of tissue (non-zero) fraction per cell -- cheap; the EMD computed from this grid is what's expensive, not the binning."""
    h, w = img.shape[:2]
    gh, gw = max(1, h // n_bins), max(1, w // n_bins)
    grid = np.zeros((n_bins, n_bins))
    for i in range(n_bins):
        for j in range(n_bins):
            cell = img[i * gh:(i + 1) * gh, j * gw:(j + 1) * gw]
            grid[i, j] = np.count_nonzero(cell) / cell.size if cell.size else 0.0
    return grid

def _naive_stitch_path(project_dir, slide, scene, r, v):
    # project_id/user_id aren't tracked separately by this driver, so match by prefix/suffix instead of hardcoding the whole folder name
    out_reg = os.path.join(project_dir, "output_reg")
    prefix, suffix = f"{slide}_R{r:02d}_{v}_", f"_S{scene}M"
    matches = [d for d in os.listdir(out_reg)
               if d.startswith(prefix) and d.endswith(suffix)
               and os.path.isdir(os.path.join(out_reg, d))]
    if len(matches) != 1:
        return None
    jpeg = os.path.join(out_reg, matches[0], "naive_stitch", f"R{r:02d}.jpeg")
    return jpeg if os.path.exists(jpeg) else None

def diagnose_registration_failure(project_dir, slide, scene, rnd, ver, ref_round, ref_version,
                                   n_bins=15, low_tissue_threshold=0.02):
    """Distinguish "no tissue to register in the first place" from "registration destroyed real
    tissue" for a (slide, scene, round) the fast completeness check already flagged, by comparing
    step 1's per-scene naive-stitch preview (before step 2's registration ever runs) between the
    failing round and the reference round, for the SAME scene. Only called on failure."""
    p_fail = _naive_stitch_path(project_dir, slide, scene, rnd, ver)
    p_ref = _naive_stitch_path(project_dir, slide, scene, ref_round, ref_version)
    if p_fail is None or p_ref is None:
        return ("no diagnosis available -- per-scene naive-stitch preview missing for "
                f"slide={slide} scene={scene} "
                f"({'R%02d_%s' % (rnd, ver) if p_fail is None else 'R%02d_%s' % (ref_round, ref_version)})")

    img_fail = np.array(Image.open(p_fail).convert("L"))
    img_ref = np.array(Image.open(p_ref).convert("L"))
    frac_fail = float(np.count_nonzero(img_fail)) / img_fail.size
    frac_ref = float(np.count_nonzero(img_ref)) / img_ref.size

    if frac_fail < low_tissue_threshold:
        return (f"likely NOT a registration bug -- pre-registration (naive-stitch) coverage "
                f"for slide={slide} scene={scene} R{rnd:02d}_{ver} was already only "
                f"{frac_fail:.1%} (reference R{ref_round:02d}_{ref_version}: {frac_ref:.1%}), "
                f"i.e. there was little tissue in THIS SCENE to register in the first place.")

    g_fail = _coarse_tissue_grid(img_fail, n_bins)
    g_ref = _coarse_tissue_grid(img_ref, n_bins)
    ys, xs = np.mgrid[0:n_bins, 0:n_bins]
    pts = np.stack([ys.ravel(), xs.ravel()], axis=1).astype(float)
    w_fail, w_ref = g_fail.ravel(), g_ref.ravel()
    try:
        emd = wasserstein_distance_nd(pts, pts, w_fail / w_fail.sum(), w_ref / w_ref.sum())
        emd_str = f"{emd:.3f}"
    except Exception as e:  # best-effort diagnostic -- the frac comparison above already
        emd_str = f"(EMD computation failed: {e})"  # carries the main signal regardless

    return (f"likely IS a registration bug -- pre-registration (naive-stitch) coverage for "
            f"slide={slide} scene={scene} R{rnd:02d}_{ver} was {frac_fail:.1%} (comparable to "
            f"reference R{ref_round:02d}_{ref_version}'s {frac_ref:.1%}), so THIS SCENE clearly "
            f"had tissue before registration; spatial-distribution EMD vs reference = "
            f"{emd_str} on a {n_bins}x{n_bins} grid. Investigate step 2's overlap/masking "
            f"geometry (coor_im1_int/coor_im2_int, register.compression_factor) for this "
            f"scene/round.")

def _nonzero_fraction(out_dir, channel, slide, scene, rnd, ver):
    prefix = f"{slide}_R{rnd:02d}_{ver}_"
    suffix = f"_S{scene}"
    matches = [d for d in os.listdir(out_dir)
               if os.path.isdir(os.path.join(out_dir, d))
               and d.startswith(prefix) and d.endswith(suffix)]
    if len(matches) != 1:
        return None
    f = os.path.join(out_dir, matches[0], f"{matches[0]}_{channel}.tiff")
    if not os.path.exists(f):
        return None
    img = tifffile.imread(f)
    return float(np.count_nonzero(img)) / img.size

def verify_reconstruction_completeness(project_dir, channel, min_fraction_of_reference=0.5):
    """Sanity-check step 4's output: reject silently-empty reconstructions -- COLLAGE can exit 0
    while having written a blank reconstruction for a whole round (e.g. transient resource
    contention killed all of step 2's scoring workers for that round). Compares each non-reference
    round's non-zero fraction against its group's reference round as a RATIO (not an absolute
    non-zero check, since some rounds legitimately have less tissue than the reference)."""
    manifest = pd.read_csv(os.path.join(project_dir, "manifest.csv"))
    out_dir = os.path.join(project_dir, "output_registration")

    failures = []
    for (slide, scene), g in manifest.groupby(["slide", "scene"]):
        ref_rows = g[g["is_reference"]]
        if ref_rows.empty:
            continue  # reference resolution already validates this elsewhere
        ref_round = int(ref_rows.iloc[0]["round"])
        ref_version = str(ref_rows.iloc[0]["version"])

        ref_frac = _nonzero_fraction(out_dir, channel, slide, scene, ref_round, ref_version)
        if ref_frac is None:
            failures.append(f"slide={slide} scene={scene}: reference reconstruction "
                             f"(R{ref_round:02d}_{ref_version}, {channel}) is missing")
            continue

        for (rnd, ver), _gg in g.groupby(["round", "version"]):
            rnd, ver = int(rnd), str(ver)
            if rnd == ref_round and ver == ref_version:
                continue
            frac = _nonzero_fraction(out_dir, channel, slide, scene, rnd, ver)
            if frac is None:
                failures.append(f"slide={slide} scene={scene} R{rnd:02d}_{ver}: "
                                 f"{channel} reconstruction is missing")
            elif ref_frac > 0 and frac < min_fraction_of_reference * ref_frac:
                msg = (
                    f"slide={slide} scene={scene} R{rnd:02d}_{ver}: {channel} "
                    f"reconstruction is {frac:.1%} non-zero vs reference's {ref_frac:.1%} "
                    f"-- registration likely failed for this round (check "
                    f"output_reg/test_for_consen/<tile>/ for missing consensus JSONs)."
                )
                diagnosis = diagnose_registration_failure(
                    project_dir, slide, scene, rnd, ver, ref_round, ref_version)
                msg += f"\n    diagnosis: {diagnosis}"
                failures.append(msg)

    if failures:
        raise RuntimeError(
            "COLLAGE reconstruction completeness check failed:\n  " + "\n  ".join(failures)
        )
    print(f"### completeness check passed: all rounds have reasonable {channel} coverage ###")

def run_collage(input_path_tiles, project_dir, reference_map_json, channel, model_path,
                 n_cores, collage_python, collage_repo_dir, run_qc, skip_existing):
    print(f"### input path tiles (split_scenes output): {input_path_tiles} ###")
    print(f"### project directory (COLLAGE output): {project_dir} ###")
    print(f"### reference map json: {reference_map_json} ###")
    print(f"### channel: {channel} ###")
    print(f"### model path: {model_path} ###")
    print(f"### n_cores: {n_cores} ###")
    print(f"### collage python: {collage_python} ###")
    print(f"### collage repo dir (subprocess cwd): {collage_repo_dir} ###")
    print(f"### run qc: {run_qc} ###")
    print(f"### skip existing: {skip_existing} ###")

    with open(reference_map_json) as f:
        reference_map = json.load(f)

    os.makedirs(project_dir, exist_ok=True)
    config = build_config(input_path_tiles, project_dir, reference_map, channel,
                           model_path, n_cores, run_qc)
    config_path = os.path.join(project_dir, "collage_config.yaml")
    with open(config_path, "w") as f:
        yaml.safe_dump(config, f, sort_keys=False)
    print(f"### wrote COLLAGE config: {config_path} ###")

    manifest_path = os.path.join(project_dir, "manifest.csv")
    if skip_existing and os.path.exists(os.path.join(project_dir, "output_registration")):
        print("### output_registration already exists, skip_existing=True: skipping ###")
        return True

    # cwd matters: TensorFlow/XLA's JIT fallback path has been observed to look
    # for CUDA support files via a path relative to the process's cwd (seen in
    # the wild as "error: libdevice not found at ./libdevice.10.bc"). Every
    # known-good COLLAGE invocation so far was launched with collage_repo/ as
    # cwd; run this driver's subprocesses the same way rather than inheriting
    # whatever directory the caller happens to be in.
    #
    # Thread caps matter just as much: COLLAGE parallelises at the process
    # level (n_cores worker processes for phase-correlation refinement, plus a
    # separate consensus_workers-sized pool for AI scoring -- up to 2*n_cores
    # processes). Left uncapped, numpy/OpenBLAS/MKL/TensorFlow each try to use
    # every core *inside* every one of those processes too, so e.g. n_cores=16
    # on a 32-core box can end up scheduling hundreds of threads across ~32
    # cores (observed: load average >100 on a 32-core machine, workers stuck
    # at ~12% CPU each instead of ~100%). Since parallelism already happens at
    # the process level, cap each process to a single thread for its internal
    # math libraries.
    worker_env = dict(os.environ)
    worker_env.update({
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
    })
    subprocess.run([collage_python, "-m", "collage.cli", "digest", "--config", config_path],
                    check=True, cwd=collage_repo_dir, env=worker_env)
    subprocess.run([collage_python, "-m", "collage.cli", "run", "--config", config_path],
                    check=True, cwd=collage_repo_dir, env=worker_env)

    verify_reconstruction_completeness(project_dir, channel)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run COLLAGE (stage 07) on split_scenes output.")
    parser.add_argument("--input_path_tiles", type=str, required=True,
                         help="Path to split_scenes output (dir). Example: /path/to/project_directory/split_scenes")
    parser.add_argument("--project_dir", type=str, required=True,
                         help="Path to COLLAGE's project/output directory (dir).")
    parser.add_argument("--reference_map_json", type=str, required=True,
                         help="Path to reference_map_slide_round_version.json (.json).")
    parser.add_argument("--channel", type=str, default="DAPI", help="Registration channel.")
    parser.add_argument("--model_path", type=str, required=True,
                         help="Path to the AlignQC model (.h5).")
    parser.add_argument("--n_cores", type=int, default=4, help="Parallel worker processes.")
    parser.add_argument("--collage_python", type=str, required=True,
                         help="Path to the python interpreter with collage installed "
                              "(the collage_clean conda env's python).")
    parser.add_argument("--collage_repo_dir", type=str, required=True,
                         help="Path to collage_repo/ (run as the subprocess's cwd).")
    parser.add_argument("--run_qc", type=lambda v: str(v).lower() in ("yes", "true", "t", "1"),
                         default=False, help="Also run COLLAGE's step 5 QC.")
    parser.add_argument("--skip_existing", type=lambda v: str(v).lower() in ("yes", "true", "t", "1"),
                         default=False, help="Skip if output_registration already exists.")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    run_collage(
        input_path_tiles=args.input_path_tiles,
        project_dir=args.project_dir,
        reference_map_json=args.reference_map_json,
        channel=args.channel,
        model_path=args.model_path,
        n_cores=args.n_cores,
        collage_python=args.collage_python,
        collage_repo_dir=args.collage_repo_dir,
        run_qc=args.run_qc,
        skip_existing=args.skip_existing,
    )
