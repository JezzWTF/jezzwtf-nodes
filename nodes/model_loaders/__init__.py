"""Model-loader family: Diffusers loader, LoRA stacks, LoRA inspector, regional LoRA and Prompt Relay.

Each node module is imported in its own try/except so one failure doesn't take the rest down.
"""
from __future__ import annotations

import importlib

from comfy_api.latest import io

from ._comfy import log

NODES: list[type[io.ComfyNode]] = []

_MODULES: tuple[str, ...] = ("diffusers_loader", "lora_stack", "inspector", "regional", "relay")

for _module in _MODULES:
    try:
        NODES.extend(importlib.import_module(f".{_module}", __name__).NODES)
    except Exception as _exc:  # pragma: no cover - surfaced in the ComfyUI log
        log.warning("jezzwtf model_loaders: %s unavailable: %s", _module, _exc)

try:
    from .routes import register_routes

    register_routes()
except Exception as _exc:  # pragma: no cover
    log.warning("jezzwtf model_loaders: routes not registered: %s", _exc)

__all__ = ["NODES"]
