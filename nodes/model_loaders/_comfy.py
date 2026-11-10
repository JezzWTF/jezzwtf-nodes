"""Import-safe accessors for ComfyUI services used by the model-loader family.

Nothing here imports ComfyUI at module load, so the pure-logic modules (and the
tests) work without a ComfyUI install.
"""
from __future__ import annotations

import logging
import os
import tempfile

log = logging.getLogger("jezzwtf.model_loaders")

PACK_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CATEGORY_LOADERS = "JezzWTF/loaders"
CATEGORY_LORA = "JezzWTF/lora"
CATEGORY_VIDEO = "JezzWTF/video"


def prompt_server() -> object | None:
    try:
        import server  # type: ignore[import-not-found]
    except Exception:
        return None
    return getattr(server.PromptServer, "instance", None)


def send_sync(event: str, data: dict[str, object], sid: str | None = None) -> None:
    """Send a websocket event to `sid` (the requesting client) when known, else to the client
    whose prompt ComfyUI is executing."""
    inst = prompt_server()
    if inst is None:
        return
    try:
        target = sid or getattr(inst, "client_id", None)
        inst.send_sync(event, data, target)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - transport errors are not fatal
        log.debug("send_sync(%s) failed: %s", event, exc)


def user_cache_dir() -> str:
    """`<ComfyUI user dir>/jezzwtf_cache`, created on demand."""
    try:
        import folder_paths  # type: ignore[import-not-found]

        base = str(folder_paths.get_user_directory())
    except Exception:
        base = os.path.join(tempfile.gettempdir(), "jezzwtf_user")
    path = os.path.join(base, "jezzwtf_cache")
    os.makedirs(path, exist_ok=True)
    return path


def lora_names() -> list[str]:
    try:
        import folder_paths  # type: ignore[import-not-found]

        return [str(n) for n in folder_paths.get_filename_list("loras")]
    except Exception:
        return []


def lora_full_path(name: str) -> str | None:
    try:
        import folder_paths  # type: ignore[import-not-found]

        p = folder_paths.get_full_path("loras", name)
        return str(p) if p else None
    except Exception:
        return None


def folder_roots(folder: str) -> list[str]:
    try:
        import folder_paths  # type: ignore[import-not-found]

        return [str(p) for p in folder_paths.get_folder_paths(folder)]
    except Exception:
        return []
