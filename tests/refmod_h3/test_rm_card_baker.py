"""Card baker: header-only rewrite keeps tensor bytes identical; verification catches tampering."""
from __future__ import annotations

import base64
import json
import os
import struct
from pathlib import Path

import pytest
import torch
from safetensors import safe_open

from refmod_h3 import _comfy, bundle, card_baker
from refmod_h3._types import RefModError
from refmod_h3.bundle import RefMod

CARD = {"spec": "chara_card_v2", "spec_version": "2.0",
        "data": {"name": "Alice", "description": "curious", "first_mes": "hi", "personality": "kind"}}
META = {
    card_baker.KEY_VERSION: "1",
    card_baker.KEY_NAME: "Alice",
    card_baker.KEY_CARD: json.dumps(CARD, ensure_ascii=False),
    card_baker.KEY_AVATAR: base64.b64encode(b"\x89PNG-fake").decode("ascii"),
}


def data_section(path: str) -> bytes:
    with open(path, "rb") as fh:
        (n,) = struct.unpack("<Q", fh.read(8))
        fh.seek(8 + n)
        return fh.read()


@pytest.fixture()
def base_file(tmp_path: Path) -> str:
    dest = os.path.join(str(tmp_path), "base.safetensors")
    g = torch.Generator().manual_seed(1)
    mods = [RefMod("v", "video", torch.randn(1, 24, 5, 4, 4, generator=g).to(torch.float16)),
            RefMod("a", "audio", torch.randn(1, 32, 2, 12, generator=g))]
    bundle.write_bundle(dest, "base", mods)
    return dest


def test_embed_keeps_every_tensor_byte_and_merges_metadata(base_file: str, tmp_path: Path) -> None:
    dst = os.path.join(str(tmp_path), "out", "char.safetensors")
    card_baker.embed_metadata(base_file, dst, META)
    assert data_section(base_file) == data_section(dst)
    src_header, _ = bundle.read_header(base_file)
    dst_header, _ = bundle.read_header(dst)
    assert {k: v for k, v in src_header.items() if k != "__metadata__"} == \
           {k: v for k, v in dst_header.items() if k != "__metadata__"}
    meta = dst_header["__metadata__"]
    assert "refmod_meta" in meta and meta[card_baker.KEY_NAME] == "Alice"  # old + new keys
    with safe_open(base_file, framework="pt") as a, safe_open(dst, framework="pt") as b:
        for key in a.keys():
            assert torch.equal(a.get_tensor(key), b.get_tensor(key))
    # the bundle still loads as a RefMod
    assert [m.name for m in bundle.load_refmod_file(dst)] == ["v", "a"]
    card_baker.verify_embed(base_file, dst, META)
    card, prompt, avatar = card_baker.read_character(dst)
    assert card == CARD and prompt == "" and avatar == META[card_baker.KEY_AVATAR]


def test_header_is_padded_to_8_and_compact(base_file: str, tmp_path: Path) -> None:
    dst = os.path.join(str(tmp_path), "pad.safetensors")
    card_baker.embed_metadata(base_file, dst, META)
    with open(dst, "rb") as fh:
        (n,) = struct.unpack("<Q", fh.read(8))
        raw = fh.read(n)
    assert n % 8 == 0
    text = raw.decode("utf-8").rstrip(" ")
    assert text == json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=False)
    assert "Alice" in text


def test_character_only_file_has_no_tensors(tmp_path: Path) -> None:
    dst = os.path.join(str(tmp_path), "only.safetensors")
    meta = {**META, card_baker.KEY_PROMPT: "You are Alice."}
    card_baker.embed_metadata(None, dst, meta)
    header, off = bundle.read_header(dst)
    assert list(header) == ["__metadata__"] and os.path.getsize(dst) == off
    card_baker.verify_embed(None, dst, meta)
    assert card_baker.read_character(dst)[1] == "You are Alice."


def test_same_file_is_refused_and_tampering_detected(base_file: str, tmp_path: Path) -> None:
    with pytest.raises(RefModError, match="same file"):
        card_baker.embed_metadata(base_file, base_file, META)
    dst = os.path.join(str(tmp_path), "t.safetensors")
    card_baker.embed_metadata(base_file, dst, META)
    with open(dst, "r+b") as fh:
        fh.seek(-1, os.SEEK_END)
        last = fh.read(1)
        fh.seek(-1, os.SEEK_END)
        fh.write(bytes([last[0] ^ 0xFF]))
    with pytest.raises(RefModError, match="tensor data differs"):
        card_baker.verify_embed(base_file, dst, META)
    with pytest.raises(RefModError, match="metadata differs"):
        card_baker.verify_embed(base_file, dst, {**META, card_baker.KEY_NAME: "Bob"})
    assert not os.path.exists(dst + ".tmp")


def test_read_character_requires_card(base_file: str) -> None:
    with pytest.raises(RefModError, match="no embedded character"):
        card_baker.read_character(base_file)


def test_output_path_counter_prefix_and_traversal(tmp_path: Path) -> None:
    root = str(tmp_path)
    first = card_baker.output_path("Refmods/%name%", "Alice", root)
    assert first.endswith(os.path.join("Refmods", "Alice_00001_.safetensors"))
    open(first, "wb").close()
    assert card_baker.output_path("Refmods/%name%", "Alice", root).endswith("Alice_00002_.safetensors")
    sneaky = card_baker.output_path("../../etc/passwd", "x", root)
    assert os.path.commonpath([os.path.abspath(sneaky), root]) == os.path.abspath(root)
    assert card_baker.output_path("", "Zed", root).endswith("Zed_00001_.safetensors")


def test_base_choice_and_path_clean(refmod_root: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWTF_REFMOD_DIR", refmod_root)
    os.makedirs(os.path.join(refmod_root, "sub"))
    bundle.write_bundle(os.path.join(refmod_root, "sub", "x.safetensors"), "x",
                        [RefMod("v", "image", torch.zeros(1, 24, 1, 2, 2, dtype=torch.float16))])
    choices = card_baker.base_choices()
    assert choices[0] == card_baker.NONE_CHOICE and "sub/x.safetensors" in choices
    assert card_baker.resolve_base("sub/x.safetensors") == os.path.realpath(os.path.join(refmod_root, "sub", "x.safetensors"))
    assert card_baker.resolve_base(card_baker.NONE_CHOICE) is None
    with pytest.raises(RefModError, match="not found"):
        card_baker.resolve_base("../escape.safetensors")
    for junk in ("none", "None", "null", "undefined", "", None, '"none"'):
        assert card_baker._clean_path(junk) == ""
    assert card_baker._clean_path('  "C:/x/y.safetensors" ') == "C:/x/y.safetensors"


def test_node_end_to_end_hybrid(base_file: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out_dir, tmp_dir = os.path.join(str(tmp_path), "out"), os.path.join(str(tmp_path), "tmp")
    os.makedirs(out_dir)
    os.makedirs(tmp_dir)
    monkeypatch.setattr(_comfy, "output_dir", lambda: out_dir)
    monkeypatch.setattr(_comfy, "temp_dir", lambda: tmp_dir)
    image = torch.rand(1, 64, 48, 3)
    res = card_baker.JWTFRefmodCardBaker().bake(image, json.dumps(CARD), "Refmods/%name%",
                                                 card_baker.NONE_CHOICE, 64, True,
                                                 system_prompt="Stay in character.", base_refmod_path=base_file,
                                                 save_to=card_baker.SAVE_TO_OUTPUT)
    dst, name = res["result"]
    assert name == "Alice" and os.path.isfile(dst) and dst.startswith(out_dir)
    assert data_section(dst) == data_section(base_file)
    card, prompt, avatar = card_baker.read_character(dst)
    assert card["data"]["name"] == "Alice" and prompt == "Stay in character."
    info = res["ui"]["card_info"][0]["refmod"]
    assert info["kind"] == "hybrid" and info["tensors"] == 2 and info["base"] == "base.safetensors"
    preview = res["ui"]["card_preview"][0]
    assert preview["type"] == "temp" and os.path.isfile(os.path.join(tmp_dir, preview["filename"]))
    # character-only
    res2 = card_baker.JWTFRefmodCardBaker().bake(image, json.dumps(CARD), "Refmods/%name%",
                                                  card_baker.NONE_CHOICE, 64, True,
                                                  save_to=card_baker.SAVE_TO_OUTPUT)
    assert res2["ui"]["card_info"][0]["refmod"]["kind"] == "character-only"
    with pytest.raises(RefModError, match="base_refmod_path not found"):
        card_baker.JWTFRefmodCardBaker().bake(image, json.dumps(CARD), "x", card_baker.NONE_CHOICE, 64, True,
                                               base_refmod_path=os.path.join(str(tmp_path), "nope.safetensors"))


def test_rebaking_with_a_blank_prompt_drops_the_stale_prompt(base_file: str, tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    out_dir, tmp_dir = os.path.join(str(tmp_path), "out"), os.path.join(str(tmp_path), "tmp")
    os.makedirs(out_dir)
    os.makedirs(tmp_dir)
    monkeypatch.setattr(_comfy, "output_dir", lambda: out_dir)
    monkeypatch.setattr(_comfy, "temp_dir", lambda: tmp_dir)
    image = torch.rand(1, 64, 48, 3)
    node = card_baker.JWTFRefmodCardBaker()
    first = node.bake(image, json.dumps(CARD), "first", card_baker.NONE_CHOICE, 64, True,
                      system_prompt="Stay in character.", base_refmod_path=base_file)["result"][0]
    assert card_baker.read_character(first)[1] == "Stay in character."
    second = node.bake(image, json.dumps(CARD), "second", card_baker.NONE_CHOICE, 64, True,
                       system_prompt="", base_refmod_path=first)["result"][0]
    assert card_baker.read_character(second)[1] == ""
    header, _ = bundle.read_header(second)
    assert card_baker.KEY_PROMPT not in header["__metadata__"]


def test_embed_refuses_a_base_file_shorter_than_its_header_claims(base_file: str, tmp_path: Path) -> None:
    truncated = os.path.join(str(tmp_path), "short.safetensors")
    with open(base_file, "rb") as fh:
        data = fh.read()
    with open(truncated, "wb") as fh:
        fh.write(data[:-16])
    with pytest.raises(RefModError, match="truncated or corrupt"):
        card_baker.embed_metadata(truncated, os.path.join(str(tmp_path), "o.safetensors"), META)
    assert not os.path.exists(os.path.join(str(tmp_path), "o.safetensors"))


def test_default_save_goes_to_the_refmods_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Character Chat lists models/refmods, so a freshly baked character must land there by default."""
    from refmod_h3 import library

    root = os.path.join(str(tmp_path), "refmods_root")
    os.makedirs(root)
    library.set_search_dirs_override([root])
    out_dir = os.path.join(str(tmp_path), "out")
    os.makedirs(out_dir)
    monkeypatch.setattr(_comfy, "output_dir", lambda: out_dir)
    monkeypatch.setattr(_comfy, "temp_dir", lambda: str(tmp_path))
    res = card_baker.JWTFRefmodCardBaker().bake(torch.rand(1, 64, 48, 3), json.dumps(CARD), "%name%",
                                                 card_baker.NONE_CHOICE, 64, True)
    dst = res["result"][0]
    assert os.path.dirname(dst) == root and os.path.isfile(dst)
    assert not os.listdir(out_dir)
