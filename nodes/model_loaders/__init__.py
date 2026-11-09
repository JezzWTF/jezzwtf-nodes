"""Model-loader family: Diffusers loader, LoRA stacks, LoRA inspector, regional LoRA and Prompt Relay.

Each node module is imported in its own try/except so one failure doesn't take the rest down.
"""
from __future__ import annotations

import importlib

from ._comfy import log

NODE_CLASS_MAPPINGS: dict[str, type] = {}
NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {}

_NODES: tuple[tuple[str, str, str], ...] = (
    ("diffusers_loader", "JWTFDiffusersLoader", "Diffusers Loader"),
    ("lora_stack", "JWTFLoraStack", "LoRA Stack"),
    ("lora_stack", "JWTFLoraFolderStack", "LoRA Folder Stack"),
    ("lora_stack", "JWTFLoraFolderStackMulti", "LoRA Folder Stack (Multi-Model)"),
    ("inspector", "JWTFLoraInspector", "LoRA Inspector"),
    ("regional", "JWTFRegionalLoRA", "Regional Character LoRA"),
    ("relay", "JWTFPromptRelayEncode", "Prompt Relay Encode"),
    ("relay", "JWTFPromptRelayTimeline", "Prompt Relay Timeline"),
    ("relay", "JWTFPromptRelayOptions", "Prompt Relay Options"),
)

for _module, _cls, _display in _NODES:
    try:
        _mod = importlib.import_module(f".{_module}", __name__)
        NODE_CLASS_MAPPINGS[_cls] = getattr(_mod, _cls)
        NODE_DISPLAY_NAME_MAPPINGS[_cls] = _display
    except Exception as _exc:  # pragma: no cover - surfaced in the ComfyUI log
        log.warning("jezzwtf model_loaders: %s.%s unavailable: %s", _module, _cls, _exc)

try:
    from .routes import register_routes

    register_routes()
except Exception as _exc:  # pragma: no cover
    log.warning("jezzwtf model_loaders: routes not registered: %s", _exc)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
