"""Import nodes/video_compare.py without ComfyUI: it only needs a `folder_paths` module at import time."""
from __future__ import annotations

import os
import sys
import types

_NODES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "nodes"))
if _NODES not in sys.path:
    sys.path.insert(0, _NODES)
sys.modules.setdefault("folder_paths", types.ModuleType("folder_paths"))

_TESTS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)

import v3_helpers  # noqa: E402

v3_helpers.install_default_hidden()
