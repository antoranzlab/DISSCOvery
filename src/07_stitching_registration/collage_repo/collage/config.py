"""Configuration loading and validation for COLLAGE.

All pipeline parameters come from a single YAML file (see config.example.yaml).
This module loads it, applies defaults, validates the essentials, and exposes a
plain object the step modules consume. No step should read paths or parameters
from anywhere else.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class CollageConfig:
    project_dir: str
    reference_round: int = 1
    reference_version: str | None = None
    reference_overrides: list = field(default_factory=list)
    channel: str = "DAPI"
    n_cores: int = 4
    steps: dict[str, bool] = field(default_factory=dict)
    register: dict[str, Any] = field(default_factory=dict)
    pseudotiles: dict[str, Any] = field(default_factory=dict)
    reconstruct: dict[str, Any] = field(default_factory=dict)
    qc: dict[str, Any] = field(default_factory=dict)
    model: dict[str, Any] = field(default_factory=dict)
    input: dict[str, Any] = field(default_factory=dict)
    stitch: dict[str, Any] = field(default_factory=dict)
    config_dir: str = ""

    # --- ingestion settings --------------------------------------------------
    @property
    def input_dir(self) -> str:
        """Where the round folders live. Defaults to the conventional
        output_FFC_corrected/ subfolder, but can be set explicitly via
        input.dir for data that does not use that wrapper."""
        d = self.input.get("dir")
        if d:
            return os.path.abspath(os.path.expanduser(str(d)))
        return self.tiles_dir

    @property
    def adapter(self) -> str:
        return str(self.input.get("adapter", "auto"))

    @property
    def manifest_path(self) -> str:
        p = self.input.get("manifest", "manifest.csv")
        return p if os.path.isabs(p) else os.path.join(self.project_dir, p)

    def ingest_context(self):
        from .ingest import IngestContext
        return IngestContext(
            reference_round=self.reference_round,
            column_map=self.input.get("column_map") or {},
            overlap=float(self.input.get("overlap", 0.1)),
            reference_version=self.reference_version,
            reference_overrides=self.reference_overrides or [],
        )

    # --- derived paths (single source of truth for the directory layout) -----
    @property
    def tiles_dir(self) -> str:
        return os.path.join(self.project_dir, "output_FFC_corrected")

    @property
    def output_reg(self) -> str:
        return os.path.join(self.project_dir, "output_reg")

    @property
    def output_pseudotiles(self) -> str:
        return os.path.join(self.project_dir, "output_pseudotiles")

    @property
    def output_registration(self) -> str:
        # Step 4 writes reconstructions to <project>/output_registration/<scene>/
        # (folder_reg = project_dir/output_registration). Single level, not doubled.
        return os.path.join(self.project_dir, "output_registration")

    @property
    def qc_dir(self) -> str:
        return os.path.join(self.output_reg, "QC_final")

    def step_manifest_path(self, n: int) -> str:
        """Location of a step's run-manifest. Steps 1/2/4 write into output_reg;
        step 3 writes into output_pseudotiles. Single source of truth for the
        precondition checks (collage.errors.require_prior_step)."""
        base = self.output_pseudotiles if n == 3 else self.output_reg
        return os.path.join(base, f"run_manifest_step{n}.json")

    @property
    def model_path(self) -> str:
        # Resolve to an absolute path so the model is found regardless of the
        # working directory of the process that loads it (notably the consensus
        # subprocess in step 2). A relative path is tried against several bases
        # in priority order -- the config file's directory, the current working
        # directory, and the repo root (where scripts/download_model.py installs
        # it) -- returning the first that exists. This prevents the silent
        # "model not found" that otherwise makes the AI consensus fail and
        # produces empty pseudotiles / empty moving-round reconstructions.
        p = os.path.expanduser(str(self.model.get("path", "./models/classification_network.h5")))
        if os.path.isabs(p):
            return p
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bases = []
        if self.config_dir:
            bases.append(self.config_dir)
        bases.append(os.getcwd())
        bases.append(repo_root)
        for base in bases:
            cand = os.path.abspath(os.path.join(base, p))
            if os.path.exists(cand):
                return cand
        # None exist: return the config-dir (or cwd) relative path so the
        # downstream existence check reports a sensible, absolute location.
        return os.path.abspath(os.path.join(self.config_dir or os.getcwd(), p))


_DEFAULT_STEPS = {
    "stitch": True,
    "register": True,
    "pseudotiles": True,
    "reconstruct": True,
    "qc": False,
}


def load_config(path: str) -> CollageConfig:
    """Load and validate a COLLAGE config file."""
    with open(path, "r") as fh:
        raw = yaml.safe_load(fh) or {}

    if "project_dir" not in raw:
        raise ValueError(
            f"'project_dir' is required in {path}. See config.example.yaml."
        )

    steps = {**_DEFAULT_STEPS, **(raw.get("steps") or {})}

    # reference_round accepts an int (1) or a literal token ("R01"); normalise to
    # int. reference_version is an optional literal token ("V01") or None.
    from .ingest.reference import norm_round, norm_version, ReferenceError
    try:
        ref_round = norm_round(raw.get("reference_round", 1))
        ref_version = norm_version(raw.get("reference_version"))
    except ReferenceError as e:
        raise ValueError(f"{e} (in {path})") from e
    ref_overrides = raw.get("reference_overrides") or []
    if not isinstance(ref_overrides, list):
        raise ValueError(
            f"'reference_overrides' must be a list of entries in {path}; got "
            f"{type(ref_overrides).__name__}."
        )

    cfg = CollageConfig(
        project_dir=os.path.abspath(os.path.expanduser(raw["project_dir"])),
        reference_round=ref_round,
        reference_version=ref_version,
        reference_overrides=ref_overrides,
        channel=str(raw.get("channel", "DAPI")),
        n_cores=int(raw.get("n_cores", 4)),
        steps=steps,
        register=raw.get("register") or {},
        pseudotiles=raw.get("pseudotiles") or {},
        reconstruct=raw.get("reconstruct") or {},
        qc=raw.get("qc") or {},
        model=raw.get("model") or {},
        input=raw.get("input") or {},
        stitch=raw.get("stitch") or {},
        config_dir=os.path.dirname(os.path.abspath(path)),
    )

    _validate(cfg)
    return cfg


def _validate(cfg: CollageConfig) -> None:
    # project_dir is an OUTPUT location: create it if missing rather than
    # erroring (the pipeline writes all of its outputs underneath it).
    os.makedirs(cfg.project_dir, exist_ok=True)
    if not os.path.isdir(cfg.input_dir):
        raise FileNotFoundError(
            f"Input folder not found: {cfg.input_dir}. Set input.dir in the config, "
            f"or place the round folders in an 'output_FFC_corrected' subfolder of "
            f"project_dir. See docs/data_layout.md."
        )
    if cfg.n_cores < 1:
        raise ValueError("n_cores must be >= 1")
