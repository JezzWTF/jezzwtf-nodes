"""aiohttp routes for the model-loader family. Registered once, only inside ComfyUI."""
from __future__ import annotations

import asyncio
import json

from ._comfy import folder_roots, log, lora_names, prompt_server

_registered = False


def register_routes() -> bool:
    global _registered
    if _registered:
        return True
    inst = prompt_server()
    routes = getattr(inst, "routes", None)
    if routes is None:
        return False
    try:
        from aiohttp import web
    except ImportError:
        return False

    from .diffusers_loader import list_models
    from .inspector import run_inspection
    from .lora_stack_logic import folder_files, folder_listing, list_subfolders

    @routes.get("/jezzwtf/loras")
    async def jezzwtf_loras(_request: web.Request) -> web.Response:
        try:
            return web.json_response([n.replace("\\", "/") for n in lora_names()])
        except Exception:
            return web.json_response([])

    @routes.get("/jezzwtf/lora_folders")
    async def jezzwtf_lora_folders(_request: web.Request) -> web.Response:
        try:
            return web.json_response({"folders": list_subfolders(folder_roots("loras"))})
        except Exception:
            return web.json_response({"folders": []})

    @routes.get("/jezzwtf/lora_folder")
    async def jezzwtf_lora_folder(request: web.Request) -> web.Response:
        folder = request.query.get("folder", "")
        try:
            files = folder_files(folder_roots("loras"), folder)
            return web.json_response({"folder": folder, "loras": folder_listing(files)})
        except Exception as exc:
            return web.json_response({"folder": folder, "loras": [], "error": str(exc)})

    @routes.get("/jezzwtf/diffusers_models")
    async def jezzwtf_diffusers_models(_request: web.Request) -> web.Response:
        try:
            names = await asyncio.get_running_loop().run_in_executor(None, list_models)
            return web.json_response(names)
        except Exception:
            return web.json_response([])

    @routes.post("/jezzwtf/lora_inspector/inspect")
    async def jezzwtf_lora_inspect(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except (ValueError, json.JSONDecodeError):
            body = {}
        if not isinstance(body, dict):
            body = {}
        lora = str(body.get("lora") or "")
        if not lora:
            return web.json_response({"error": "missing 'lora'"}, status=400)
        source = str(body.get("source") or "auto")
        client_id = str(body.get("client_id") or "") or None
        node = str(body.get("node") or "0")
        force = str(body.get("force") or "0") in ("1", "true", "True")
        try:
            payload = await asyncio.get_running_loop().run_in_executor(
                None, run_inspection, lora, source, node, force, client_id)
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response(payload)

    _registered = True
    log.debug("jezzwtf model-loader routes registered")
    return True
