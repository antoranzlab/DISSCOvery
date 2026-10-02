"""Persistent worker pool for step 3's gap-fill overlap scoring.

Mirrors _inference_service.py's CPUPoolService (see that module for the
fork-safety and file-based-result-delivery rationale) but scores raw
(ref, query) numpy array pairs directly via step3_pseudotiles.evaluate_overlap,
matching step 3's own gap-fill scoring math exactly -- unlike step 2's
file-path-based scorer, step 3's candidates are crops taken on-the-fly from
in-memory stitched mosaics and never written to disk, so there is nothing to
hand a file-path-based scorer.

Before this pool existed, every one of step 3's per-tile worker processes
(step3_pseudotiles.generate_pseudotile, forked once per tile) that needed
gap-fill scoring loaded its own fresh copy of the ~94MB model whenever it had
any overlapping registration candidates to reconcile. Measured on a real
production run: 12,830 per-tile calls, 8,685 of them loading the model fresh
(mean 3.24s/load), for 41,621 CPU-seconds of model-loading alone -- more than
the step's entire wall-clock duration. With this pool the model is loaded
once per pool worker (n_cores times total) instead of once per tile.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import time
import uuid

from ._inference_service import _FileFuture, _write_result_atomic


def _gapfill_worker_main(model_path, in_queue, ready_queue):
    """Pool worker: load the model once, then score jobs until a sentinel."""
    for _v in ("OMP_NUM_THREADS", "TF_NUM_INTRAOP_THREADS", "TF_NUM_INTEROP_THREADS",
               "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[_v] = "1"
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    try:
        from ._tf_env import quiet_tf, force_cpu
        # Gap-fill scoring is cheap and not inference-bound (see
        # step3_pseudotiles.py's original inline comment) -- leave the GPU to
        # step 2's single resident worker rather than contending with it.
        force_cpu()
        quiet_tf()
    except Exception:
        pass
    try:
        from tensorflow.keras.models import load_model
        import tensorflow as tf
        tf.config.threading.set_intra_op_parallelism_threads(1)
        tf.config.threading.set_inter_op_parallelism_threads(1)
        model = load_model(model_path)
    except Exception as e:
        ready_queue.put(("error", os.getpid(), repr(e)))
        return
    ready_queue.put(("ready", os.getpid(), None))

    # Deferred import: avoids a module-load-time circular import (this module
    # is imported by step3_pseudotiles.py) and keeps TF out of any process
    # that doesn't end up needing it.
    from .step3_pseudotiles import evaluate_overlap

    while True:
        job = in_queue.get()
        if job is None:  # shutdown sentinel
            break
        ref_arr, query_arr, output_path = job
        try:
            score = evaluate_overlap([(ref_arr, query_arr)], model)
            payload = {"score": score}
        except Exception as e:
            payload = {"score": 0, "error": repr(e)}
        try:
            _write_result_atomic(output_path, payload)
        except Exception:
            pass


class GapfillPoolService:
    """A pool of persistent gap-fill scorer processes that each load the model once."""

    def __init__(self, model_path, n_workers, output_root, start_timeout_s=180.0):
        self.model_path = model_path
        self.n_workers = max(1, int(n_workers))
        self.output_root = output_root
        self.start_timeout_s = start_timeout_s
        # fork, not spawn: workers must be started before any per-tile worker
        # is forked from the main step-3 process, exactly like step 2's pool,
        # so those per-tile workers inherit this pool's queue. See
        # _inference_service.py's module docstring for the full rationale.
        self._ctx = mp.get_context("fork")
        self._in_queue = None
        self._workers = []

    def start(self):
        self._in_queue = self._ctx.Queue()
        ready_queue = self._ctx.Queue()
        for _ in range(self.n_workers):
            p = self._ctx.Process(
                target=_gapfill_worker_main,
                args=(self.model_path, self._in_queue, ready_queue),
                daemon=True,
            )
            p.start()
            self._workers.append(p)

        deadline = time.time() + self.start_timeout_s
        ready = 0
        while ready < self.n_workers:
            remaining = deadline - time.time()
            if remaining <= 0:
                self.shutdown()
                raise TimeoutError(
                    f"Gap-fill pool: only {ready}/{self.n_workers} workers became "
                    f"ready within {self.start_timeout_s}s."
                )
            try:
                status, pid, msg = ready_queue.get(timeout=remaining)
            except Exception:
                continue
            if status == "error":
                self.shutdown()
                raise RuntimeError(f"Gap-fill worker failed to load the model: {msg}")
            ready += 1
        return self

    def submit(self, ref_arr, query_arr):
        if self._in_queue is None:
            raise RuntimeError("GapfillPoolService.start() must be called before submit().")
        output_path = os.path.join(
            self.output_root, "_gapfill_pool_results", uuid.uuid4().hex + ".pkl"
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        self._in_queue.put((ref_arr, query_arr, output_path))
        return _FileFuture(output_path)

    def shutdown(self, timeout=30.0):
        if self._in_queue is not None:
            for _ in self._workers:
                try:
                    self._in_queue.put(None)
                except Exception:
                    pass
        for p in self._workers:
            p.join(timeout=timeout)
            if p.is_alive():
                p.terminate()
        self._workers = []
        self._in_queue = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.shutdown()
