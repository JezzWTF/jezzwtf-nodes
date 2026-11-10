"""HTTP route for Paste Stack. Registered at import time, silently skipped outside ComfyUI."""

from __future__ import annotations

import asyncio
import logging

from . import clipboard

log = logging.getLogger("jezzwtf.paste_stack")

ROUTE_PATH = "/jezzwtf/paste_stack/clipboard"
HEADER_NAME = "X-JezzWTF-Paste"
HEADER_VALUE = "1"
COLLECT_TIMEOUT_S = 15.0

try:  # aiohttp ships with ComfyUI; absent in bare test environments
    from aiohttp import web
except Exception:  # noqa: BLE001
    web = None  # type: ignore[assignment]


async def handle_clipboard(request: "web.Request") -> "web.Response":
    """POST handler: header check, then locality check, then a threaded clipboard read."""
    if request.headers.get(HEADER_NAME) != HEADER_VALUE:
        return web.json_response({"files": [], "error": "forbidden"}, status=403)
    local = clipboard.is_local_caller(request.remote) and clipboard.is_local_request_origin(
        request.headers.get("Host"), request.headers.get("Origin")
    )
    if not local:
        return web.json_response({"files": [], "error": "not-local"}, status=403)
    loop = asyncio.get_running_loop()
    try:
        files = await asyncio.wait_for(
            loop.run_in_executor(None, clipboard.collect_clipboard_files), COLLECT_TIMEOUT_S
        )
    except Exception:  # noqa: BLE001 - includes timeout; empty list, status 200
        files = []
    return web.json_response({"files": files})


def register(routes: object) -> None:
    """Attach the POST route to an aiohttp RouteTableDef."""
    post = getattr(routes, "post")
    post(ROUTE_PATH)(handle_clipboard)


def register_with_server() -> bool:
    if web is None:
        return False
    try:
        from server import PromptServer  # type: ignore[import-not-found]

        instance = getattr(PromptServer, "instance", None)
        if instance is None:
            return False
        register(instance.routes)
        return True
    except Exception:  # noqa: BLE001 - not running inside ComfyUI
        return False
