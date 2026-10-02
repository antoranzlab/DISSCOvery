"""NumPy compatibility shim.

Several registration libraries COLLAGE relies on (notably imreg_dft, and some
older releases of astroalign / image_registration) still use NumPy aliases that
were deprecated in 1.20 and *removed* in 1.24 -- e.g. ``np.bool``, ``np.int``,
``np.float``. On numpy >= 1.24 these raise ``AttributeError`` at runtime (for
imreg_dft, inside ``utils.get_borderval`` during ``transform_img``).

COLLAGE pins ``numpy < 2`` for TensorFlow, but that range still includes 1.24-1.26
where the aliases are gone. Rather than pin numpy down to the ancient 1.23, we
restore the removed aliases to their builtin equivalents here. This changes no
behaviour -- the aliases were always just the Python builtins -- and lets the
unmodified third-party libraries run across the whole supported numpy range.

Imported for its side effects by ``collage/__init__.py`` (and defensively by the
step modules, so forked/spawned workers are covered too).
"""
from __future__ import annotations

import warnings

import numpy as _np

# Removed-in-1.24 aliases -> their builtin equivalents.
_ALIASES = {
    "bool": bool,
    "int": int,
    "float": float,
    "complex": complex,
    "object": object,
    "str": str,
    "unicode": str,
}

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    for _name, _builtin in _ALIASES.items():
        if not hasattr(_np, _name):
            setattr(_np, _name, _builtin)


# collections ABC compatibility shim.
#
# thunder-registration (the optional CrossCorr backend) depends on the old
# bolt-python, which still does ``from collections import Iterable`` -- a name
# that moved to ``collections.abc`` in Python 3.3 and was *removed* from
# ``collections`` in Python 3.10. On the 3.10 env this raises ImportError before
# CrossCorr can be imported, so the thunder method silently never runs.
#
# Rather than edit the installed bolt package, restore the ABCs onto the
# ``collections`` module for 3.10+. The names are unchanged objects (just
# relocated), so this alters no behaviour; it only lets the unmodified old
# dependency import. Applied for its side effects, like the numpy shim above.
import collections as _collections  # noqa: E402
import collections.abc as _collections_abc  # noqa: E402

for _abc in ("Iterable", "Mapping", "MutableMapping", "Sequence", "Callable",
             "Set", "MutableSet", "MutableSequence", "Hashable"):
    if not hasattr(_collections, _abc) and hasattr(_collections_abc, _abc):
        setattr(_collections, _abc, getattr(_collections_abc, _abc))
