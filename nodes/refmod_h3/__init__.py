"""RefMod / MiniMax H3 family: RefMod bake/load/apply, tails, unified RefMods, card baker,
H3 image edit, live-preview samplers, upscale picker and the Ultimate Model Loader.

Each node module is imported in its own try/except so one failure doesn't take the rest down.
"""
from __future__ import annotations

import importlib

from comfy_api.latest import io

from ._comfy import log

NODES: list[type[io.ComfyNode]] = []

try:  # the refmods model folder must exist before any node's INPUT_TYPES lists it
    from .library import register_folder

    register_folder()
except Exception as _exc:  # pragma: no cover - depends on ComfyUI
    log.warning("jezzwtf refmod_h3: refmods folder not registered: %s", _exc)

_MODULES: tuple[str, ...] = (
    "h3_nodes",
    "unified",
    "card_baker",
    "image_edit",
    "samplers",
    "upscale_picker",
    "ultimate_loader",
)

for _name in _MODULES:
    try:
        _mod = importlib.import_module(f".{_name}", __name__)
        NODES.extend(_mod.NODES)
    except Exception as _exc:  # pragma: no cover - surfaced in the ComfyUI log
        log.warning("jezzwtf refmod_h3: %s unavailable: %s", _name, _exc)

try:
    from .routes import register_routes

    register_routes()
except Exception as _exc:  # pragma: no cover
    log.warning("jezzwtf refmod_h3: routes not registered: %s", _exc)

__all__ = ["NODES"]
