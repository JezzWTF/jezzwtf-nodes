"""Make `gallery` importable as a top-level package without ComfyUI."""
from __future__ import annotations

import os
import sys

_NODES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "nodes"))
if _NODES not in sys.path:
    sys.path.insert(0, _NODES)

_TESTS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)

import v3_helpers  # noqa: E402

v3_helpers.install_default_hidden()
