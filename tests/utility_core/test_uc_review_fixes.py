"""Regression tests for the code-review fixes (expr limits, caption safety, timer, set/get, loaders, JS)."""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import time
import types
import weakref
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
import torch

import utility_core.duration_frames as df
import utility_core.folder_batch as fb
import utility_core.multi_load as ml
import utility_core.resolution as res
import utility_core.timer as timer
from utility_core._comfy import is_loopback_request, read_json_object
from utility_core.expr_eval import ExprError, evaluate
from utility_core.folder_utils import caption_target
from utility_core.multi_load import JWTFMultiLoadImage
from utility_core.set_get import SetGetStore
from utility_core.text_nodes import zero_out

Handler = Callable[..., Awaitable[object]]


class FakeRoutes:
    """Collects handlers registered through the routes.get/post(path) decorators."""

    def __init__(self) -> None:
        self.handlers: dict[str, Handler] = {}

    def _reg(self, path: str) -> Callable[[Handler], Handler]:
        def deco(fn: Handler) -> Handler:
            self.handlers[path] = fn
            return fn
        return deco

    get = post = _reg


class FakeUrl:
    def __init__(self, query: dict[str, str]) -> None:
        self.query = query


class FakeRequest:
    def __init__(self, body: object = None, raw: str | None = None, remote: str | None = "127.0.0.1",
                 host: str | None = "127.0.0.1:8188", query: dict[str, str] | None = None) -> None:
        self._body, self._raw = body, raw
        self.remote = remote
        self.headers = {"Host": host} if host else {}
        self.rel_url = FakeUrl(query or {})

    async def json(self) -> object:
        if self._raw is not None:
            return json.loads(self._raw)
        return self._body


def call(handler: Handler, request: FakeRequest) -> tuple[int, dict[str, object]]:
    response = asyncio.run(handler(request))
    status = int(getattr(response, "status"))
    return status, json.loads(str(getattr(response, "text")))


# ---------------------------------------------------------------- 1. expression limits

def test_round_with_huge_digits_is_rejected_fast() -> None:
    t0 = time.perf_counter()
    for expr in ("round(5, -1000000000)", "round(5, 100)", "round(1.5, -33)"):
        with pytest.raises(ExprError, match="digits"):
            evaluate(expr, 1.0, 24.0)
    assert time.perf_counter() - t0 < 1.0
    assert evaluate("round(1234, -2)", 1.0, 24.0) == 1200 and evaluate("round(1.234, 2)", 1.0, 24.0) == 1.23


def test_eval_rows_survive_overflow_inputs() -> None:
    _, _, rows = df.eval_rows("Custom", "a * fps", 24, [10**400, float("inf"), float("nan"), 2])
    assert "error" in rows[0] and "error" in rows[1] and "error" in rows[2] and rows[3]["frames"] == 48
    json.dumps(rows, allow_nan=False)  # strict JSON: no Infinity / NaN / giant ints echoed back


def test_deeply_nested_expression_is_an_error_not_a_crash() -> None:
    with pytest.raises(ExprError):
        evaluate("-" * 290 + "a", 1.0, 24.0)


def test_eval_route_handles_hostile_bodies() -> None:
    routes = FakeRoutes()
    df.register_routes(routes)  # type: ignore[arg-type]
    handler = routes.handlers["/jezzwtf/duration_frames/eval"]
    assert call(handler, FakeRequest(raw="[" * 100000 + "]" * 100000))[0] == 400
    status, payload = call(handler, FakeRequest(body={
        "preset": "Custom", "expression": "a*fps", "fps": float("inf"), "values": [10**400, 1]}))
    rows = payload["rows"]
    assert isinstance(rows, list) and status == 200 and payload["fps"] == 24 and "error" in rows[0]
    _, slow = call(handler, FakeRequest(body={"expression": "round(5, -1000000000)", "values": [1]}))
    slow_rows = slow["rows"]
    assert isinstance(slow_rows, list) and "digits" in slow_rows[0]["error"]


def test_read_json_object_rejects_recursion_and_non_objects() -> None:
    assert asyncio.run(read_json_object(FakeRequest(raw="[" * 100000))) is None  # type: ignore[arg-type]
    assert asyncio.run(read_json_object(FakeRequest(body=[1]))) is None  # type: ignore[arg-type]
    assert asyncio.run(read_json_object(FakeRequest(body={"a": 1}))) == {"a": 1}  # type: ignore[arg-type]


# ---------------------------------------------------------------- 2. caption safety + scan route

@pytest.mark.parametrize("ext", ["bat", "CMD", ".ps1", "exe", "sh", "py", "js", "dll", "lnk", "com", "scr", "vbs"])
def test_caption_rejects_executable_extensions(tmp_path: Path, ext: str) -> None:
    with pytest.raises(ValueError, match="not allowed"):
        caption_target(str(tmp_path / "a.png"), "next to image", "", ext)


@pytest.mark.parametrize("ext", ["../x", "a/b", "a\\b", "t.xt", "tx t", "t:s"])
def test_caption_rejects_unsafe_extension_characters(tmp_path: Path, ext: str) -> None:
    with pytest.raises(ValueError, match="invalid extension"):
        caption_target(str(tmp_path / "a.png"), "next to image", "", ext)


def test_caption_allows_plain_extensions(tmp_path: Path) -> None:
    assert caption_target(str(tmp_path / "a.png"), "next to image", "", "my-cap_1").endswith("a.my-cap_1")


def test_loopback_check() -> None:
    assert is_loopback_request("127.0.0.1", "localhost:8188") and is_loopback_request("::1", "[::1]:8188")
    assert not is_loopback_request("192.168.1.5", "127.0.0.1:8188")
    assert not is_loopback_request("127.0.0.1", "evil.example:8188")  # DNS rebinding
    assert not is_loopback_request(None, "localhost") and not is_loopback_request("127.0.0.1", None)


def test_scan_route_is_loopback_only_and_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    routes = FakeRoutes()
    fb.register_routes(routes)  # type: ignore[arg-type]
    handler = routes.handlers["/jezzwtf/folder_batch/scan"]
    query = {"folder": str(tmp_path), "kind": "image"}
    assert call(handler, FakeRequest(remote="10.0.0.9", query=query))[0] == 403
    assert call(handler, FakeRequest(host="evil.example", query=query))[0] == 403
    status, body = call(handler, FakeRequest(query=query))
    assert status == 200 and body["ok"] is False
    monkeypatch.setattr(fb, "MAX_SCAN_FILES", 1)
    (tmp_path / "a.png").write_bytes(b"x")
    (tmp_path / "b.png").write_bytes(b"x")
    assert "too many files" in str(fb.scan(str(tmp_path), "alphabetical", "image", 0)["error"])


# ---------------------------------------------------------------- 3-7. timer server

def test_timer_routes_state_reset_arm(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = timer.TimerRuns()
    monkeypatch.setattr(timer, "RUNS", runs)
    monkeypatch.setattr(timer, "queue_busy", lambda: False)
    routes = FakeRoutes()
    timer.register_routes(routes)  # type: ignore[arg-type]
    runs.tick("5", 4, now=time.time() - 120)
    runs.tick("12:5", 4, now=time.time())
    _, state = call(routes.handlers["/jezzwtf/timer/state"], FakeRequest())
    snap = state["runs"]
    assert isinstance(snap, dict)
    assert snap["5"]["stale"] is True and snap["12:5"]["stale"] is False and snap["5"]["run_id"]
    call(routes.handlers["/jezzwtf/timer/reset"], FakeRequest(body={"node_ids": ["5"]}))
    assert set(runs.snapshot()) == {"12:5"}  # a root reset leaves the subgraph instance alone
    call(routes.handlers["/jezzwtf/timer/reset"], FakeRequest(raw="[" * 100000))  # hostile body: no crash
    assert runs.snapshot() == {}  # unparseable body keeps the old "reset everything" meaning
    call(routes.handlers["/jezzwtf/timer/arm"], FakeRequest())
    assert runs.tick("n", 2, now=time.time() + 5)[0].started_at < time.time()


# ---------------------------------------------------------------- 8. set / get scope

def test_set_get_store_is_scoped_to_one_prompt() -> None:
    prompt = ["p1"]
    store = SetGetStore(scope=lambda: prompt[0])
    marker = object()
    store.set("k", marker)
    assert store.get("k") is marker  # Set -> Get inside one run
    store.set("k2", 1)
    assert sorted(store.keys()) == ["k", "k2"]
    version = store.version("k")
    prompt[0] = "p2"
    with pytest.raises(KeyError):
        store.get("k")  # previous prompt's value is released
    assert store.keys() == []
    store.set("k", 2)
    assert store.version("k") == version + 1  # versions stay monotonic so IS_CHANGED never repeats


def test_store_releases_value_for_gc() -> None:
    prompt = ["p1"]
    store = SetGetStore(scope=lambda: prompt[0])
    tensor = torch.zeros(4)
    ref = weakref.ref(tensor)
    store.set("big", tensor)
    del tensor
    assert ref() is not None
    prompt[0] = "p2"
    store.keys()
    assert ref() is None


# ---------------------------------------------------------------- 9. multi load

def _fake_folder_paths(inp: Path, out: Path, temp: Path, exists: bool | None = None) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        get_input_directory=lambda: str(inp), get_output_directory=lambda: str(out),
        get_temp_directory=lambda: str(temp),
        get_annotated_filepath=lambda name: str(inp / name),
        exists_annotated_filepath=lambda name: (inp / name).exists() if exists is None else exists)


def test_multi_load_blocks_path_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inp, out = tmp_path / "input", tmp_path / "output"
    inp.mkdir()
    out.mkdir()
    (tmp_path / "secret.png").write_bytes(b"top secret")
    (inp / "ok.png").write_bytes(b"fine")
    monkeypatch.setitem(sys.modules, "folder_paths", _fake_folder_paths(inp, out, tmp_path / "temp"))
    evil = json.dumps(["../secret.png"])
    assert JWTFMultiLoadImage.VALIDATE_INPUTS(evil) != True  # noqa: E712
    with pytest.raises(ValueError, match="outside"):
        JWTFMultiLoadImage().run(evil)
    assert JWTFMultiLoadImage.VALIDATE_INPUTS(json.dumps(["ok.png"])) is True
    ok_hash = JWTFMultiLoadImage.IS_CHANGED(json.dumps(["ok.png"]))
    (tmp_path / "secret.png").write_bytes(b"changed")
    assert JWTFMultiLoadImage.IS_CHANGED(evil) == JWTFMultiLoadImage.IS_CHANGED(evil)  # never reads the file
    assert JWTFMultiLoadImage.IS_CHANGED(json.dumps(["ok.png"])) == ok_hash


def test_multi_load_hash_is_chunked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "big.png").write_bytes(b"x" * (3 << 20))
    monkeypatch.setitem(sys.modules, "folder_paths", _fake_folder_paths(tmp_path, tmp_path, tmp_path))
    sizes: list[int] = []
    real_open = open

    class Spy:
        def __init__(self, fh: object) -> None:
            self.fh = fh

        def read(self, n: int = -1) -> bytes:
            sizes.append(n)
            data: bytes = self.fh.read(n)  # type: ignore[attr-defined]
            return data

        def __enter__(self) -> "Spy":
            return self

        def __exit__(self, *exc: object) -> None:
            self.fh.close()  # type: ignore[attr-defined]

    monkeypatch.setattr(ml, "open", lambda p, m="r": Spy(real_open(p, m)), raising=False)
    JWTFMultiLoadImage.IS_CHANGED(json.dumps(["big.png"]))
    assert sizes and all(0 < n <= (1 << 20) for n in sizes)


# ---------------------------------------------------------------- 10. latent dtype

def test_resolution_latent_uses_intermediate_dtype(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(res, "intermediate_dtype", lambda: torch.float16)
    _, _, latent = res.JWTFResolutionPicker().run("Preset Resolution", "1:1 (Square)", 1, 1, 1,
                                                  "640x360 (16:9 nHD)", False, 32, False, 1)
    samples = latent["samples"]
    assert isinstance(samples, torch.Tensor) and samples.dtype == torch.float16


# ---------------------------------------------------------------- 11. zero out lyrics

def test_zero_out_clears_conditioning_lyrics() -> None:
    cond = [[torch.ones(1, 2, 3), {"conditioning_lyrics": torch.ones(1, 4), "pooled_output": torch.ones(1, 3)}]]
    out = zero_out(cond)
    lyrics = out[0][1]["conditioning_lyrics"]  # type: ignore[index]
    assert isinstance(lyrics, torch.Tensor) and torch.count_nonzero(lyrics) == 0
    assert torch.count_nonzero(cond[0][1]["conditioning_lyrics"]) == 4  # type: ignore[index]


# ---------------------------------------------------------------- JS (4-6, 12) via plain node

JS_DIR = Path(__file__).resolve().parents[2] / "js" / "utility_core"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def node_eval(script: str) -> object:
    out = subprocess.run([NODE or "node", "--input-type=module", "-e", script], capture_output=True, text=True,
                         check=True, timeout=30)
    return json.loads(out.stdout)


@needs_node
def test_js_timer_subgraph_matching_is_exact() -> None:
    url = (JS_DIR / "timer_core.js").as_uri()
    result = node_eval(f"""
import {{ pathMatches }} from "{url}";
const sub = {{ id: "sg-A" }};
const other = {{ id: "sg-B" }};
const table = {{ 12: {{ subgraph: sub }}, 7: {{ subgraph: other }} }};
const root = {{ getNodeById: (id) => table[id] }};
const rootNode = {{ id: 5, graph: root }};
const inner = {{ id: 5, graph: sub }};
console.log(JSON.stringify([
  pathMatches(rootNode, "5", root), pathMatches(rootNode, "12:5", root), pathMatches(rootNode, "7:5", root),
  pathMatches(inner, "12:5", root), pathMatches(inner, "7:5", root), pathMatches(inner, "5", root),
]));""")
    assert result == [True, False, False, True, False, False]


@needs_node
def test_js_timer_durations_count_paused_time() -> None:
    url = (JS_DIR / "timer_core.js").as_uri()
    result = node_eval(f"""
import {{ attributeItems }} from "{url}";
const t = {{ durations: [], lastItemAt: 0 }};
attributeItems(t, 1, 10000);
attributeItems(t, 2, 40000);
console.log(JSON.stringify(t.durations));""")
    assert result == [10, 15, 15]  # two items finished while paused still get their real share, never 0


@needs_node
def test_js_draw_uid_collision_and_texture_destroy() -> None:
    url = (JS_DIR / "draw_core.js").as_uri()
    result = node_eval(f"""
import {{ collidesWithOther, dropTexture }} from "{url}";
const a = {{ uid: "x", node: {{ id: 3 }} }}, b = {{ uid: "x", node: {{ id: 3 }} }}, c = {{ uid: "y", node: {{ id: 3 }} }};
let destroyed = 0;
const layer = {{ tex: {{ texture: {{ destroy: () => destroyed++ }} }} }};
dropTexture(layer);
console.log(JSON.stringify([collidesWithOther([a, b], a), collidesWithOther([a, c], a), destroyed, layer.tex]));""")
    assert result == [True, False, 1, None]
