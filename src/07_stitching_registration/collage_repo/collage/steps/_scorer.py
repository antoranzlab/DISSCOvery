"""Registration scorers: the model that scores a (reference, query) image pair.

This is the seam that decouples *what model scores a registration* from *how
inference is scheduled* (see _inference_service.py). The inference service treats
a scorer as an opaque "load once, then score pairs" object; swapping KimiaNet for
a future architecture (PVT, etc.) means adding another RegistrationScorer
implementation and a config value -- no change to the service or to step 2.

Scope for this version: patch-based scoring only (tile into fixed patches, score
each, average). A future whole-region scorer would be a new major version.

The KimiaNet scoring math here is lifted verbatim from the legacy
evaluate_overlap_function.py so output is pixel-identical; only its packaging
changed. TensorFlow is imported lazily inside load(), so importing this module
(e.g. in tests) does not require TF.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod

import numpy as np
from ._model_input import model_channels, pack_pair


def range_x1_q(x, q):
    """Percentile rescale to [0, 1] (verbatim from legacy)."""
    x = np.asarray(x, dtype=np.float64)
    tmp_median = np.median(x)
    tmp_q_high = np.percentile(x[(x > 0) & (x != tmp_median)], q)
    tmp_q_min = np.percentile(x[(x > 0) & (x != tmp_median)], 100 - q)
    x = (x - tmp_q_min) / (tmp_q_high - tmp_q_min)
    x[x > 1] = 1
    x[x < 0] = 0
    return x


class RegistrationScorer(ABC):
    """Loads a scoring model once, then scores (ref_path, query_path) pairs.

    Implementations must preserve these properties so they are interchangeable:
      * score() returns a float in [0, 1] (higher = better registration), or nan
        if the pair could not be scored.
      * load() is called exactly once per worker process before any score().
      * scoring is stateless across pairs (no carryover between score() calls).
    """

    name: str = "base"

    @abstractmethod
    def load(self) -> None:
        """Load model weights into this process. Called once per worker."""

    @abstractmethod
    def score(self, ref_path: str, query_path: str) -> float:
        """Score one (reference, query) image pair. Returns a float in [0, 1]."""


class KimiaNetScorer(RegistrationScorer):
    """AlignQC scorer: DenseNet/KimiaNet fine-tune, patch-based 256x256 scoring.

    Math is identical to the legacy evaluate_overlap_function.py per-pair loop.
    """

    name = "kimianet"
    PATCH = 256

    def __init__(self, model_path: str):
        self.model_path = model_path
        self._model = None
        self._img_to_array = None
        self._load_img = None

    def load(self) -> None:
        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
        try:
            from collage.steps._tf_env import quiet_tf
            quiet_tf()
        except Exception:
            pass
        from tensorflow.keras.models import load_model
        from tensorflow.keras.preprocessing.image import img_to_array, load_img
        self._model = load_model(self.model_path)
        self._img_to_array = img_to_array
        self._load_img = load_img

    def _prep(self, path: str) -> np.ndarray:
        img = self._img_to_array(self._load_img(path, color_mode="grayscale")) / 255.0
        img = np.arcsinh(2 ** 16 * img)
        img = range_x1_q(img, 99)
        return np.squeeze(img)

    def score(self, ref_path: str, query_path: str) -> float:
        if self._model is None:
            raise RuntimeError("KimiaNetScorer.load() must be called before score().")
        P = self.PATCH
        ref_image = self._prep(ref_path)
        query_image = self._prep(query_path)

        # Pad to a multiple of the patch size (verbatim from legacy).
        if ref_image.shape[0] % P > 0 or ref_image.shape[1] % P > 0:
            ref_image = np.pad(
                ref_image,
                ((0, P - ref_image.shape[0] % P), (0, P - ref_image.shape[1] % P)),
                "constant",
            )
            query_image = np.pad(
                query_image,
                ((0, P - query_image.shape[0] % P), (0, P - query_image.shape[1] % P)),
                "constant",
            )

        tmp_scores = []
        for tmp_r in range(0, ref_image.shape[0], P):
            for tmp_c in range(0, ref_image.shape[1], P):
                tmp_query = query_image[tmp_r:tmp_r + P, tmp_c:tmp_c + P]
                tmp_ref = ref_image[tmp_r:tmp_r + P, tmp_c:tmp_c + P]
                if np.mean(tmp_ref) == 0:
                    continue
                tmp_qc = pack_pair(tmp_ref, tmp_query, self._model)
                tmp_score = self._model.predict(tmp_qc[None, ...], verbose=0)
                tmp_scores.append(tmp_score[0, 0])

        return float(np.mean(tmp_scores))

    # --- Batched scoring (GPU path only) ---------------------------------------------
    # The per-patch score() above issues one model.predict per 256x256 patch. On a GPU
    # the fixed host<->device overhead of each call dwarfs the compute, so scoring one
    # patch at a time is slower than CPU. The methods below extract the SAME patches
    # (identical selection and arcsinh/range_x1_q/pad preprocessing) but run them
    # through the model in batches -- one predict over many patches -- which is what
    # makes the GPU win. The patches and the per-pair np.mean are unchanged, so scores
    # are identical to score() up to floating-point ordering (already within the
    # baseline tolerance). Used only by score_job_batched in the GPU worker; the CPU
    # paths keep the per-patch score() untouched.

    def extract_patches(self, ref_path: str, query_path: str) -> np.ndarray:
        """Return all non-blank 256x256x3 patches for a pair (no model call)."""
        if self._model is None:
            raise RuntimeError("KimiaNetScorer.load() must be called first.")
        P = self.PATCH
        ref_image = self._prep(ref_path)
        query_image = self._prep(query_path)
        if ref_image.shape[0] % P > 0 or ref_image.shape[1] % P > 0:
            ref_image = np.pad(
                ref_image,
                ((0, P - ref_image.shape[0] % P), (0, P - ref_image.shape[1] % P)),
                "constant",
            )
            query_image = np.pad(
                query_image,
                ((0, P - query_image.shape[0] % P), (0, P - query_image.shape[1] % P)),
                "constant",
            )
        patches = []
        for tmp_r in range(0, ref_image.shape[0], P):
            for tmp_c in range(0, ref_image.shape[1], P):
                tmp_ref = ref_image[tmp_r:tmp_r + P, tmp_c:tmp_c + P]
                tmp_query = query_image[tmp_r:tmp_r + P, tmp_c:tmp_c + P]
                if np.mean(tmp_ref) == 0:
                    continue
                patches.append(pack_pair(tmp_ref, tmp_query, self._model))
        if not patches:
            return np.empty((0, P, P, model_channels(self._model)), dtype=np.float64)
        return np.stack(patches, axis=0)

    def predict_patches(self, patches: np.ndarray, max_batch: int = 32) -> np.ndarray:
        """Run the model over a stack of patches in chunks; return per-patch scores.

        Uses predict_on_batch(), not predict(): measured via
        tf.config.experimental.get_memory_info across 80 repeated calls on real
        data, predict() both peaks ~2x higher per call AND leaks ~2MB/call net
        (it rebuilds a tf.data-based prediction loop internally every call).
        predict_on_batch() showed zero growth over that same 80-call probe --
        but that probe used one FIXED shape repeated 80x. Real jobs vary in
        patch count (4, 8, 12, 16, 17, 20, ...), so the *last* chunk of each
        job is a different size almost every time. Keras/TF traces a new
        concrete function per distinct input shape and never evicts old ones,
        so many distinct chunk sizes across many real jobs accumulate cached
        graphs until the GPU allocator fragments and can't serve even a ~6MB
        allocation (confirmed via full traceback from a live failing run:
        ResourceExhaustedError on an 8-image, ~6.6MB tensor with 5GB+ nominally
        free). Padding every chunk to a constant max_batch means TF traces
        ONCE, ever, for this scorer's whole process lifetime -- eliminating
        the accumulation. Padded rows are zeros (harmless: BatchNorm layers
        run in inference mode with pre-computed stats, not batch stats, so
        padding rows don't affect the real rows' predictions) and their
        outputs are discarded before returning.
        """
        if patches.shape[0] == 0:
            return np.empty((0,), dtype=np.float64)
        out = []
        for i in range(0, patches.shape[0], max_batch):
            chunk = patches[i:i + max_batch]
            n = chunk.shape[0]
            if n < max_batch:
                pad = np.zeros((max_batch - n,) + chunk.shape[1:], dtype=chunk.dtype)
                chunk = np.concatenate([chunk, pad], axis=0)
            pred = self._model.predict_on_batch(chunk)
            out.append(np.asarray(pred)[:n, 0])
        return np.concatenate(out, axis=0)

    def score_pairs_batched(self, pairs, max_batch: int = 8):
        """Score many (ref, query) pairs with batched inference.

        Returns one entry per pair: a float (mean patch score), nan (no patches),
        or an Exception instance (this pair failed during patch extraction). Errors
        are isolated per pair, matching score()'s per-pair try/except.
        """
        per_pair, errors = [], []
        for ref, qry in pairs:
            try:
                per_pair.append(self.extract_patches(ref, qry)); errors.append(None)
            except Exception as e:                      # noqa: BLE001 - isolate per pair
                per_pair.append(None); errors.append(e)
        counts = [0 if p is None else p.shape[0] for p in per_pair]
        good = [p for p in per_pair if p is not None and p.shape[0] > 0]
        flat = (self.predict_patches(np.concatenate(good, axis=0), max_batch)
                if good else np.empty((0,), dtype=np.float64))
        out, idx = [], 0
        for i, p in enumerate(per_pair):
            if errors[i] is not None:
                out.append(errors[i])
            elif counts[i] == 0:
                out.append(float("nan"))
            else:
                out.append(float(np.mean(flat[idx:idx + counts[i]])))
                idx += counts[i]
        return out


def get_scorer(name: str, model_path: str) -> RegistrationScorer:
    """Factory: map a config name to a scorer implementation."""
    name = (name or "kimianet").lower()
    if name == "kimianet":
        return KimiaNetScorer(model_path)
    raise ValueError(
        f"Unknown scorer '{name}'. Available: kimianet. "
        f"(New architectures are added as RegistrationScorer subclasses.)"
    )
