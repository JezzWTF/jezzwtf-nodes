"""Make `refmod_h3` importable as a top-level package without ComfyUI, and isolate disk state."""
from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

_NODES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "nodes"))
if _NODES not in sys.path:
    sys.path.insert(0, _NODES)


@pytest.fixture()
def refmod_root(tmp_path: Path) -> Iterator[str]:
    """A temporary refmods folder that is the only library search dir and the save root."""
    from refmod_h3 import library

    root = os.path.join(str(tmp_path), "refmods")
    os.makedirs(root)
    library.set_search_dirs_override([root])
    library.MOD_CACHE.clear()
    try:
        yield root
    finally:
        library.set_search_dirs_override(None)
        library.MOD_CACHE.clear()


@pytest.fixture(autouse=True)
def isolate_refmod_folders(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """No test may write into a real models/refmods folder: default every test to a temp one."""
    from refmod_h3 import library

    root = str(tmp_path_factory.mktemp("auto_refmods"))
    library.set_search_dirs_override([root])
    library.MOD_CACHE.clear()
    try:
        yield
    finally:
        library.set_search_dirs_override(None)
        library.MOD_CACHE.clear()


@pytest.fixture(autouse=True)
def no_gpu_model_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    """The audio extractor asks ComfyUI to load the audio VAE; tests use CPU stand-ins instead."""
    from refmod_h3 import _comfy

    mm = _comfy.optional_module("comfy.model_management")
    if mm is not None and hasattr(mm, "load_models_gpu"):
        monkeypatch.setattr(mm, "load_models_gpu", lambda *args, **kwargs: None)
