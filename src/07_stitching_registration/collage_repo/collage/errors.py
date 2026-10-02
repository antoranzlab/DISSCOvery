"""Exception types for COLLAGE.

These replace the legacy bare-name "halt here" sentinels (e.g. a line that just
said ``error_finding_pixel_size``), which raised an opaque ``NameError`` when hit
-- or, worse, were silently swallowed by a surrounding ``except``. Each now
raises a typed, message-bearing error so failures are loud and diagnosable, and
so callers (e.g. a cohort runner) can catch ``CollageError`` to isolate a bad
scene without taking down the whole batch.
"""
from __future__ import annotations


class CollageError(RuntimeError):
    """Base class for all COLLAGE pipeline errors."""


class MetadataError(CollageError):
    """Tile metadata is missing or unparseable (pixel size, scene/tile token)."""


class MissingInputError(CollageError):
    """A required output from an earlier pipeline step is absent.

    Raised at a step boundary when a precondition is not met (e.g. step 3 run
    before step 2 produced its registration output), so the failure is reported
    where it originates rather than as empty/garbage output downstream.
    """


class ConsensusError(CollageError):
    """The AlignQC/registration consensus could not be established for a tile."""


class ReconstructionError(CollageError):
    """An invariant was violated while assembling a reconstruction."""


def require_prior_step(manifest_path: str, *, step: str, prior: str, hint: str = "") -> None:
    """Fail loudly at a step boundary if the prior step did not complete.

    A step writes its ``run_manifest_step{N}.json`` only at the very end, so the
    manifest's existence means that step ran to completion. This check is a single
    ``os.path.exists`` -- O(1) regardless of tile count, with no directory scan --
    and it reuses the manifest the pipeline already produces rather than competing
    with it.

    Combined with the consensus/registration code now *raising* on failure
    (so a failed step aborts before writing its manifest), this turns "step N run
    before step N-1" and "step N-1 crashed midway" into an immediate, located
    error instead of empty/garbage output surfacing one or two steps downstream.
    """
    import os

    if not os.path.exists(manifest_path):
        msg = (f"Step {step} requires step {prior} to have completed first, but its "
               f"run-manifest is missing:\n  {manifest_path}\n"
               f"Run step {prior} before step {step} (or step {prior} may have failed "
               f"before finishing -- check its log).")
        raise MissingInputError(msg + (f"\n{hint}" if hint else ""))
