"""Thin, import-safe accessors for ComfyUI services.

Every function degrades gracefully when ComfyUI isn't importable (tests, linters).
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import tempfile
from typing import TYPE_CHECKING

import torch

if TYPE_CHECKING:
    from aiohttp import web

log = logging.getLogger("jezzwtf.utility_core")

def prompt_server() -> object | None:
    try:
        import server  # type: ignore[import-not-found]
    except Exception:
        return None
    return getattr(server.PromptServer, "instance", None)


def send_sync(event: str, data: dict[str, object]) -> None:
    inst = prompt_server()
    if inst is None:
        return
    try:
        inst.send_sync(event, data)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - transport errors are not fatal
        log.debug("send_sync(%s) failed: %s", event, exc)


def current_prompt_id() -> str | None:
    """Id of the prompt ComfyUI is executing (or last started); None outside a server."""
    pid = getattr(prompt_server(), "last_prompt_id", None)
    return None if pid is None else str(pid)


def queue_busy() -> bool | None:
    """Whether ComfyUI is executing a prompt right now; None when the queue can't be inspected."""
    queue = getattr(prompt_server(), "prompt_queue", None)
    getter = getattr(queue, "get_current_queue_volatile", None) or getattr(queue, "get_current_queue", None)
    if not callable(getter):
        return None
    try:
        running = getter()[0]
    except Exception:
        return None
    return bool(running)


def temp_dir() -> str:
    try:
        import folder_paths  # type: ignore[import-not-found]

        path = str(folder_paths.get_temp_directory())
    except Exception:
        path = os.path.join(tempfile.gettempdir(), "jezzwtf_temp")
    os.makedirs(path, exist_ok=True)
    return path


def input_dir() -> str:
    try:
        import folder_paths  # type: ignore[import-not-found]

        return str(folder_paths.get_input_directory())
    except Exception:
        path = os.path.join(tempfile.gettempdir(), "jezzwtf_input")
        os.makedirs(path, exist_ok=True)
        return path


def intermediate_device() -> torch.device:
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]

        return mm.intermediate_device()
    except Exception:
        return torch.device("cpu")


def intermediate_dtype() -> torch.dtype:
    """`comfy.model_management.intermediate_dtype()` (honours --fp16-intermediates); float32 without ComfyUI."""
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]

        return mm.intermediate_dtype()
    except Exception:
        return torch.float32


def upscale(samples: torch.Tensor, width: int, height: int, method: str, crop: str) -> torch.Tensor:
    """`comfy.utils.common_upscale` with a plain-torch fallback for tests."""
    try:
        import comfy.utils  # type: ignore[import-not-found]

        return comfy.utils.common_upscale(samples, width, height, method, crop)
    except ImportError:
        pass
    s = samples
    if crop == "center":
        ow, oh = s.shape[-1], s.shape[-2]
        oa, na = ow / oh, width / height
        x = y = 0
        if oa > na:
            x = round((ow - ow * (na / oa)) / 2)
        elif oa < na:
            y = round((oh - oh * (oa / na)) / 2)
        s = s.narrow(-2, y, oh - y * 2).narrow(-1, x, ow - x * 2)
    mode = {"lanczos": "bicubic", "bislerp": "bilinear"}.get(method, method)
    kwargs: dict[str, bool] = {"align_corners": False} if mode in ("bilinear", "bicubic") else {}
    return torch.nn.functional.interpolate(s, size=(height, width), mode=mode, **kwargs)


# ---------------------------------------------------------------- request helpers

_LOOPBACK_NAMES = frozenset({"localhost"})


def _is_loopback_host(host: str) -> bool:
    candidate = host.strip().strip("[]").lower()
    if not candidate:
        return False
    if candidate in _LOOPBACK_NAMES:
        return True
    try:
        ip = ipaddress.ip_address(candidate.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped.is_loopback
    return ip.is_loopback


def _hostname_of_host_header(host: str) -> str:
    host = host.strip()
    if host.startswith("["):
        end = host.find("]")
        return host[1:end] if end > 0 else ""
    if host.count(":") == 1:
        return host.split(":", 1)[0]
    return host


def is_loopback_request(remote: str | None, host_header: str | None) -> bool:
    """True only when the peer is a loopback address and the Host header names a loopback host."""
    if not remote or not _is_loopback_host(remote):
        return False
    return bool(host_header) and _is_loopback_host(_hostname_of_host_header(host_header or ""))


async def read_json_object(request: "web.Request") -> dict[str, object] | None:
    """Parse a JSON object body; None for anything malformed, non-object or too deeply nested."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    return body if isinstance(body, dict) else None
