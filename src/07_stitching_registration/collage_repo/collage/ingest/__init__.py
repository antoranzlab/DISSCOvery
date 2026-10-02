"""Data ingestion: turn heterogeneous scanner output into one canonical manifest.

Public API:
    build_manifest(input_dir, adapter_name, ctx) -> DataFrame
    manifest.save / manifest.load / manifest.validate
"""
from . import manifest
from .adapters import IngestContext, build_manifest, discover_round_dirs, get_adapter

__all__ = [
    "manifest",
    "IngestContext",
    "build_manifest",
    "discover_round_dirs",
    "get_adapter",
]
