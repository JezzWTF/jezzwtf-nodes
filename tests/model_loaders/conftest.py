"""Make `model_loaders` importable as a top-level package without ComfyUI."""
from __future__ import annotations

import os
import sys

_NODES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "nodes"))
if _NODES not in sys.path:
    sys.path.insert(0, _NODES)
