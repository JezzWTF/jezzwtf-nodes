"""Node-level tests: bakers write verified PNGs, Character Chat runs a turn on a fake CLIP, routes answer."""

from __future__ import annotations

import asyncio
import json
import os
import struct
import sys
import types
from collections.abc import Iterator
from typing import Callable

import pytest
import torch
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from PIL import Image

from nodes.llm_cards import bakers, character_chat as cc
from nodes.llm_cards.png_chunks import decode_chara, read_png_text_from_file, save_png_with_text
from v3_helpers import legacy


@pytest.fixture()
def comfy_dirs(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[types.ModuleType]:
    """A minimal stand-in for ComfyUI's `folder_paths` rooted in tmp_path."""
    out_dir = tmp_path / "output"
    in_dir = tmp_path / "input"
    tmp_dir = tmp_path / "temp"
    for d in (out_dir, in_dir, tmp_dir):
        d.mkdir()
    fp = types.ModuleType("folder_paths")
    fp.models_dir = str(tmp_path / "models")  # type: ignore[attr-defined]
    fp.get_output_directory = lambda: str(out_dir)  # type: ignore[attr-defined]
    fp.get_input_directory = lambda: str(in_dir)  # type: ignore[attr-defined]
    fp.get_temp_directory = lambda: str(tmp_dir)  # type: ignore[attr-defined]

    def get_folder_paths(key: str) -> list[str]:
        raise KeyError(key)

    def get_save_image_path(prefix: str, output_dir: str, width: int = 0, height: int = 0):
        subfolder, fname = os.path.split(prefix)
        full = os.path.join(output_dir, subfolder)
        os.makedirs(full, exist_ok=True)
        counter = 1
        while os.path.exists(os.path.join(full, f"{fname}_{counter:05}_.png")):
            counter += 1
        return full, fname, counter, subfolder, prefix

    fp.get_folder_paths = get_folder_paths  # type: ignore[attr-defined]
    fp.get_save_image_path = get_save_image_path  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "folder_paths", fp)
    yield fp


def _batch(n: int = 2) -> torch.Tensor:
    return torch.rand(n, 16, 24, 3)


# --------------------------------------------------------------------------- bakers


def test_v2_baker_saves_and_verifies(comfy_dirs: types.ModuleType) -> None:
    card = json.dumps({"name": "Mira/Q", "description": "héllo ✓", "first_mes": "Hi"})
    res = legacy(bakers.JWTFV2PNGBaker.execute(_batch(2), card, "V2_cards/%name%", True, save_to=bakers.SAVE_TO_OUTPUT))
    paths = res["result"][0].split("\n")  # type: ignore[index]
    assert len(paths) == 2 and res["result"][1] == "Mira/Q"  # type: ignore[index]
    assert paths[0].endswith("Mira_Q_00001_.png") and paths[1].endswith("Mira_Q_00002_.png")
    chunks = read_png_text_from_file(paths[0])
    assert set(chunks) == {"chara"}  # no workflow/prompt chunk
    decoded = decode_chara(chunks["chara"])
    assert decoded["spec"] == "chara_card_v2" and decoded["data"]["description"] == "héllo ✓"  # type: ignore[index]
    ui = res["ui"]
    assert ui["card_preview"][0] == {"filename": "Mira_Q_00001_.png", "subfolder": "V2_cards", "type": "output"}  # type: ignore[index]
    info = ui["card_info"][0]  # type: ignore[index]
    assert info["name"] == "Mira/Q" and info["rarity"] == "common"


def test_v2_baker_errors_are_readable(comfy_dirs: types.ModuleType) -> None:
    with pytest.raises(ValueError, match="V2 PNG Baker"):
        legacy(bakers.JWTFV2PNGBaker.execute(_batch(1), "not json", "x", True))


def test_workflow_baker_writes_chunks_and_counts_up(comfy_dirs: types.ModuleType) -> None:
    wf = {"nodes": [{"id": 1, "type": "Note", "widgets_values": ["ünï"]}], "links": []}
    api_prompt = {"1": {"class_type": "Note", "inputs": {}}}
    text = json.dumps({"workflow": json.dumps(wf), "prompt": api_prompt})
    baker = bakers.JWTFWorkflowPNGBaker
    first = legacy(baker.execute(_batch(1), text, "../Wf/./a:b"))
    second = legacy(baker.execute(_batch(1), text, "../Wf/./a:b"))
    p1 = first["result"][0]  # type: ignore[index]
    assert p1.replace("\\", "/").endswith("Wf/a_b_00001_.png")
    assert second["result"][0].replace("\\", "/").endswith("Wf/a_b_00002_.png")  # type: ignore[index]
    chunks = read_png_text_from_file(p1)
    assert json.loads(chunks["workflow"]) == wf and json.loads(chunks["prompt"]) == api_prompt
    assert "ü" not in chunks["workflow"]  # json.dumps escapes non-ASCII
    assert first["ui"]["images"][0]["type"] == "output"  # type: ignore[index]


def test_workflow_baker_rejects_other_json(comfy_dirs: types.ModuleType) -> None:
    with pytest.raises(ValueError, match="neither a ComfyUI workflow"):
        legacy(bakers.JWTFWorkflowPNGBaker.execute(_batch(1), '{"a": 1}', "x"))


# --------------------------------------------------------------------------- character chat


class FakeClip:
    def __init__(self, fail_modes: bool = False) -> None:
        self.tokenize_kwargs: dict[str, object] = {}
        self.prompt = ""
        self.generate_calls: list[dict[str, object]] = []
        self.fail_modes = fail_modes

    def tokenize(self, prompt: str, **kwargs: object) -> str:
        self.prompt = prompt
        self.tokenize_kwargs = dict(kwargs)
        return "tokens"

    def generate(self, tokens: str, **kwargs: object) -> list[int]:
        self.generate_calls.append(dict(kwargs))
        if self.fail_modes and isinstance(kwargs["mtp"], str):
            raise TypeError("unexpected keyword")
        return [1, 2, 3]

    def decode(self, ids: list[int]) -> str:
        return "<think>hm</think>Mira: Hello there.<|im_end|>"


def _write_card(comfy_dirs: types.ModuleType) -> None:
    folder = os.path.join(comfy_dirs.get_input_directory(), "characters")  # type: ignore[attr-defined]
    os.makedirs(folder, exist_ok=True)
    card = {"spec": "chara_card_v2", "data": {"name": "Mira", "description": "A scout.", "first_mes": "Hello {{user}}",
                                              "alternate_greetings": ["Hey"]}}
    with open(os.path.join(folder, "mira.json"), "w", encoding="utf-8") as fh:
        json.dump(card, fh)


def _chat(node: cc.JWTFCharacterChat, clip: FakeClip, **over: object) -> dict[str, object]:
    args: dict[str, object] = dict(
        clip=clip, character="mira.json", user_name="Sam", max_length=64, temperature=0.7, top_p=0.9, top_k=40,
        min_p=0.05, repetition_penalty=1.05, seed=7, thinking=False, context_messages=40,
    )
    args.update(over)
    return legacy(node.execute(**args))  # type: ignore[arg-type]


def test_chat_seeds_greeting_without_generating(comfy_dirs: types.ModuleType) -> None:
    _write_card(comfy_dirs)
    clip = FakeClip()
    res = _chat(cc.JWTFCharacterChat(), clip)
    reply, log, name, desc, avatar, history = res["result"]  # type: ignore[misc]
    assert reply == "Hello Sam" and name == "Mira" and desc == "A scout."
    assert log == "Mira: Hello Sam" and tuple(avatar.shape) == (1, 256, 256, 3)
    assert json.loads(history) == [{"role": "assistant", "content": "Hello Sam"}]
    assert clip.generate_calls == []
    payload = json.loads(res["ui"]["jwtf_chat"][0])  # type: ignore[index]
    assert payload["generated"] is False and payload["stats"] is None


def test_chat_send_generates_and_cleans_reply(comfy_dirs: types.ModuleType) -> None:
    _write_card(comfy_dirs)
    clip = FakeClip()
    res = _chat(cc.JWTFCharacterChat(), clip, action="send", user_message=" Hi! ",
                history_json=json.dumps([{"role": "assistant", "content": "Hello Sam"}]))
    reply = res["result"][0]  # type: ignore[index]
    assert reply == "Hello there."
    history = json.loads(res["result"][5])  # type: ignore[index]
    assert [m["role"] for m in history] == ["assistant", "user", "assistant"]
    assert history[1]["content"] == "Hi!"
    assert clip.prompt.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    assert clip.tokenize_kwargs["skip_template"] is True and clip.tokenize_kwargs["image"] is None
    kw = clip.generate_calls[0]
    assert kw["do_sample"] is True and kw["seed"] == 7 and kw["mtp"] is True and kw["max_length"] == 64
    stats = json.loads(res["ui"]["jwtf_chat"][0])["stats"]  # type: ignore[index]
    assert stats["tokens"] == 3 and stats["max_length"] == 64


def test_chat_media_and_sampling_off(comfy_dirs: types.ModuleType) -> None:
    _write_card(comfy_dirs)
    clip = FakeClip()
    video = torch.rand(48, 8, 8, 3)  # 48 frames at the default 24 fps -> 2 sampled frames
    _chat(cc.JWTFCharacterChat(), clip, action="send", user_message="look", sampling_mode="off",
          image=torch.rand(1, 8, 8, 3), video=video, video_max_frames=8,
          history_json=json.dumps([{"role": "assistant", "content": "Hello Sam"}]))
    assert clip.prompt.count("<|vision_start|>") == 3
    assert "last 2 attached images are consecutive frames" in clip.prompt
    assert tuple(clip.tokenize_kwargs["image"].shape) == (3, 8, 8, 3)  # type: ignore[attr-defined]
    kw = clip.generate_calls[0]
    assert kw["do_sample"] is False and kw["seed"] is None and kw["top_k"] == 50


def test_chat_mtp_string_mode_retries_with_true(comfy_dirs: types.ModuleType) -> None:
    _write_card(comfy_dirs)
    clip = FakeClip(fail_modes=True)
    _chat(cc.JWTFCharacterChat(), clip, action="send", user_message="hi", mtp="tree2s1",
          history_json=json.dumps([{"role": "assistant", "content": "Hello Sam"}]))
    assert [c["mtp"] for c in clip.generate_calls] == ["tree2s1", True]


def test_chat_regenerate_drops_trailing_assistant(comfy_dirs: types.ModuleType) -> None:
    _write_card(comfy_dirs)
    clip = FakeClip()
    hist = [{"role": "assistant", "content": "Hello Sam"}, {"role": "user", "content": "q"},
            {"role": "assistant", "content": "old"}]
    res = _chat(cc.JWTFCharacterChat(), clip, action="regenerate", history_json=json.dumps(hist))
    history = json.loads(res["result"][5])  # type: ignore[index]
    assert [m["content"] for m in history] == ["Hello Sam", "q", "Hello there."]


def test_chat_missing_character_is_readable(comfy_dirs: types.ModuleType) -> None:
    with pytest.raises(ValueError, match="Character Chat: No character selected"):
        _chat(cc.JWTFCharacterChat(), FakeClip(), character="(none - add cards to input/characters)")


def test_input_types_orders_optional_widgets_by_spec(comfy_dirs: types.ModuleType) -> None:
    opt = list(cc.JWTFCharacterChat.INPUT_TYPES()["optional"])
    assert opt == ["card_path", "action", "user_message", "history_json", "presence_penalty", "mtp",
                   "video_max_frames", "image", "audio", "video", "system_prompt", "sampling_mode"]
    assert cc.JWTFCharacterChat.INPUT_TYPES()["required"]["character"][1]["options"] == [cc.PLACEHOLDER]


# --------------------------------------------------------------------------- routes


class _Routes:
    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[web.Request], object]] = {}

    def get(self, path: str) -> Callable[[Callable[[web.Request], object]], Callable[[web.Request], object]]:
        def deco(fn: Callable[[web.Request], object]) -> Callable[[web.Request], object]:
            self.handlers[path] = fn
            return fn

        return deco

    post = get


def _call(routes: _Routes, path: str, query: str) -> web.StreamResponse:
    req = make_mocked_request("GET", f"{path}?{query}")
    return asyncio.run(routes.handlers[path](req))  # type: ignore[arg-type,return-value]


def test_character_routes(comfy_dirs: types.ModuleType) -> None:
    _write_card(comfy_dirs)
    folder = os.path.join(comfy_dirs.get_input_directory(), "characters")  # type: ignore[attr-defined]
    img = Image.new("RGB", (4, 4), (200, 30, 30))
    save_png_with_text(img, os.path.join(folder, "pic.png"),
                       {"chara": __import__("base64").b64encode(json.dumps(
                           {"spec": "chara_card_v2", "data": {"name": "Pic", "creator_notes": "n"}}).encode()).decode()})
    Image.new("RGB", (4, 4)).save(os.path.join(folder, "plain.png"))  # no card inside
    routes = _Routes()
    cc.register(routes)
    assert set(routes.handlers) == {"/jezzwtf/character/list", "/jezzwtf/character/info", "/jezzwtf/character/avatar",
                                      "/jezzwtf/character/save_chat"}

    lst = _call(routes, "/jezzwtf/character/list", "")
    assert json.loads(lst.body) == {"cards": ["mira.json", "pic.png", "plain.png"]}  # type: ignore[attr-defined]

    info = _call(routes, "/jezzwtf/character/info", "character=mira.json&user=Sam")
    data = json.loads(info.body)  # type: ignore[attr-defined]
    assert data["name"] == "Mira" and data["first_mes"] == "Hello Sam" and data["alternate_greetings"] == ["Hey"]
    assert data["source"] == "card"

    bad = _call(routes, "/jezzwtf/character/info", "character=plain.png")
    assert bad.status == 400 and "no text chunks" in json.loads(bad.body)["error"]  # type: ignore[attr-defined]

    assert isinstance(_call(routes, "/jezzwtf/character/avatar", "character=pic.png"), web.FileResponse)
    assert _call(routes, "/jezzwtf/character/avatar", "character=mira.json").status == 404
    assert _call(routes, "/jezzwtf/character/avatar", "character=plain.png").status == 404
    assert _call(routes, "/jezzwtf/character/avatar", "character=../../etc/passwd").status == 404


def test_refmod_listing_and_avatar_route(comfy_dirs: types.ModuleType, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import base64
    import io

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 200, 10)).save(buf, format="PNG")
    meta = {
        "jezzwtf_character_card": json.dumps({"spec": "chara_card_v2", "data": {"name": "Ref", "system_prompt": "own"}}),
        "jezzwtf_character_system_prompt": "embedded system",
        "jezzwtf_character_avatar_png_b64": base64.b64encode(buf.getvalue()).decode(),
    }
    header = json.dumps({"__metadata__": meta}).encode()
    rdir = tmp_path / "refs"
    rdir.mkdir()
    (rdir / "ref.safetensors").write_bytes(struct.pack("<Q", len(header)) + header)
    monkeypatch.setenv("JEZZWTF_REFMOD_DIR", str(rdir))
    assert cc.list_choices() == ["refmod:ref.safetensors"]
    routes = _Routes()
    cc.register(routes)
    resp = _call(routes, "/jezzwtf/character/avatar", "character=refmod%3Aref.safetensors")
    assert resp.content_type == "image/png"
    loaded = cc.load_selected("refmod:ref.safetensors", "")
    assert loaded["card"]["system_prompt"] == "embedded system" and loaded["source"] == "refmod"
    assert tuple(cc.avatar_tensor(loaded).shape) == (1, 4, 4, 3)
