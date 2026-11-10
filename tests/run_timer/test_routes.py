"""The HTTP handlers, exercised through a real aiohttp test server (loopback) and with fake non-local requests."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

aiohttp = pytest.importorskip("aiohttp")
from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from run_timer import routes as R  # noqa: E402
from run_timer.store import HistoryStore  # noqa: E402

H = {R.HEADER_NAME: R.HEADER_VALUE}
NOW_MS = 1_800_000_000_000


def good(**over: object) -> dict[str, object]:
    base: dict[str, object] = {"prompt_id": "p-1", "status": "ok", "started_at": 1_700_000_000_000, "duration_ms": 1234, "label": "a"}
    base.update(over)
    return base


def with_client(tmp_path: Path, scenario: Callable[[TestClient, HistoryStore], Awaitable[None]]) -> None:
    store = HistoryStore(tmp_path / "h.json")

    async def go() -> None:
        table = web.RouteTableDef()
        R.register(table, lambda: store)
        app = web.Application()
        app.add_routes(table)
        async with TestClient(TestServer(app)) as client:
            await scenario(client, store)

    asyncio.run(go())


def test_record_history_delete_clear_roundtrip(tmp_path: Path) -> None:
    async def scenario(c: TestClient, store: HistoryStore) -> None:
        r = await c.post(f"{R.BASE}/record", json=good(), headers=H)
        assert r.status == 201
        run = (await r.json())["run"]
        assert run["label"] == "a" and run["id"]
        dup = await c.post(f"{R.BASE}/record", json=good(duration_ms=9), headers=H)
        assert dup.status == 200 and (await dup.json())["duplicate"] is True
        await c.post(f"{R.BASE}/record", json=good(prompt_id="p-2", started_at=1_700_000_100_000), headers=H)
        hist = await (await c.get(f"{R.BASE}/history")).json()
        assert [x["prompt_id"] for x in hist["runs"]] == ["p-2", "p-1"]
        assert (await c.delete(f"{R.BASE}/history/{run['id']}", headers=H)).status == 200
        assert (await c.delete(f"{R.BASE}/history/{run['id']}", headers=H)).status == 404
        cleared = await c.delete(f"{R.BASE}/history", headers=H)
        assert (await cleared.json())["cleared"] == 1 and store.snapshot() == []

    with_client(tmp_path, scenario)


def test_mutations_need_the_header_and_valid_json(tmp_path: Path) -> None:
    async def scenario(c: TestClient, store: HistoryStore) -> None:
        assert (await c.post(f"{R.BASE}/record", json=good())).status == 403
        assert (await c.delete(f"{R.BASE}/history")).status == 403
        assert (await c.delete(f"{R.BASE}/history/x")).status == 403
        bad = await c.post(f"{R.BASE}/record", data="not json", headers=H)
        assert bad.status == 400
        arr = await c.post(f"{R.BASE}/record", data="[1]", headers=H)
        assert arr.status == 400
        invalid = await c.post(f"{R.BASE}/record", json=good(status="weird"), headers=H)
        assert invalid.status == 400 and "status" in (await invalid.json())["error"]
        huge = await c.post(f"{R.BASE}/record", data=json.dumps(good(label="x" * (R.MAX_BODY + 10))), headers=H)
        assert huge.status == 413
        assert store.snapshot() == []

    with_client(tmp_path, scenario)


def test_history_limit_and_live(tmp_path: Path) -> None:
    async def scenario(c: TestClient, store: HistoryStore) -> None:
        for i in range(3):
            await c.post(f"{R.BASE}/record", json=good(prompt_id=f"p-{i}", started_at=1_700_000_000_000 + i), headers=H)
        assert len((await (await c.get(f"{R.BASE}/history?limit=2")).json())["runs"]) == 2
        assert (await c.get(f"{R.BASE}/history?limit=abc")).status == 400
        live = await (await c.get(f"{R.BASE}/live")).json()
        assert isinstance(live["now"], int) and isinstance(live["runs"], list)

    with_client(tmp_path, scenario)


def test_locked_store_answers_503(tmp_path: Path) -> None:
    async def scenario(c: TestClient, store: HistoryStore) -> None:
        store._locked_reason = "protected"  # noqa: SLF001
        assert (await c.post(f"{R.BASE}/record", json=good(), headers=H)).status == 503
        assert (await c.get(f"{R.BASE}/history")).status == 200  # reads still work

    with_client(tmp_path, scenario)


@pytest.mark.parametrize(("remote", "host"), [("203.0.113.9", "127.0.0.1:8000"), ("127.0.0.1", "evil.example"), (None, "127.0.0.1")])
def test_non_loopback_callers_are_refused(tmp_path: Path, remote: str | None, host: str) -> None:
    handlers = R.make_handlers(lambda: HistoryStore(tmp_path / "h.json"))
    request = SimpleNamespace(remote=remote, headers={"Host": host, R.HEADER_NAME: R.HEADER_VALUE}, query={}, match_info={}, content_length=2)

    async def go() -> list[int]:
        return [(await handlers[name](request)).status for name in ("history", "live", "record", "delete_one", "clear")]  # type: ignore[arg-type]

    assert asyncio.run(go()) == [403] * 5


def test_register_with_server_is_a_noop_outside_comfyui() -> None:
    assert R.register_with_server() is False
