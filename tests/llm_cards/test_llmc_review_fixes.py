"""Regression tests for the llm_cards code-review fixes."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import threading
import time
import types
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import torch
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from nodes.llm_cards import bboxes as bb
from nodes.llm_cards import character as ch
from nodes.llm_cards import character_chat as cc
from nodes.llm_cards import lmstudio as lms
from nodes.llm_cards.common import MAX_IMAGES
from v3_helpers import hidden, legacy

PACK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _read(rel: str) -> str:
    with open(os.path.join(PACK_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture()
def comfy_dirs(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[types.ModuleType]:
    dirs = {name: tmp_path / name for name in ("input", "output", "temp")}
    for d in dirs.values():
        d.mkdir()
    fp = types.ModuleType("folder_paths")
    fp.models_dir = str(tmp_path / "models")  # type: ignore[attr-defined]
    fp.get_input_directory = lambda: str(dirs["input"])  # type: ignore[attr-defined]
    fp.get_output_directory = lambda: str(dirs["output"])  # type: ignore[attr-defined]
    fp.get_temp_directory = lambda: str(dirs["temp"])  # type: ignore[attr-defined]

    def get_folder_paths(key: str) -> list[str]:
        raise KeyError(key)

    fp.get_folder_paths = get_folder_paths  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "folder_paths", fp)
    yield fp


def _card_json(name: str) -> dict[str, object]:
    return {"spec": "chara_card_v2", "data": {"name": name, "description": "d", "first_mes": "hi"}}


def _write_card(comfy_dirs: types.ModuleType, rel: str = "mira.json", name: str = "Mira") -> str:
    folder = os.path.join(comfy_dirs.get_input_directory(), "characters")  # type: ignore[attr-defined]
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, rel)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(_card_json(name), fh)
    return path


# --------------------------------------------------------------------------- 1. CLIP.generate kwargs


class ComfyClip:
    """Mirrors comfy/sd.py CLIP.generate: no `mtp` parameter."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def tokenize(self, prompt: str, **kwargs: object) -> str:
        return "tokens"

    def generate(self, tokens: str, do_sample: bool = True, max_length: int = 256, temperature: float = 1.0,
                 top_k: int = 50, top_p: float = 0.95, min_p: float = 0.0, repetition_penalty: float = 1.0,
                 seed: int | None = None, presence_penalty: float = 0.0) -> list[int]:
        self.calls.append({"do_sample": do_sample, "seed": seed, "presence_penalty": presence_penalty})
        return [1, 2]

    def decode(self, ids: list[int]) -> str:
        return "Mira: ok"


class MtpClip(ComfyClip):
    def generate(self, tokens: str, do_sample: bool = True, max_length: int = 256, temperature: float = 1.0,
                 top_k: int = 50, top_p: float = 0.95, min_p: float = 0.0, repetition_penalty: float = 1.0,
                 seed: int | None = None, presence_penalty: float = 0.0, mtp: bool | str = False) -> list[int]:
        self.calls.append({"mtp": mtp})
        if isinstance(mtp, str):
            raise TypeError("bad mode")
        return [1]


def _chat(clip: object, **over: object) -> dict[str, object]:
    args: dict[str, object] = dict(
        clip=clip, character="mira.json", user_name="Sam", max_length=64, temperature=0.7, top_p=0.9, top_k=40,
        min_p=0.05, repetition_penalty=1.05, seed=7, thinking=False, context_messages=40, action="send",
        user_message="hi", history_json=json.dumps([{"role": "assistant", "content": "Hello"}]),
    )
    args.update(over)
    return legacy(cc.JWTFCharacterChat.execute(**args))  # type: ignore[arg-type]


def test_generate_without_mtp_parameter_does_not_raise(comfy_dirs: types.ModuleType) -> None:
    _write_card(comfy_dirs)
    for mode in ("auto", "off", "tree2s1"):
        clip = ComfyClip()
        res = _chat(clip, mtp=mode)
        assert res["result"][0] == "ok"  # type: ignore[index]
        assert len(clip.calls) == 1 and clip.calls[0]["presence_penalty"] == 0.0


def test_supported_generate_kwargs_filters_by_signature() -> None:
    kw = {"do_sample": True, "mtp": True, "presence_penalty": 0.5, "bogus": 1}
    assert cc.supported_generate_kwargs(ComfyClip().generate, kw) == {"do_sample": True, "presence_penalty": 0.5}
    assert cc.supported_generate_kwargs(MtpClip().generate, kw) == {"do_sample": True, "mtp": True,
                                                                     "presence_penalty": 0.5}
    assert cc.supported_generate_kwargs(lambda t, **k: None, kw) == kw


def test_mtp_retry_only_when_signature_accepts_it(comfy_dirs: types.ModuleType) -> None:
    _write_card(comfy_dirs)
    clip = MtpClip()
    _chat(clip, mtp="tree2s1")
    assert [c["mtp"] for c in clip.calls] == ["tree2s1", True]


# --------------------------------------------------------------------------- 2. card_path confinement


class _Routes:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}

    def get(self, path: str):
        def deco(fn):
            self.handlers[path] = fn
            return fn

        return deco

    post = get


def _call(routes: _Routes, path: str, query: str) -> web.StreamResponse:
    req = make_mocked_request("GET", f"{path}?{query}")
    return asyncio.run(routes.handlers[path](req))  # type: ignore[operator]


def test_routes_ignore_card_path(comfy_dirs: types.ModuleType, tmp_path) -> None:
    _write_card(comfy_dirs)
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps(_card_json("Leaked")), encoding="utf-8")
    routes = _Routes()
    cc.register(routes)
    from urllib.parse import quote

    only_path = _call(routes, "/jezzwtf/character/info", f"card_path={quote(str(secret))}")
    assert only_path.status == 400  # no character chosen: card_path is never consulted
    both = _call(routes, "/jezzwtf/character/info", f"character=mira.json&card_path={quote(str(secret))}")
    assert json.loads(both.body)["name"] == "Mira"  # type: ignore[attr-defined]
    assert _call(routes, "/jezzwtf/character/avatar", f"card_path={quote(str(secret))}").status == 404
    unc = _call(routes, "/jezzwtf/character/info", "character=" + quote("\\\\evil\\share\\x.json"))
    assert unc.status == 400


def test_node_card_path_confined_to_comfy_folders(comfy_dirs: types.ModuleType, tmp_path) -> None:
    inside = _write_card(comfy_dirs, "inner.json", "Inner")
    outside = tmp_path / "elsewhere.json"
    outside.write_text(json.dumps(_card_json("Outside")), encoding="utf-8")
    assert cc.load_selected("", inside, allow_explicit=True)["card"]["name"] == "Inner"
    out_in_output = os.path.join(comfy_dirs.get_output_directory(), "o.json")  # type: ignore[attr-defined]
    with open(out_in_output, "w", encoding="utf-8") as fh:
        json.dump(_card_json("Out"), fh)
    assert cc.load_selected("", out_in_output, allow_explicit=True)["card"]["name"] == "Out"
    with pytest.raises(ch.CardReadError, match="inside the ComfyUI"):
        cc.load_selected("", str(outside), allow_explicit=True)
    with pytest.raises(ch.CardReadError, match="inside the ComfyUI"):
        cc.load_selected("", os.path.join(os.path.dirname(inside), "..", "..", "..", "elsewhere.json"),
                         allow_explicit=True)


@pytest.mark.parametrize("bad", ["\\\\server\\share\\a.png", "//server/share/a.png", "C:card.png", "z:..\\x.json"])
def test_unc_and_drive_relative_rejected(comfy_dirs: types.ModuleType, bad: str) -> None:
    assert ch.is_unsafe_explicit_path(bad)
    with pytest.raises(ch.CardReadError, match="UNC"):
        cc.load_selected("", bad, allow_explicit=True)
    assert not ch.is_unsafe_explicit_path("C:\\cards\\a.png")


# --------------------------------------------------------------------------- 3. non-UTF-8 JSON cards


def test_cp1252_json_card_loads(tmp_path) -> None:
    p = tmp_path / "caf.json"
    p.write_bytes(json.dumps(_card_json("Caf\u00e9"), ensure_ascii=False).encode("cp1252"))
    assert ch.load_card(str(p))["card"]["name"] == "Caf\u00e9"
    bom = tmp_path / "bom.json"
    bom.write_bytes(b"\xef\xbb\xbf" + json.dumps(_card_json("Bom")).encode("utf-8"))
    assert ch.load_card(str(bom))["card"]["name"] == "Bom"


def test_undecodable_json_card_is_card_read_error(tmp_path) -> None:
    p = tmp_path / "bad.json"
    p.write_bytes(b'{"name": "\x81\x8d"}')  # undefined in both UTF-8 and cp1252
    with pytest.raises(ch.CardReadError, match="not valid"):
        ch.load_card(str(p))


def test_info_route_survives_bad_encoding(comfy_dirs: types.ModuleType) -> None:
    folder = os.path.dirname(_write_card(comfy_dirs))
    with open(os.path.join(folder, "bad.json"), "wb") as fh:
        fh.write(b'\x81\x8d')
    routes = _Routes()
    cc.register(routes)
    assert _call(routes, "/jezzwtf/character/info", "character=bad.json").status == 400


# --------------------------------------------------------------------------- 4. interruptible + deadline


class _Interrupted(Exception):
    pass


_Interrupted.__name__ = "InterruptProcessingException"


def _blocking_post(release: threading.Event):
    def post(url, payload, stream):
        release.wait(10)
        yield 'data: {"choices":[{"delta":{"content":"x"}}]}'

    return post


def test_cancel_interrupts_a_silent_server(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()
    monkeypatch.setattr(lms, "_http_post", _blocking_post(release))
    monkeypatch.setattr(lms, "POLL_INTERVAL", 0.02)
    state = {"n": 0}

    def check() -> None:
        state["n"] += 1
        if state["n"] > 3:
            raise _Interrupted()

    monkeypatch.setattr(lms, "_raise_if_interrupted", check)
    t0 = time.monotonic()
    with pytest.raises(_Interrupted):
        lms.run_completion("http://h:1", {"stream": True})
    assert time.monotonic() - t0 < 2
    release.set()


def test_cancel_interrupts_between_stream_lines_and_non_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    def post(url, payload, stream):
        for _ in range(50):
            yield 'data: {"choices":[{"delta":{"content":"x"}}]}'
            time.sleep(0.01)

    monkeypatch.setattr(lms, "_http_post", post)
    monkeypatch.setattr(lms, "POLL_INTERVAL", 0.02)
    calls = {"n": 0}

    def check() -> None:
        calls["n"] += 1
        if calls["n"] > 5:
            raise _Interrupted()

    monkeypatch.setattr(lms, "_raise_if_interrupted", check)
    with pytest.raises(_Interrupted):
        lms.run_completion("http://h:1", {"stream": True})
    release = threading.Event()
    monkeypatch.setattr(lms, "_http_post", _blocking_post(release))
    calls["n"] = 0
    with pytest.raises(_Interrupted):
        lms.run_completion("http://h:1", {"stream": False})
    release.set()


def test_total_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()
    monkeypatch.setattr(lms, "_http_post", _blocking_post(release))
    monkeypatch.setattr(lms, "POLL_INTERVAL", 0.02)
    with pytest.raises(TimeoutError, match="no complete reply"):
        lms.run_completion("http://h:1", {"stream": False}, deadline=0.2)
    release.set()


def test_node_reraises_interrupt_instead_of_returning_error_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lms, "send_event", lambda e, p: None)

    def boom(*_a: object, **_k: object):
        raise _Interrupted()

    monkeypatch.setattr(lms, "run_completion", boom)
    with pytest.raises(_Interrupted), hidden(lms.JWTFLMStudio, unique_id=None):
        legacy(lms.JWTFLMStudio.execute("http://x:1", "m", "", "hi", 0, 0.7, 0.95, True, 0, "512", 8))


# --------------------------------------------------------------------------- 5. mid-stream errors


def test_mid_stream_error_chunk_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def post(url, payload, stream):
        yield 'data: {"choices":[{"delta":{"content":"par"}}]}'
        yield 'data: {"error":{"message":"model crashed"}}'
        yield "data: [DONE]"

    monkeypatch.setattr(lms, "_http_post", post)
    with pytest.raises(RuntimeError, match="model crashed"):
        lms.run_completion("http://h:1", {"stream": True})


def test_empty_reply_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lms, "_http_post", lambda u, p, s: iter(["data: [DONE]"]))
    with pytest.raises(RuntimeError, match="empty reply"):
        lms.run_completion("http://h:1", {"stream": True})
    body = json.dumps({"choices": [{"message": {"content": ""}}]})
    monkeypatch.setattr(lms, "_http_post", lambda u, p, s: iter([body]))
    with pytest.raises(RuntimeError, match="empty reply"):
        lms.run_completion("http://h:1", {"stream": False})
    monkeypatch.setattr(lms, "_http_post", lambda u, p, s: iter([json.dumps({"error": "nope"})]))
    with pytest.raises(RuntimeError, match="nope"):
        lms.run_completion("http://h:1", {"stream": False})


# --------------------------------------------------------------------------- 6/7. JS (static)


def test_js_uploads_never_overwrite_and_pasted_images_get_unique_names() -> None:
    ui = _read("js/llm_cards/jwtf_ui.js")
    assert 'body.append("overwrite", "false")' in ui and '"overwrite", "true"' not in ui
    assert "uniqueUploadName" in ui and "Date.now()" in ui.split("function uniqueUploadName")[1].split("}\n")[0]
    assert "{ unique: true }" in _read("js/llm_cards/lmstudio.js")


def test_js_dispose_releases_listeners_and_gl_context() -> None:
    chat = _read("js/llm_cards/character_chat.js")
    assert "io.disconnect()" in chat
    assert 'document.removeEventListener("visibilitychange", kick)' in chat
    assert "cancelAnimationFrame(raf)" in chat and "loseContext()" in chat
    assert "webglcontextlost" in chat and "clearInterval(progTimer)" in chat
    assert re.search(r"onRemoved = function \(\) \{[^}]*_jwtfChat\?\.dispose\(\)", chat, re.S)
    card = _read("js/llm_cards/card_preview.js")
    assert 'document.removeEventListener("visibilitychange", resume)' in card
    assert "resizeObs.disconnect()" in card and "visObs.disconnect()" in card
    assert re.search(r"onRemoved = function \(\) \{[^}]*_jwtfCard\?\.dispose\(\)", card, re.S)


# --------------------------------------------------------------------------- 8. models proxy


def test_validate_base_url() -> None:
    assert lms.validate_base_url("http://127.0.0.1:1234") == "http://127.0.0.1:1234"
    assert lms.validate_base_url("https://lm.example") == "https://lm.example"
    for bad in ("file:///etc/passwd", "ftp://h/", "gopher://h", "http://user:pw@h", "http://", "just-text"):
        with pytest.raises(ValueError):
            lms.validate_base_url(bad)


def _models_call(base: str) -> dict[str, object]:
    routes = _Routes()
    lms.register(routes)
    from urllib.parse import quote

    resp = asyncio.run(routes.handlers["/jezzwtf/lmstudio/models"](  # type: ignore[operator]
        make_mocked_request("GET", f"/jezzwtf/lmstudio/models?base={quote(base, safe='')}")))
    return json.loads(resp.body)


def test_models_route_rejects_schemes_and_hides_errors() -> None:
    assert "http://" in str(_models_call("file:///etc/passwd")["error"])
    out = _models_call("http://127.0.0.1:1")  # nothing listens there
    assert out == {"models": [], "error": "could not reach the server"}


def test_models_route_does_not_follow_redirects() -> None:
    class Target(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = json.dumps({"data": [{"id": "leaked"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_a: object) -> None:
            pass

    target = HTTPServer(("127.0.0.1", 0), Target)

    class Redirect(Target):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target.server_port}/v1/models")
            self.send_header("Content-Length", "0")
            self.end_headers()

    front = HTTPServer(("127.0.0.1", 0), Redirect)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (target, front)]
    for t in threads:
        t.start()
    try:
        out = _models_call(f"http://127.0.0.1:{front.server_port}")
    finally:
        front.shutdown()
        target.shutdown()
    assert out["models"] == [] and "302" in str(out["error"])


# --------------------------------------------------------------------------- 9. image caps


def test_image_batch_is_capped() -> None:
    out = lms.image_batch_b64(torch.rand(40, 4, 4, 3), 64)
    assert len(out) == MAX_IMAGES
    assert len(lms.image_batch_b64(torch.rand(3, 4, 4, 3), 64)) == 3


def test_chat_gather_images_is_capped() -> None:
    frames, n_video = cc.gather_images(torch.rand(40, 4, 4, 3), None, 8)
    assert len(frames) == MAX_IMAGES and n_video == 0
    frames, n_video = cc.gather_images(torch.rand(40, 4, 4, 3), torch.rand(2400, 4, 4, 3), 64)
    assert len(frames) <= MAX_IMAGES and n_video == len(frames) - MAX_IMAGES // 2 and n_video > 0
    frames, _ = cc.gather_images(torch.rand(3, 4, 4, 3), None, 8)
    assert len(frames) == 3


# --------------------------------------------------------------------------- 10. regex lore keys


def test_slashed_literal_is_not_a_regex() -> None:
    assert ch.key_matches("/home/user", "cd /home/user now", False)
    assert not ch.key_matches("/home/user", "home", False)
    assert ch.key_matches("/dr.g/i", "DRAG", False)  # real flags still work
    assert not ch.key_matches("/dr.g/x", "drag", False)  # unknown flag: literal text, not regex


def test_regex_guards() -> None:
    evil = "/(a+)+$/"
    t0 = time.monotonic()
    assert not ch.key_matches(evil, "a" * 40 + "!", False)
    assert time.monotonic() - t0 < 1
    assert not ch.key_matches("/" + "a" * (ch.REGEX_MAX_LEN + 1) + "/", "a" * 300, False)
    assert ch.key_matches("/needle/", "x" * 100 + "needle", False)


# --------------------------------------------------------------------------- 11. non-finite boxes


def test_non_finite_values_are_dropped() -> None:
    for v in (float("nan"), float("inf"), float("-inf"), "nan", "inf", 1e300):
        assert bb._num(v) is None
    assert bb._num(3) == 3.0 and bb._num(" 2.5 ") == 2.5
    boxes, _ = bb.parse_bboxes_input([{"bbox": [0, 0, float("nan"), 5]}, {"bbox": [0, 0, 500, 500]}], 100, 100)
    assert len(boxes) == 1
    px, _ = bb.parse_bboxes_input({"x": float("inf"), "y": 1, "width": float("nan"), "height": 4}, 10, 10)
    assert px[0]["x"] == 0 and px[0]["width"] == 0
    regions = bb.regions_from_state([{"x": float("nan"), "y": 0, "w": 1, "h": 1},
                                     {"x": 0, "y": 0, "w": float("inf"), "h": 1},
                                     {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}])
    assert len(regions) == 1
    assert bb.regions_to_frames(regions, 100, 100)  # no OverflowError / ValueError
    nan_json = '{"layout": [{"bbox": [NaN, 0, 5, 5]}, {"bbox": [Infinity, 0, 5, 5]}]}'
    assert bb.parse_bboxes_input(nan_json, 10, 10)[0] == []


# --------------------------------------------------------------------------- 12. refmod listing cache


def _write_refmod(path, card: bool = True) -> None:
    import struct

    meta = {"jezzwtf_character_card": json.dumps(_card_json("R"))} if card else {}
    header = json.dumps({"__metadata__": meta}).encode()
    path.write_bytes(struct.pack("<Q", len(header)) + header)


def test_refmod_headers_read_once_per_file_version(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    ch._REFMOD_CARD_CACHE.clear()
    a, b = tmp_path / "a.safetensors", tmp_path / "b.safetensors"
    _write_refmod(a)
    _write_refmod(b, card=False)
    reads: list[str] = []
    real = ch.refmod_has_card

    def counting(path: str) -> bool:
        reads.append(os.path.basename(path))
        return real(path)

    monkeypatch.setattr(ch, "refmod_has_card", counting)
    assert ch.list_refmods([str(tmp_path)]) == ["refmod:a.safetensors"]
    assert ch.list_refmods([str(tmp_path)]) == ["refmod:a.safetensors"]
    assert sorted(reads) == ["a.safetensors", "b.safetensors"]  # second call hit the cache
    os.utime(a, ns=(time.time_ns(), time.time_ns() + 5_000_000_000))
    ch.list_refmods([str(tmp_path)])
    assert sorted(reads) == ["a.safetensors", "a.safetensors", "b.safetensors"]  # changed file re-read
    b.unlink()
    ch.list_refmods([str(tmp_path)])
    assert str(b) not in ch._REFMOD_CARD_CACHE
