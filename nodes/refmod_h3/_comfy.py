"""Import-safe accessors for ComfyUI services.

Every helper degrades gracefully when ComfyUI is not importable (tests, linters).
ComfyUI modules are only ever imported lazily inside functions.
"""
from __future__ import annotations

import importlib
import logging
import os
import tempfile
from types import ModuleType

import torch

log = logging.getLogger("jezzwtf.refmod_h3")

PACK_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def optional_module(name: str) -> ModuleType | None:
    """Import a module by name, returning None when it is unavailable."""
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def comfy_nodes() -> ModuleType | None:
    """ComfyUI's top-level ``nodes`` module (never this pack's ``nodes`` package)."""
    mod = optional_module("nodes")
    if mod is None or not hasattr(mod, "NODE_CLASS_MAPPINGS") or not hasattr(mod, "common_ksampler"):
        return None
    return mod


def folder_paths_mod() -> ModuleType | None:
    return optional_module("folder_paths")


def models_dir() -> str:
    fp = folder_paths_mod()
    if fp is not None:
        return str(fp.models_dir)
    return os.path.join(tempfile.gettempdir(), "jezzwtf_models")


def folder_paths_for(name: str) -> list[str]:
    fp = folder_paths_mod()
    if fp is None:
        return []
    try:
        return [str(p) for p in fp.get_folder_paths(name)]
    except Exception:
        return []


def filename_list(name: str) -> list[str]:
    fp = folder_paths_mod()
    if fp is None:
        return []
    try:
        return [str(p) for p in fp.get_filename_list(name)]
    except Exception:
        return []


def full_path(folder: str, filename: str) -> str | None:
    fp = folder_paths_mod()
    if fp is None:
        return None
    try:
        path = fp.get_full_path(folder, filename)
    except Exception:
        return None
    return str(path) if path else None


def register_model_folder(name: str, path: str) -> None:
    fp = folder_paths_mod()
    if fp is None:
        return
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    try:
        fp.add_model_folder_path(name, path)
    except Exception as exc:  # pragma: no cover - depends on ComfyUI version
        log.debug("add_model_folder_path(%s) failed: %s", name, exc)


def _dir(getter: str, fallback: str) -> str:
    fp = folder_paths_mod()
    if fp is not None:
        try:
            return str(getattr(fp, getter)())
        except Exception:
            pass
    path = os.path.join(tempfile.gettempdir(), fallback)
    os.makedirs(path, exist_ok=True)
    return path


def input_dir() -> str:
    return _dir("get_input_directory", "jezzwtf_input")


def output_dir() -> str:
    return _dir("get_output_directory", "jezzwtf_output")


def temp_dir() -> str:
    return _dir("get_temp_directory", "jezzwtf_temp")


def prompt_server() -> object | None:
    server = optional_module("server")
    if server is None:
        return None
    return getattr(getattr(server, "PromptServer", None), "instance", None)


def send_sync(event: str, data: dict[str, object], to_client: bool = False) -> None:
    """Send a websocket event; broadcast unless ``to_client`` targets the current client."""
    inst = prompt_server()
    if inst is None:
        return
    try:
        sid = getattr(inst, "client_id", None) if to_client else None
        inst.send_sync(event, data, sid)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - transport errors are not fatal
        log.debug("send_sync(%s) failed: %s", event, exc)


def intermediate_device() -> torch.device:
    mm = optional_module("comfy.model_management")
    if mm is None:
        return torch.device("cpu")
    try:
        return mm.intermediate_device()
    except Exception:
        return torch.device("cpu")


def progress_bar(total: int) -> object | None:
    utils = optional_module("comfy.utils")
    if utils is None:
        return None
    try:
        return utils.ProgressBar(total)
    except Exception:
        return None


def progress_update(bar: object | None, value: int, total: int) -> None:
    if bar is None:
        return
    try:
        bar.update_absolute(value, total)  # type: ignore[attr-defined]
    except Exception:
        pass


def common_upscale(images_bchw: torch.Tensor, width: int, height: int, method: str, crop: str) -> torch.Tensor:
    """``comfy.utils.common_upscale`` with a plain-torch fallback (tests / no ComfyUI).

    Input and output are ``[B, C, H, W]``.
    """
    utils = optional_module("comfy.utils")
    if utils is not None and hasattr(utils, "common_upscale"):
        return utils.common_upscale(images_bchw, width, height, method, crop)
    x = images_bchw
    if crop == "center":
        _, _, h, w = x.shape
        old_aspect = w / h
        new_aspect = width / height
        if old_aspect > new_aspect:
            cut = int(round(w - h * new_aspect)) // 2
            x = x[:, :, :, cut: w - cut] if cut > 0 else x
        elif old_aspect < new_aspect:
            cut = int(round(h - w / new_aspect)) // 2
            x = x[:, :, cut: h - cut, :] if cut > 0 else x
    mode = {"lanczos": "bicubic", "nearest-exact": "nearest-exact", "bilinear": "bilinear",
            "bicubic": "bicubic", "area": "area"}.get(method, "bilinear")
    kwargs: dict[str, bool] = {}
    if mode in ("bilinear", "bicubic"):
        kwargs = {"align_corners": False, "antialias": True}
    return torch.nn.functional.interpolate(x.float(), size=(height, width), mode=mode, **kwargs).to(images_bchw.dtype)


def call_node(cls: type, **kwargs: object) -> tuple[object, ...]:
    """Run a ComfyUI node class (V3 ``execute`` classmethod, V1 ``FUNCTION`` or a bare
    ``execute``), keeping only the kwargs its signature accepts, and return its outputs
    as a plain tuple (V3 ``NodeOutput.args`` is unwrapped)."""
    import inspect

    if hasattr(cls, "define_schema") and callable(getattr(cls, "execute", None)):
        fn = getattr(cls, "execute")
    else:
        name = getattr(cls, "FUNCTION", None)
        if not isinstance(name, str) or not hasattr(cls, name):
            name = "execute"
        if not hasattr(cls, name):
            raise AttributeError(f"{cls.__name__} has no callable entry point")
        fn = getattr(cls, name)
        if inspect.isfunction(fn):
            fn = getattr(cls(), name)
    params = inspect.signature(fn).parameters
    accepts_any = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
    use = {k: v for k, v in kwargs.items() if accepts_any or k in params}
    out = fn(**use)
    args = getattr(out, "args", None)
    if args is not None:
        return tuple(args)
    if isinstance(out, dict) and "result" in out:
        return tuple(out["result"])
    if isinstance(out, (tuple, list)):
        return tuple(out)
    return (out,)
