"""COLLAGE pipeline steps.

Each module exposes a single entry point:

    def run(cfg: CollageConfig) -> None

The CLI calls these in order. Steps read every parameter from `cfg` (the loaded
config) and write to the derived output paths on `cfg`. No step reads paths or
parameters from anywhere else, prompts interactively, or hard-codes a directory.
"""
