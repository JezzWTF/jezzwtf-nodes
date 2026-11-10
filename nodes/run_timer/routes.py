"""HTTP routes under /jezzwtf/run_timer/. Loopback callers only; registered at import time inside ComfyUI."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from .live import LIVE
from .store import HistoryStore, RecordError, StoreUnavailable, get_store, now_ms, parse_record

try:
    from ..utility_core._comfy import is_loopback_request, read_json_object
except ImportError:  # imported as a top-level package (tests)
    from utility_core._comfy import is_loopback_request, read_json_object  # type: ignore[no-redef]

try:  # aiohttp ships with ComfyUI; absent in bare environments
    from aiohttp import web
except Exception:  # noqa: BLE001
    web = None  # type: ignore[assignment]

log = logging.getLogger("jezzwtf.run_timer")

BASE = "/jezzwtf/run_timer"
HEADER_NAME = "X-JezzWTF-RunTimer"
HEADER_VALUE = "1"
MAX_BODY = 16 * 1024
DEFAULT_LIMIT = 500
_ROUTES_FLAG = "_jezzwtf_run_timer_routes"

StoreGetter = Callable[[], HistoryStore]
Handler = Callable[["web.Request"], Awaitable["web.Response"]]


def _reject(request: "web.Request", *, mutating: bool) -> "web.Response | None":
    if not is_loopback_request(request.remote, request.headers.get("Host")):
        return web.json_response({"error": "not-local"}, status=403)
    if mutating and request.headers.get(HEADER_NAME) != HEADER_VALUE:
        return web.json_response({"error": "forbidden"}, status=403)
    return None


def make_handlers(store_getter: StoreGetter = get_store) -> dict[str, Handler]:
    async def history(request: "web.Request") -> "web.Response":
        denied = _reject(request, mutating=False)
        if denied is not None:
            return denied
        try:
            limit = int(request.query.get("limit", DEFAULT_LIMIT))
        except ValueError:
            return web.json_response({"error": "limit must be an integer"}, status=400)
        runs = store_getter().snapshot(max(1, min(limit, DEFAULT_LIMIT)))
        return web.json_response({"now": now_ms(), "runs": runs})

    async def live(request: "web.Request") -> "web.Response":
        denied = _reject(request, mutating=False)
        if denied is not None:
            return denied
        now = now_ms()
        return web.json_response({"now": now, "runs": LIVE.snapshot(now)})

    async def record(request: "web.Request") -> "web.Response":
        denied = _reject(request, mutating=True)
        if denied is not None:
            return denied
        length = request.content_length
        if length is None or length > MAX_BODY:
            return web.json_response({"error": "body too large or missing length"}, status=413)
        body = await read_json_object(request)
        if body is None:
            return web.json_response({"error": "body must be a JSON object"}, status=400)
        try:
            parsed = parse_record(body)
        except RecordError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        try:
            stored, created = store_getter().add(parsed)
        except StoreUnavailable as exc:
            return web.json_response({"error": str(exc)}, status=503)
        return web.json_response({"run": stored, "duplicate": not created}, status=201 if created else 200)

    async def delete_one(request: "web.Request") -> "web.Response":
        denied = _reject(request, mutating=True)
        if denied is not None:
            return denied
        try:
            removed = store_getter().delete(request.match_info.get("id", ""))
        except StoreUnavailable as exc:
            return web.json_response({"error": str(exc)}, status=503)
        if not removed:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response({"deleted": True})

    async def clear(request: "web.Request") -> "web.Response":
        denied = _reject(request, mutating=True)
        if denied is not None:
            return denied
        try:
            count = store_getter().clear()
        except StoreUnavailable as exc:
            return web.json_response({"error": str(exc)}, status=503)
        return web.json_response({"cleared": count})

    return {"history": history, "live": live, "record": record, "delete_one": delete_one, "clear": clear}


def register(routes: object, store_getter: StoreGetter = get_store) -> None:
    """Attach the routes to an aiohttp RouteTableDef."""
    handlers = make_handlers(store_getter)
    getattr(routes, "get")(f"{BASE}/history")(handlers["history"])
    getattr(routes, "get")(f"{BASE}/live")(handlers["live"])
    getattr(routes, "post")(f"{BASE}/record")(handlers["record"])
    getattr(routes, "delete")(f"{BASE}/history/{{id}}")(handlers["delete_one"])
    getattr(routes, "delete")(f"{BASE}/history")(handlers["clear"])


def register_with_server() -> bool:
    if web is None:
        return False
    try:
        from server import PromptServer  # type: ignore[import-not-found]

        instance = getattr(PromptServer, "instance", None)
        if instance is None or getattr(instance, _ROUTES_FLAG, False):
            return False
        register(instance.routes)
        setattr(instance, _ROUTES_FLAG, True)
        return True
    except Exception:  # noqa: BLE001 - not running inside ComfyUI
        return False
