"""Inference service: schedule AlignQC scoring without reloading the model per pair.

Measured problem (benchmark): the consensus loaded the ~94 MB model 45 times
(once per tile-pair), 5.17s mean, 232.8s total -- 31% of consensus time. Each
load served only a few hundred ms of inference. Production cohorts pay this
thousands of times.

This module provides a persistent CPU worker pool: N processes are started once,
each loads the scorer a single time, and they consume scoring jobs from a shared
queue. The model-load tax is paid N times total instead of once per pair.

Why a *pool* and not a single persistent process: a single scorer process would
serialise all inference and lose the N-way parallelism the current per-pair
subprocess design has -- on a multi-pair scene that would be slower overall. The
pool keeps parallelism (one worker per core) while paying the load cost once each.

Why file-based result delivery: the per-pair workers that call submit() are
themselves forked children of step 2's main process. They cannot share a Python
Future object with the pool. So a job carries an output path; the worker writes
the result there (atomic rename); the submitter polls for it -- exactly the
delivery mechanism the legacy per-pair subprocess already used, so nothing
downstream changes. A future GPU consumer can batch jobs from the queue before
writing results, transparently to submitters.

Fork-safety: neither step 2's main process nor the per-pair workers load
TensorFlow; only the pool workers do, in their own processes. So no process both
initialises TF and is later fork()ed -- the deadlock condition we hit earlier
cannot arise here.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import pickle
import time
import uuid

import numpy as np


def score_job(scorer, im_pairs, export_consen_ima):
    """Score every (ref, query) pair in a job and pick the best method.

    Single source of truth for the consensus scoring loop -- used by both the
    pool worker and the legacy standalone subprocess. Logic is identical to the
    legacy evaluate_overlap_function.py per-pair loop (method name parsed from the
    filename token, best non-nan score wins, scored images deleted unless they are
    being exported).
    """
    method2ia_red = {}
    curr_best = 0
    final_method = None

    for im_p in im_pairs:
        path_ref_image, path_query_image = im_p[0], im_p[1]
        method_ = os.path.basename(path_ref_image).split("____")[3]
        _t0 = time.time()
        try:
            tmp_score = scorer.score(path_ref_image, path_query_image)
        except Exception as e:  # one bad pair must not abort the whole job
            method2ia_red[method_] = {
                "score": str(e), "path_ref_image": path_ref_image,
                "path_query_image": path_query_image,
                "score_time_sec": round(time.time() - _t0, 3),
            }
            continue
        method2ia_red[method_] = {
            "score": tmp_score, "path_ref_image": path_ref_image,
            "path_query_image": path_query_image,
            "score_time_sec": round(time.time() - _t0, 3),
        }
        if not export_consen_ima:
            try:
                os.remove(path_ref_image)
                os.remove(path_query_image)
            except OSError:
                pass
        if not np.isnan(tmp_score) and tmp_score > curr_best:
            curr_best = tmp_score + 0
            final_method = method_[:]

    return method2ia_red, final_method


def score_job_batched(scorer, im_pairs, export_consen_ima):
    """Like score_job, but scores all of a job's pairs with one batched inference
    pass (GPU path). Bookkeeping -- method name from filename, best non-nan score,
    image deletion -- is identical to score_job; only the scoring is batched.
    """
    pairs = [(p[0], p[1]) for p in im_pairs]
    _t0 = time.time()
    results = scorer.score_pairs_batched(pairs)
    _elapsed = round((time.time() - _t0) / max(1, len(pairs)), 3)

    method2ia_red = {}
    curr_best = 0
    final_method = None
    for im_p, res in zip(im_pairs, results):
        path_ref_image, path_query_image = im_p[0], im_p[1]
        method_ = os.path.basename(path_ref_image).split("____")[3]
        if isinstance(res, Exception):
            method2ia_red[method_] = {
                "score": str(res), "path_ref_image": path_ref_image,
                "path_query_image": path_query_image, "score_time_sec": _elapsed,
            }
            continue
        tmp_score = res
        method2ia_red[method_] = {
            "score": tmp_score, "path_ref_image": path_ref_image,
            "path_query_image": path_query_image, "score_time_sec": _elapsed,
        }
        if not export_consen_ima:
            try:
                os.remove(path_ref_image)
                os.remove(path_query_image)
            except OSError:
                pass
        if not np.isnan(tmp_score) and tmp_score > curr_best:
            curr_best = tmp_score + 0
            final_method = method_[:]

    return method2ia_red, final_method


def _write_result_atomic(output_path, payload):
    tmp = output_path + ".tmp-" + uuid.uuid4().hex[:8]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(tmp, "wb") as f:
        pickle.dump(payload, f)
    os.replace(tmp, output_path)  # atomic on POSIX -> submitter never reads a partial file


def _worker_main(scorer_name, model_path, in_queue, ready_queue):
    """Pool worker: load the scorer once, then serve jobs until a sentinel."""
    # Bound this worker to a single inference thread BEFORE TF initialises. With N
    # workers each running TF's full intra-op thread pool, the workers oversubscribe
    # the machine and contend for memory bandwidth -- which throttles inference and
    # eats the load-once win. One thread per worker means N workers ~= N busy cores,
    # and parallelism comes from having N workers (not N*threads). Env vars must be
    # set before TF import; we also call the TF setters defensively.
    for _v in ("OMP_NUM_THREADS", "TF_NUM_INTRAOP_THREADS", "TF_NUM_INTEROP_THREADS",
               "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[_v] = "1"
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    # Hide the GPU from every pool worker BEFORE importing TF. This is the
    # 'cpu_pool' backend -- N of these get forked and each loads the model. On
    # a machine with a visible GPU, leaving it unhidden means all N race for
    # device memory/CUDA context concurrently (observed: intermittent "Graph
    # execution error" / ResourceExhaustedError even with only 4 workers, not
    # reproducible when scoring the same pair directly in a single process).
    # Same root cause step 3's per-tile workers already hit and fixed with
    # this exact call (see force_cpu()'s docstring); the CPU pool needed it
    # too and never got it.
    try:
        from ._tf_env import force_cpu
        force_cpu()
    except Exception:
        pass
    try:
        import tensorflow as tf
        tf.config.threading.set_intra_op_parallelism_threads(1)
        tf.config.threading.set_inter_op_parallelism_threads(1)
    except Exception:
        pass  # env vars already applied; setters are belt-and-braces

    try:
        from collage.steps._scorer import get_scorer
        scorer = get_scorer(scorer_name, model_path)
        scorer.load()
    except Exception as e:
        ready_queue.put(("error", os.getpid(), repr(e)))
        return
    ready_queue.put(("ready", os.getpid(), None))

    while True:
        job = in_queue.get()
        if job is None:  # shutdown sentinel
            break
        im_pairs, export_consen_ima, output_path = job
        try:
            method2ia_red, final_method = score_job(scorer, im_pairs, export_consen_ima)
            payload = {"method2ia_red": method2ia_red, "final_method": final_method}
        except Exception as e:
            payload = {"method2ia_red": {}, "final_method": None, "error": repr(e)}
        try:
            _write_result_atomic(output_path, payload)
        except Exception:
            pass  # submitter will time out and surface a clear error


class _FileFuture:
    """Result handle: blocks in result() until the worker writes the output file."""

    def __init__(self, output_path, poll_s=0.05, timeout_s=900.0):
        self.output_path = output_path
        self.poll_s = poll_s
        self.timeout_s = timeout_s

    def result(self):
        deadline = time.time() + self.timeout_s
        while True:
            if os.path.exists(self.output_path):
                with open(self.output_path, "rb") as f:
                    return pickle.load(f)
            if time.time() > deadline:
                raise TimeoutError(
                    f"Consensus scoring timed out after {self.timeout_s}s waiting for "
                    f"{self.output_path} (a pool worker may have died)."
                )
            time.sleep(self.poll_s)


class CPUPoolService:
    """A pool of persistent scorer processes that each load the model once."""

    def __init__(self, scorer_name, model_path, n_workers, output_root,
                 start_timeout_s=180.0):
        self.scorer_name = scorer_name
        self.model_path = model_path
        self.n_workers = max(1, int(n_workers))
        self.output_root = output_root
        self.start_timeout_s = start_timeout_s
        self._ctx = mp.get_context("fork")
        self._in_queue = None
        self._workers = []

    def start(self):
        self._in_queue = self._ctx.Queue()
        ready_queue = self._ctx.Queue()
        for _ in range(self.n_workers):
            p = self._ctx.Process(
                target=_worker_main,
                args=(self.scorer_name, self.model_path, self._in_queue, ready_queue),
                daemon=True,
            )
            p.start()
            self._workers.append(p)

        # Block until every worker has loaded the model (or one failed), so the
        # first submit() never races an unloaded model.
        deadline = time.time() + self.start_timeout_s
        ready = 0
        while ready < self.n_workers:
            remaining = deadline - time.time()
            if remaining <= 0:
                self.shutdown()
                raise TimeoutError(
                    f"Inference pool: only {ready}/{self.n_workers} workers became "
                    f"ready within {self.start_timeout_s}s."
                )
            try:
                status, pid, msg = ready_queue.get(timeout=remaining)
            except Exception:
                continue
            if status == "error":
                self.shutdown()
                raise RuntimeError(f"Inference worker failed to load the scorer: {msg}")
            ready += 1
        return self

    def submit(self, im_pairs, export_consen_ima):
        if self._in_queue is None:
            raise RuntimeError("CPUPoolService.start() must be called before submit().")
        output_path = os.path.join(
            self.output_root, "_pool_results", uuid.uuid4().hex + ".pkl"
        )
        self._in_queue.put((im_pairs, export_consen_ima, output_path))
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


# --- GPU backend ---------------------------------------------------------------------
# The CPU pool's N-forked-workers design cannot be pointed at a GPU: (1) CUDA cannot
# be initialised across fork(), and (2) a GPU hosts ONE resident model fed work, not
# N processes each grabbing the whole device. So the GPU backend is a SINGLE worker,
# started with the 'spawn' context (clean CUDA init), holding the model resident.
#
# Producer/consumer transport is the filesystem, not an in-memory queue: the per-pair
# workers are forked children of step 2's main process, while the GPU worker is
# spawned -- mixing fork-inherited queues with a spawn process is fragile. Instead a
# submit() writes a *.job file atomically into a watch directory; the GPU worker picks
# it up, scores via the same score_job() the CPU path uses, and writes the result to
# the same _FileFuture output path. So results are delivered identically to the CPU
# pool, and scoring math is byte-for-byte the same (only the device differs).
#
# v1 processes one job at a time (load-once + single-resident -- which is what fixes
# the GPU memory race and the per-process reload). Patch-level batching across jobs
# for maximum GPU throughput is a documented v2 optimisation that would change the
# scoring loop, so it is deferred until v1 is validated numerically identical.

def _has_gpu():
    """True iff TensorFlow can see at least one GPU device.

    Split out from _gpu_worker_main so tests can monkeypatch it directly --
    the worker loop itself is exercised with a mock scorer and no real
    TensorFlow (see test_inference_service.py), and this needs to stay
    mockable the same way rather than forcing a real TF/GPU import in that
    fast, portable test path.
    """
    import tensorflow as tf
    return bool(tf.config.list_physical_devices("GPU"))


def _gpu_worker_main(scorer_name, model_path, jobs_dir, ready_path, stop_path,
                     poll_s=0.02):
    import glob
    import time as _t
    # Don't pre-grab all GPU memory: take only what the model needs, so the display
    # and other processes keep their share of the 16 GB.
    os.environ.setdefault("TF_FORCE_GPU_ALLOW_GROWTH", "true")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    # cuDNN autotuning profiles several candidate conv algorithms on first use
    # of a given shape and picks the fastest, but each candidate needs its own
    # scratch buffer to benchmark -- one candidate asked for 752MB in a
    # RESOURCE_EXHAUSTED traceback caught from a live failing run ("No
    # algorithm worked!"). With allow_growth already keeping this process's
    # footprint small, there's little headroom for that multi-candidate
    # comparison. Disabling autotune makes cuDNN use its default heuristic
    # algorithm instead of comparing several, avoiding that memory spike.
    os.environ.setdefault("TF_CUDNN_USE_AUTOTUNE", "0")
    try:
        # TF does NOT raise when no GPU is visible -- it silently falls back to
        # running the model on CPU inside this single process. That's worse
        # than useless here: this worker exists specifically to be GPU-
        # resident, so a silent CPU fallback would keep GPUService's one-
        # process constraint (no N-way parallelism) while getting none of the
        # GPU speed in return. Fail loudly instead, so callers relying on
        # this to signal "no GPU" (e.g. the 'auto' backend) actually see it.
        if not _has_gpu():
            raise RuntimeError("no GPU visible to TensorFlow in the worker process "
                                "(tf.config.list_physical_devices('GPU') is empty)")
        from collage.steps._scorer import get_scorer
        scorer = get_scorer(scorer_name, model_path)
        scorer.load()
    except Exception as e:
        try:
            with open(ready_path + ".error", "w") as f:
                f.write(repr(e))
        except OSError:
            pass
        return
    open(ready_path, "w").close()  # signal: model loaded, ready for work

    while True:
        jobs = sorted(glob.glob(os.path.join(jobs_dir, "*.job")))
        if not jobs:
            if os.path.exists(stop_path):
                break
            _t.sleep(poll_s)
            continue
        for jobfile in jobs:
            try:
                with open(jobfile, "rb") as f:
                    im_pairs, export_consen_ima, output_path = pickle.load(f)
            except Exception:
                continue  # incomplete file; will retry next scan
            try:
                method2ia_red, final_method = score_job_batched(scorer, im_pairs, export_consen_ima)
                payload = {"method2ia_red": method2ia_red, "final_method": final_method}
            except Exception as e:
                import traceback as _tb
                payload = {"method2ia_red": {}, "final_method": None, "error": repr(e),
                           "traceback": _tb.format_exc()}
            try:
                _write_result_atomic(output_path, payload)
            except Exception:
                pass
            try:
                os.remove(jobfile)
            except OSError:
                pass


class GPUService:
    """A single spawned, GPU-resident scorer worker fed via a filesystem job queue."""

    def __init__(self, scorer_name, model_path, output_root, start_timeout_s=300.0):
        self.scorer_name = scorer_name
        self.model_path = model_path
        self.output_root = output_root
        self.jobs_dir = os.path.join(output_root, "_gpu_jobs")
        self.results_dir = os.path.join(output_root, "_pool_results")
        self.ready_path = os.path.join(self.jobs_dir, "_ready")
        self.stop_path = os.path.join(self.jobs_dir, "_stop")
        self.start_timeout_s = start_timeout_s
        self._ctx = mp.get_context("spawn")  # spawn, NOT fork -- clean CUDA init
        self._worker = None

    def start(self):
        os.makedirs(self.jobs_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)
        for p in (self.ready_path, self.ready_path + ".error", self.stop_path):
            try:
                os.remove(p)
            except OSError:
                pass
        self._worker = self._ctx.Process(
            target=_gpu_worker_main,
            args=(self.scorer_name, self.model_path, self.jobs_dir,
                  self.ready_path, self.stop_path),
            daemon=True,
        )
        self._worker.start()
        deadline = time.time() + self.start_timeout_s
        while True:
            if os.path.exists(self.ready_path):
                break
            if os.path.exists(self.ready_path + ".error"):
                msg = open(self.ready_path + ".error").read()
                self.shutdown()
                raise RuntimeError(f"GPU inference worker failed to load the scorer: {msg}")
            if not self._worker.is_alive():
                self.shutdown()
                raise RuntimeError("GPU inference worker died during startup (see log above).")
            if time.time() > deadline:
                self.shutdown()
                raise TimeoutError(f"GPU worker not ready within {self.start_timeout_s}s.")
            time.sleep(0.05)
        return self

    def submit(self, im_pairs, export_consen_ima):
        job_id = uuid.uuid4().hex
        output_path = os.path.join(self.results_dir, job_id + ".pkl")
        tmp = os.path.join(self.jobs_dir, job_id + ".job.tmp")
        final = os.path.join(self.jobs_dir, job_id + ".job")
        with open(tmp, "wb") as f:
            pickle.dump((im_pairs, export_consen_ima, output_path), f)
        os.replace(tmp, final)  # atomic: worker only ever sees a complete .job
        return _FileFuture(output_path)

    def shutdown(self, timeout=30.0):
        try:
            open(self.stop_path, "w").close()
        except OSError:
            pass
        if self._worker is not None:
            self._worker.join(timeout=timeout)
            if self._worker.is_alive():
                self._worker.terminate()
        self._worker = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.shutdown()
