"""Quiet TensorFlow's startup banner.

TF prints a wall of CUDA/cuDNN/cuFFT/cuBLAS factory-registration messages and
GPU-probe warnings the first time it initialises -- alarming-looking but
harmless on a CPU-only run. These env vars must be set BEFORE `import tensorflow`,
so callers invoke quiet_tf() immediately before importing TF.

This only silences logging; it does NOT disable the GPU. When the GPU build is in
use (Piece 3), TF still finds and uses the device -- we just don't print the
noise. So this is safe to leave in for the eventual GPU path.
"""
import os


def quiet_tf():
    # 3 = hide INFO, WARNING, and (the cuDNN/cuFFT/cuBLAS) ERROR factory spam.
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    os.environ.setdefault("TF_CPP_MIN_VLOG_LEVEL", "3")
    os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
    os.environ.setdefault("GLOG_minloglevel", "3")
    # Silence the TF-TRT "Could not find TensorRT" warning.
    os.environ.setdefault("TF_TRT_ALLOW_ENGINE_NATIVE_SEGMENT_EXECUTION", "0")
    # GPU memory hygiene: by default TF grabs ALL GPU memory on init, so two TF
    # processes on one GPU collide ("Dst tensor is not initialized"). Memory growth
    # makes each process take only what it needs, letting several coexist and
    # leaving room for the display. No-op on CPU-only builds.
    os.environ.setdefault("TF_FORCE_GPU_ALLOW_GROWTH", "true")
    try:
        from absl import logging as _absl_logging
        _absl_logging.set_verbosity(_absl_logging.ERROR)
    except Exception:
        pass


def force_cpu():
    """Hide the GPU from TensorFlow in THIS process (set before importing TF).

    Used by step 3: its per-tile workers are forked and each loads the model, so
    on a GPU they all race for device memory and hit RESOURCE_EXHAUSTED. Step 3's
    scoring is cheap and not inference-bound, so it runs the model on CPU and
    leaves the GPU entirely to step 2's single resident worker. No-op on a
    CPU-only machine.
    """
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
