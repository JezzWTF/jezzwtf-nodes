"""HTTP routes for the Gallery window: a folder listing. Thumbnails come from ComfyUI's own /view?preview=."""
from __future__ import annotations

import logging

from aiohttp import web

from . import listing

log = logging.getLogger("jezzwtf.gallery")


async def list_handler(request: web.Request) -> web.Response:
    kind = request.query.get("type", "input")
    folder = request.query.get("folder", "")
    query = request.query.get("q", "")
    try:
        return web.json_response(listing.list_folder(kind, folder, query))
    except OSError as exc:
        return web.json_response({"error": str(exc)}, status=500)


def register_with_server() -> bool:
    try:
        from server import PromptServer  # type: ignore[import-not-found]

        instance = getattr(PromptServer, "instance", None)
        if instance is None:
            return False
        instance.routes.get("/jezzwtf/gallery/list")(list_handler)
        return True
    except Exception as exc:  # noqa: BLE001 - running outside ComfyUI
        log.debug("jezzwtf gallery: routes not registered (%s)", exc)
        return False
