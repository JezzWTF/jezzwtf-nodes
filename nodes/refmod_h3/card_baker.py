"""Refmod character-card baker (spec section 10).

Stores a Character Card V2 (+ optional system prompt and avatar) in a ``.safetensors``
header, either as a tensor-less file or as a copy of an existing refmod whose data
section is preserved byte for byte (header-only rewrite).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import secrets
import struct

import numpy as np
import torch
from PIL import Image

from . import _comfy, library
from ._types import CATEGORY_REFMOD, InputTypes, JSONDict, JSONValue, RefModError
from .bundle import read_header
from .cards import card_info, parse_card, safe_name

log = logging.getLogger("jezzwtf.refmod_h3")

NONE_CHOICE = "(none - character-only file)"
SAVE_TO_REFMODS = "refmods folder"
SAVE_TO_OUTPUT = "output folder"
KEY_VERSION = "jezzwtf_character_version"
KEY_NAME = "jezzwtf_character_name"
KEY_CARD = "jezzwtf_character_card"
KEY_PROMPT = "jezzwtf_character_system_prompt"
KEY_AVATAR = "jezzwtf_character_avatar_png_b64"
CHUNK = 16 * 1024 * 1024
REFMOD_FOLDER_KEYS = ("refmod", "refmods", "h3_refmod", "minimax_refmod", "reference", "references")
ENV_DIRS = ("JWTF_REFMOD_DIR",)


# --------------------------------------------------------------------------- header rewrite (pure)

def _serialise_header(header: dict[str, JSONValue]) -> bytes:
    raw = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    pad = (-len(raw)) % 8
    return raw + b" " * pad


def _check_data_extent(src: str, entries: dict[str, JSONValue], data_offset: int) -> None:
    """The header's tensor offsets must fit inside the file; otherwise copying would silently truncate or pad."""
    end = 0
    for name, info in entries.items():
        offsets = info.get("data_offsets") if isinstance(info, dict) else None
        if not (isinstance(offsets, list) and len(offsets) == 2 and all(isinstance(o, int) for o in offsets)):
            raise RefModError(f"{os.path.basename(src)}: tensor {name!r} has no valid data_offsets")
        end = max(end, int(offsets[1]))
    if data_offset + end > os.path.getsize(src):
        raise RefModError(f"{os.path.basename(src)}: header describes {data_offset + end} bytes but the file has "
                          f"{os.path.getsize(src)} (truncated or corrupt)")


def embed_metadata(src: str | None, dst: str, new_meta: dict[str, str], drop: tuple[str, ...] = ()) -> None:
    """Write ``dst`` = ``src`` with ``new_meta`` merged into ``__metadata__``; data section copied.

    Without ``src`` the file is header-only (no tensors).
    """
    if src is not None and os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dst)):
        raise RefModError("source and destination refmod are the same file")
    old_meta: dict[str, str] = {}
    entries: dict[str, JSONValue] = {}
    data_offset = 0
    if src is not None:
        header, data_offset = read_header(src)
        meta = header.get("__metadata__")
        if isinstance(meta, dict):
            old_meta = {str(k): str(v) for k, v in meta.items()}
        entries = {k: v for k, v in header.items() if k != "__metadata__"}
        _check_data_extent(src, entries, data_offset)
    merged = {**{k: v for k, v in old_meta.items() if k not in drop}, **{k: str(v) for k, v in new_meta.items()}}
    out_header: dict[str, JSONValue] = {"__metadata__": merged}  # type: ignore[dict-item]
    out_header.update(entries)
    blob = _serialise_header(out_header)
    tmp = dst + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)
    try:
        with open(tmp, "wb") as out:
            out.write(struct.pack("<Q", len(blob)))
            out.write(blob)
            if src is not None:
                with open(src, "rb") as fh:
                    fh.seek(data_offset)
                    while True:
                        buf = fh.read(CHUNK)
                        if not buf:
                            break
                        out.write(buf)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _data_equal(a: str, a_off: int, b: str, b_off: int) -> bool:
    if os.path.getsize(a) - a_off != os.path.getsize(b) - b_off:
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        fa.seek(a_off)
        fb.seek(b_off)
        while True:
            x = fa.read(CHUNK)
            y = fb.read(CHUNK)
            if x != y:
                return False
            if not x:
                return True


def verify_embed(src: str | None, dst: str, new_meta: dict[str, str], drop: tuple[str, ...] = ()) -> None:
    header, off = read_header(dst)
    meta = header.get("__metadata__")
    if not isinstance(meta, dict):
        raise RefModError("verify: metadata missing after write")
    expected_meta: dict[str, str] = {}
    entries_src: dict[str, JSONValue] = {}
    src_off = 0
    if src is not None:
        sh, src_off = read_header(src)
        sm = sh.get("__metadata__")
        if isinstance(sm, dict):
            expected_meta = {str(k): str(v) for k, v in sm.items() if k not in drop}
        entries_src = {k: v for k, v in sh.items() if k != "__metadata__"}
    expected_meta.update(new_meta)
    if {str(k): str(v) for k, v in meta.items()} != expected_meta:
        raise RefModError("verify: metadata differs after write")
    entries_dst = {k: v for k, v in header.items() if k != "__metadata__"}
    if entries_dst != entries_src:
        raise RefModError("verify: tensor entries differ after write")
    if src is not None:
        if not _data_equal(src, src_off, dst, off):
            raise RefModError("verify: tensor data differs after write")
    elif os.path.getsize(dst) != off:
        raise RefModError("verify: character-only file has a data section")


def read_character(path: str) -> tuple[JSONDict, str, str]:
    """(card, system_prompt, avatar_b64) from a refmod header."""
    header, _ = read_header(path)
    meta = header.get("__metadata__")
    if not isinstance(meta, dict):
        raise RefModError(f"{os.path.basename(path)} has no embedded character")

    def get(key: str) -> JSONValue:
        return meta.get(key)

    raw_card = get(KEY_CARD)
    if raw_card is None:
        raise RefModError(f"{os.path.basename(path)} has no embedded character")
    card = json.loads(str(raw_card))
    if not isinstance(card, dict):
        raise RefModError("embedded card is not an object")
    return card, str(get(KEY_PROMPT) or ""), str(get(KEY_AVATAR) or "")


def avatar_png_b64(image: torch.Tensor, max_size: int) -> tuple[str, bytes]:
    frame = image[0] if image.dim() == 4 else image
    arr = (frame[..., :3].clamp(0, 1).cpu().numpy() * 255.0).round().astype(np.uint8)
    im = Image.fromarray(arr).convert("RGB")
    if max(im.size) > max_size:
        s = max_size / max(im.size)
        im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    data = buf.getvalue()
    return base64.b64encode(data).decode("ascii"), data


# --------------------------------------------------------------------------- paths

def refmod_dirs() -> list[str]:
    cands: list[str] = []
    for env in ENV_DIRS:
        cands.extend(p for p in os.environ.get(env, "").split(os.pathsep) if p.strip())
    for key in REFMOD_FOLDER_KEYS:
        cands.extend(_comfy.folder_paths_for(key))
    cands.append(os.path.join(_comfy.models_dir(), "refmods"))
    out: list[str] = []
    seen: set[str] = set()
    for c in cands:
        k = os.path.normcase(os.path.abspath(c))
        if k in seen or not os.path.isdir(c):
            continue
        seen.add(k)
        out.append(os.path.abspath(c))
    return out


def base_choices() -> list[str]:
    names: list[str] = []
    for d in refmod_dirs():
        for root, dirnames, files in os.walk(d):
            dirnames.sort()
            for f in sorted(files):
                if f.endswith(".safetensors"):
                    rel = os.path.relpath(os.path.join(root, f), d).replace("\\", "/")
                    if rel not in names:
                        names.append(rel)
    return [NONE_CHOICE] + sorted(names, key=str.casefold)


def resolve_base(choice: str) -> str | None:
    if not choice or choice == NONE_CHOICE:
        return None
    for d in refmod_dirs():
        p = os.path.realpath(os.path.join(d, *choice.split("/")))
        base = os.path.realpath(d)
        try:
            inside = os.path.commonpath([os.path.normcase(p), os.path.normcase(base)]) == os.path.normcase(base)
        except ValueError:
            inside = False
        if inside and os.path.isfile(p):
            return p
    raise RefModError(f"base refmod {choice!r} not found")


_PART_BAD = re.compile(r'[\\:*?"<>|\x00-\x1f]')


def output_path(prefix: str, name: str, out_root: str) -> str:
    replaced = str(prefix or "").replace("%name%", safe_name(name))
    parts = [p for p in replaced.split("/") if p not in ("", ".", "..")]
    parts = [_PART_BAD.sub("_", p).strip(" .") or "_" for p in parts] or [safe_name(name)]
    folder = os.path.join(out_root, *parts[:-1])
    os.makedirs(folder, exist_ok=True)
    counter = 1
    while True:
        path = os.path.join(folder, f"{parts[-1]}_{counter:05d}_.safetensors")
        if not os.path.exists(path):
            return path
        counter += 1


def _clean_path(v: str | None) -> str:
    s = str(v or "").strip().strip('"').strip("'")
    return "" if s.casefold() in ("none", "null", "undefined") else s


# --------------------------------------------------------------------------- node

class JWTFRefmodCardBaker:
    CATEGORY = CATEGORY_REFMOD
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("saved_path", "character_name")
    FUNCTION = "bake"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        choices = base_choices()
        return {
            "required": {
                "image": ("IMAGE",),
                "json_text": ("STRING", {"multiline": True, "forceInput": True}),
                "filename_prefix": ("STRING", {"default": "%name%"}),
                "base_refmod": (choices, {"default": NONE_CHOICE}),
                "avatar_max_size": ("INT", {"default": 512, "min": 64, "max": 2048, "step": 16}),
                "fill_missing_fields": ("BOOLEAN", {"default": True, "label_on": "fill missing V2 fields",
                                                    "label_off": "keep JSON exactly as pasted"}),
            },
            "optional": {
                "system_prompt": ("STRING", {"multiline": True, "forceInput": True}),
                "base_refmod_path": ("STRING", {"default": ""}),
                "save_to": ([SAVE_TO_REFMODS, SAVE_TO_OUTPUT], {"default": SAVE_TO_REFMODS}),
            },
        }

    def bake(self, image: torch.Tensor, json_text: str, filename_prefix: str, base_refmod: str,
             avatar_max_size: int, fill_missing_fields: bool, system_prompt: str | None = None,
             base_refmod_path: str = "", save_to: str = SAVE_TO_REFMODS) -> dict[str, object]:
        card, notes = parse_card(json_text, bool(fill_missing_fields))
        data = card["data"]
        assert isinstance(data, dict)
        name = str(data.get("name", "")).strip()
        explicit = _clean_path(base_refmod_path)
        if explicit:
            if not os.path.isfile(explicit):
                raise RefModError(f"base_refmod_path not found: {explicit}")
            src: str | None = explicit
        else:
            src = resolve_base(base_refmod)
        # models/refmods is where Character Chat looks, so a new character shows up in its list at once.
        out_root = _comfy.output_dir() if save_to == SAVE_TO_OUTPUT else library.save_root()
        dst = output_path(filename_prefix, name, out_root)
        avatar_b64, avatar_png = avatar_png_b64(image, int(avatar_max_size))
        card_json = json.dumps(card, ensure_ascii=False)
        meta = {KEY_VERSION: "1", KEY_NAME: name, KEY_CARD: card_json, KEY_AVATAR: avatar_b64}
        prompt = str(system_prompt or "")
        drop: tuple[str, ...] = ()
        if prompt.strip():
            meta[KEY_PROMPT] = prompt
        else:
            drop = (KEY_PROMPT,)  # a blank prompt must not keep the base file's stale one
        embed_metadata(src, dst, meta, drop)
        verify_embed(src, dst, meta, drop)
        rcard, rprompt, ravatar = read_character(dst)
        if rcard != json.loads(card_json) or ravatar != avatar_b64 or (prompt.strip() and rprompt != prompt):
            raise RefModError("verify: character did not round-trip")
        header, _ = read_header(dst)
        tensors = [k for k in header if k != "__metadata__"]
        temp_name = f"jwtf_refmod_{safe_name(name)}_{secrets.token_hex(4)}.png"
        with open(os.path.join(_comfy.temp_dir(), temp_name), "wb") as fh:
            fh.write(avatar_png)
        info = card_info(card, notes, len(avatar_b64))
        info["refmod"] = {
            "kind": "hybrid" if src else "character-only", "tensors": len(tensors),
            "bytes": os.path.getsize(dst), "saved": os.path.relpath(dst, out_root).replace("\\", "/"),
            "base": os.path.basename(src) if src else "",
        }
        return {"ui": {"card_preview": [{"filename": temp_name, "subfolder": "", "type": "temp"}],
                       "card_info": [info]},
                "result": (dst, name)}


NODE_CLASS_MAPPINGS = {"JWTFRefmodCardBaker": JWTFRefmodCardBaker}
NODE_DISPLAY_NAME_MAPPINGS = {"JWTFRefmodCardBaker": "Refmod Character Card Baker"}
