"""COLLAGE command-line interface.

Replaces both the old `main.py` (hard-coded paths, only 3 of 5 steps) and the
manual workflow where each script prompted for a path with input().

Usage:
    collage run --config config.yaml            # run all enabled steps
    collage run --config config.yaml --step 2   # run only step 2
    collage --help
"""
from __future__ import annotations

import argparse
import sys
import time

from .config import load_config
from .ingest import build_manifest, manifest as manifest_mod
from .steps import step1_stitch, step2_register, step3_pseudotiles, step4_reconstruct, step5_qc

# Ordered registry: (key, human name, module, config-toggle key)
_PIPELINE = [
    (1, "Stitch", step1_stitch, "stitch"),
    (2, "Register", step2_register, "register"),
    (3, "Pseudotiles", step3_pseudotiles, "pseudotiles"),
    (4, "Reconstruct", step4_reconstruct, "reconstruct"),
    (5, "QC", step5_qc, "qc"),
]


def _digest(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    print(f"Digesting input: {cfg.input_dir}")
    print(f"  adapter = {cfg.adapter}")
    df = build_manifest(cfg.input_dir, cfg.adapter, cfg.ingest_context())
    report = manifest_mod.validate(
        df,
        require_stage=not getattr(args, "allow_missing_stage", False),
        register_channel=cfg.channel,
    )
    print(report.render())
    manifest_mod.save(df, cfg.manifest_path)
    print(f"\nManifest written to: {cfg.manifest_path}")
    print("Inspect or hand-edit it before running the pipeline if needed.")
    return 0 if report.ok else 2


def _run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    is_child = getattr(args, "_child", False)

    # Ensure a manifest exists; build it on the fly if the user skipped `digest`.
    # Only the top-level orchestrator does this (children inherit the manifest).
    import os as _os
    if not is_child and not _os.path.exists(cfg.manifest_path):
        print("No manifest found; running digest first...\n")
        rc = _digest(args)
        if rc not in (0,):
            print("\nDigest reported errors. Fix them (or edit the manifest) before running.")
            return rc
        print()

    selected = set(args.step) if args.step else None

    # Resolve the ordered list of steps to actually run.
    steps_to_run = []
    for num, name, module, toggle in _PIPELINE:
        if selected is not None:
            if num in selected:
                steps_to_run.append((num, name, module, toggle))
        elif cfg.steps.get(toggle, False):
            steps_to_run.append((num, name, module, toggle))

    # Child invocation: run exactly the requested step(s) in-process, no chrome.
    if is_child:
        for num, name, module, toggle in steps_to_run:
            module.run(cfg)
        return 0

    print(f"COLLAGE pipeline on project: {cfg.project_dir}")
    print(f"  reference round = R{cfg.reference_round:02d} | channel = {cfg.channel} | cores = {cfg.n_cores}\n")
    if selected is None:
        for num, name, module, toggle in _PIPELINE:
            if not cfg.steps.get(toggle, False):
                print(f"[step {num}: {name}] skipped (disabled in config)")

    # Why subprocess isolation: TensorFlow initialises internal threads on first
    # use. A later step that fork()s workers would inherit those threads' held
    # locks and deadlock (e.g. step 2 loads TF, then step 3's forked workers hang
    # on model load). Running each step as a fresh process gives every step a
    # pristine interpreter -- exactly what running them one-by-one does manually.
    # A single step is already its own process, so it runs in-process.
    isolate = len(steps_to_run) > 1

    for num, name, module, toggle in steps_to_run:
        print(f"[step {num}: {name}] starting...")
        t0 = time.time()
        if isolate:
            import subprocess
            cmd = [sys.executable, "-m", "collage.cli", "run",
                   "--config", args.config, "--step", str(num), "--_child"]
            rc = subprocess.run(cmd).returncode
            if rc != 0:
                print(f"[step {num}: {name}] FAILED (exit {rc}). Stopping.")
                return rc
        else:
            module.run(cfg)
        print(f"[step {num}: {name}] done in {time.time() - t0:.1f}s\n")

    print("COLLAGE finished.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="collage", description="COLLAGE pipeline runner.")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run the COLLAGE pipeline.")
    run_p.add_argument("--config", required=True, help="Path to config.yaml")
    run_p.add_argument(
        "--step", type=int, action="append", choices=[1, 2, 3, 4, 5],
        help="Run only this step (repeatable). Overrides the config toggles.",
    )
    run_p.add_argument("--_child", action="store_true", help=argparse.SUPPRESS)
    run_p.set_defaults(func=_run)

    dig_p = sub.add_parser("digest", help="Scan inputs and build/validate the tile manifest.")
    dig_p.add_argument("--config", required=True, help="Path to config.yaml")
    dig_p.add_argument(
        "--allow-missing-stage", action="store_true",
        help="Treat missing stage positions as a warning, not an error "
             "(for the filename_grid adapter).",
    )
    dig_p.set_defaults(func=_digest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
