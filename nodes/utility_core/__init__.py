"""JezzWTF utility-core node family.

Each feature module loads inside its own try/except so one broken module can't
block the rest. Modules (or their display labels) listed one per line in
`jezzwtf_disabled.txt` next to this file are skipped; `#` starts a comment.
"""
from __future__ import annotations

import importlib
import logging
import os
from collections.abc import Callable
from types import ModuleType

log = logging.getLogger("jezzwtf.utility_core")

MODULES: tuple[tuple[str, str], ...] = (
    ("set_get", "Set / Get"),
    ("text_nodes", "Text"),
    ("get_image", "Get Image"),
    ("match_size", "Match Image Size"),
    ("duration_frames", "Duration to Frames"),
    ("timer", "Batch Timer"),
    ("resolution", "Resolution Picker"),
    ("folder_batch", "Folder Batch"),
    ("refresh_page", "Refresh Page"),
    ("draw_image", "Draw Image"),
    ("multi_load", "Multi Load Image"),
)
_ROUTES_FLAG = "_jezzwtf_utility_core_routes"


def _disabled() -> set[str]:
    path = os.path.join(os.path.dirname(__file__), "jezzwtf_disabled.txt")
    try:
        with open(path, encoding="utf-8") as fh:
            lines = [ln.split("#", 1)[0].strip().casefold() for ln in fh]
    except OSError:
        return set()
    return {ln for ln in lines if ln}


def _register_routes(modules: list[ModuleType]) -> None:
    try:
        import server  # type: ignore[import-not-found]

        inst = getattr(server.PromptServer, "instance", None)
    except Exception:
        return  # not running inside ComfyUI
    if inst is None or getattr(inst, _ROUTES_FLAG, False):
        return
    for mod in modules:
        register: Callable[..., None] | None = getattr(mod, "register_routes", None)
        if register is None:
            continue
        try:
            register(inst.routes)
        except Exception as exc:
            log.warning("utility_core: routes for %s failed: %s", mod.__name__, exc)
    setattr(inst, _ROUTES_FLAG, True)


NODE_CLASS_MAPPINGS: dict[str, type] = {}
NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {}

_skip = _disabled()
_loaded: list[ModuleType] = []
for _name, _label in MODULES:
    if _name.casefold() in _skip or _label.casefold() in _skip:
        log.info("utility_core: %s disabled", _name)
        continue
    try:
        _mod = importlib.import_module(f".{_name}", __name__)
    except Exception as _exc:
        log.warning("utility_core: failed to load %s: %s", _name, _exc)
        continue
    NODE_CLASS_MAPPINGS.update(getattr(_mod, "NODE_CLASS_MAPPINGS", {}))
    NODE_DISPLAY_NAME_MAPPINGS.update(getattr(_mod, "NODE_DISPLAY_NAME_MAPPINGS", {}))
    _loaded.append(_mod)

_register_routes(_loaded)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
