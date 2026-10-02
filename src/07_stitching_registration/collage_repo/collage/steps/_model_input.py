"""Pack reference/query arrays for two-channel or legacy RGB classifiers.

No TensorFlow import: safe in the parent of forked scoring workers.
"""
import numpy as np


def model_channels(model):
    shape = model.input_shape
    if isinstance(shape, list) or len(shape) != 4 or shape[-1] not in (2, 3):
        raise ValueError(f"Expected a single NHWC model with 2 or 3 channels, got {shape}")
    return int(shape[-1])


def pack_pair(reference, query, model):
    """Accept HxW patches or NxHxW batches; preserve dtype and normalization."""
    if reference.shape != query.shape or reference.ndim not in (2, 3):
        raise ValueError("Reference/query must have matching HxW or NxHxW shapes")
    arrays = [reference, query]
    if model_channels(model) == 3:
        arrays.append(np.zeros_like(reference))
    return np.stack(arrays, axis=-1)
