"""aiohttp routes for the RefMod family (spec sections 7.13, 8.6 and 15). Registered once, only inside ComfyUI."""
from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import TypeVar

from . import _comfy
from . import library, unified
from ._types import RefModError

log = _comfy.log
T = TypeVar("T")
_registered = False


def h3_thumb_bytes(name: str) -> bytes | None:
    """The thumbnail sidecar (``.jezzwtf.jpg``) of an H3 library entry, or None (invalid name / no thumbnail)."""
    try:
        library.check_rel(str(name))
    except RefModError:
        return None
    stem = library.resolve_stem(str(name))
    if stem is None:
        return None
    try:
        with open(library.thumb_path(stem), "rb") as fh:
            return fh.read()
    except OSError:
        return None


def register_routes() -> bool:
    """Register the ``/jezzwtf/refmods*`` and ``/jezzwtf/refmod_lib*`` routes. False outside ComfyUI."""
    global _registered
    if _registered:
        return True
    inst = _comfy.prompt_server()
    routes = getattr(inst, "routes", None)
    if routes is None:
        return False
    try:
        from aiohttp import web
    except ImportError:
        return False

    async def in_thread(fn: Callable[..., T], *args: object) -> T:
        return await asyncio.get_running_loop().run_in_executor(None, fn, *args)

    @routes.get("/jezzwtf/refmods")
    async def refmods(_request: web.Request) -> web.Response:
        try:
            return web.json_response(await in_thread(library.library_entries))
        except Exception as exc:
            log.warning("refmods listing failed: %s", exc)
            return web.json_response({"error": str(exc)}, status=500)

    @routes.get("/jezzwtf/refmods/thumb")
    async def refmods_thumb(request: web.Request) -> web.Response:
        data = await in_thread(h3_thumb_bytes, request.query.get("name", ""))
        if data is None:
            return web.Response(status=404)
        return web.Response(body=data, content_type="image/jpeg", headers={"Cache-Control": "no-cache"})

    @routes.get("/jezzwtf/refmod_lib")
    async def refmod_lib(_request: web.Request) -> web.Response:
        return web.json_response(await in_thread(unified.library_payload))

    @routes.get("/jezzwtf/refmod_lib/thumb")
    async def refmod_lib_thumb(request: web.Request) -> web.Response:
        try:
            data = await in_thread(unified.thumb_bytes, request.query.get("name", ""))
        except Exception as exc:
            log.debug("refmod_lib thumb failed: %s", exc)
            data = None
        if data is None:
            return web.Response(status=404)
        return web.Response(body=data, content_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})

    _registered = True
    return True
