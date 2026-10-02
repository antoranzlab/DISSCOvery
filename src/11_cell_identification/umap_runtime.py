"""Load ordinary UMAP without importing its unused neural-network backends."""

import sys


def load_umap():
    # umap.__init__ eagerly tries ParametricUMAP, pulling in TensorFlow and
    # PyTorch. These native libraries can segfault together in the integrated
    # environment, although ordinary UMAP needs neither of them.
    optional_module = "umap.parametric_umap"
    suppress_optional = optional_module not in sys.modules
    if suppress_optional:
        sys.modules[optional_module] = None
    try:
        import umap
        return umap
    finally:
        if suppress_optional:
            sys.modules.pop(optional_module, None)
