"""Refresh Page (VRAM cleaner): pass-through node that frees VRAM and caches."""
from __future__ import annotations

import gc
import time
from typing import TYPE_CHECKING, TypedDict

import torch

from ._comfy import prompt_server, read_json_object
from ._types import ANY, CATEGORY_UTILS, InputTypes

if TYPE_CHECKING:
    from aiohttp import web

KITCHEN_CHOICES = ("leave as is", "auto", "cuda", "triton", "eager")
DEFAULT_PRIORITY = ["ascend", "cuda", "triton", "eager"]
UI_KEY = "jezzwtf_vram"

_original_priority: list[str] | None = None


class CleanStats(TypedDict):
    device: str
    total: int
    free_before: int
    free_after: int
    freed: int
    ms: float
    notes: list[str]


class KitchenInfo(TypedDict, total=False):
    installed: bool
    priority: list[str]
    backends: dict[str, bool]
    error: str


def _device() -> torch.device:
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]

        return mm.get_torch_device()
    except Exception:
        return torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")


def mem_info(device: torch.device) -> tuple[int, int]:
    """(free, total) in bytes; zeros when the device isn't CUDA."""
    if device.type != "cuda" or not torch.cuda.is_available():
        return (0, 0)
    try:
        free, total = torch.cuda.mem_get_info(device)
        return (int(free), int(total))
    except Exception:
        return (0, 0)


def _kitchen_priority(ck: object) -> list[str]:
    registry = getattr(ck, "registry", None)
    current = getattr(registry, "_priority", None)
    return [str(x) for x in current] if isinstance(current, (list, tuple)) and current else list(DEFAULT_PRIORITY)


def _kitchen_backends(ck: object) -> dict[str, bool]:
    lister = getattr(ck, "list_backends", None)
    raw = lister() if callable(lister) else {}
    out: dict[str, bool] = {}
    if isinstance(raw, dict):
        for name, info in raw.items():
            if isinstance(info, dict):
                out[str(name)] = bool(info.get("available")) and not bool(info.get("disabled"))
    return out


def kitchen_info() -> KitchenInfo:
    try:
        import comfy_kitchen as ck  # type: ignore[import-not-found]
    except ImportError:
        return {"installed": False, "priority": [], "backends": {}}
    try:
        return {"installed": True, "priority": _kitchen_priority(ck), "backends": _kitchen_backends(ck)}
    except Exception as exc:
        return {"installed": True, "priority": [], "backends": {}, "error": str(exc)}


def apply_kitchen(choice: str, notes: list[str]) -> None:
    global _original_priority
    if choice == "leave as is":
        return
    try:
        import comfy_kitchen as ck  # type: ignore[import-not-found]
    except ImportError:
        notes.append("comfy_kitchen not installed")
        return
    try:
        if _original_priority is None:
            _original_priority = _kitchen_priority(ck)
        original = list(_original_priority)
        if choice == "auto":
            ck.set_backend_priority(original)
            notes.append("kitchen: priority restored")
            return
        raw = ck.list_backends()
        info = raw.get(choice) if isinstance(raw, dict) else None
        if not isinstance(info, dict) or not info.get("available"):
            reason = info.get("unavailable_reason") if isinstance(info, dict) else "not registered"
            notes.append(f"kitchen: {choice} unavailable ({reason})")
            return
        ck.enable_backend(choice)
        ck.set_backend_priority([choice] + [b for b in original if b != choice])
        notes.append(f"kitchen: {choice} first")
    except Exception as exc:
        notes.append(f"kitchen error: {exc}")


def clean(vram: bool = True, cache: bool = True, node_cache: bool = False, kitchen: str = "leave as is") -> CleanStats:
    t0 = time.perf_counter()
    device = _device()
    free_before, total = mem_info(device)
    notes: list[str] = []
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
    except ImportError:
        mm = None
    if vram:
        if mm is not None:
            mm.unload_all_models()
            notes.append("models unloaded")
        else:
            notes.append("model management unavailable")
    if vram or cache:
        gc.collect()
        try:
            if mm is None:
                raise RuntimeError("no model management")
            mm.soft_empty_cache(True)
        except Exception:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        notes.append("cache emptied")
    if node_cache:
        inst = prompt_server()
        queue = getattr(inst, "prompt_queue", None)
        setter = getattr(queue, "set_flag", None)
        if callable(setter):
            setter("free_memory", True)
            notes.append("node cache flagged")
        else:
            notes.append("prompt queue unavailable")
    apply_kitchen(kitchen, notes)
    free_after, total_after = mem_info(device)
    return {"device": str(device), "total": total or total_after, "free_before": free_before,
            "free_after": free_after, "freed": max(0, free_after - free_before),
            "ms": round((time.perf_counter() - t0) * 1000, 1), "notes": notes}


class JWTFRefreshPage:
    CATEGORY = CATEGORY_UTILS
    OUTPUT_NODE = True
    RETURN_TYPES = (ANY,)
    RETURN_NAMES = ("anything",)
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {
                "clean_vram": ("BOOLEAN", {"default": True}),
                "clear_cache": ("BOOLEAN", {"default": True}),
                "clear_node_cache": ("BOOLEAN", {"default": False}),
                "kitchen_backend": (list(KITCHEN_CHOICES), {"default": "leave as is"}),
            },
            "optional": {"anything": (ANY, {})},
        }

    @classmethod
    def IS_CHANGED(cls, **_: object) -> float:
        return float("nan")

    def run(self, clean_vram: bool, clear_cache: bool, clear_node_cache: bool, kitchen_backend: str,
            anything: object = None) -> dict[str, object]:
        stats = clean(clean_vram, clear_cache, clear_node_cache, kitchen_backend)
        return {"ui": {UI_KEY: [stats]}, "result": (anything,)}


def _queue_busy() -> bool:
    queue = getattr(prompt_server(), "prompt_queue", None)
    getter = getattr(queue, "get_current_queue", None)
    if not callable(getter):
        return False
    try:
        running = getter()[0]
    except Exception:
        return False
    return bool(running)


def register_routes(routes: "web.RouteTableDef") -> None:
    from aiohttp import web

    @routes.get("/jezzwtf/vram")
    async def _vram(_request: web.Request) -> web.Response:
        device = _device()
        free, total = mem_info(device)
        return web.json_response({"device": str(device), "total": total, "free": free,
                                  "used": max(0, total - free), "kitchen": kitchen_info()})

    @routes.post("/jezzwtf/clean")
    async def _clean(request: web.Request) -> web.Response:
        if _queue_busy():
            return web.json_response({"error": "busy"}, status=409)
        body = await read_json_object(request) or {}
        stats = clean(bool(body.get("vram", True)), bool(body.get("cache", True)),
                      bool(body.get("node_cache", False)), str(body.get("kitchen", "leave as is")))
        return web.json_response(stats)


NODE_CLASS_MAPPINGS = {"JWTFRefreshPage": JWTFRefreshPage}
NODE_DISPLAY_NAME_MAPPINGS = {"JWTFRefreshPage": "Refresh Page (VRAM Cleaner)"}
