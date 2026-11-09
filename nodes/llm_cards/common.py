"""Small helpers shared by the LLM + cards nodes.

Everything that touches ComfyUI (`server`, `folder_paths`) is imported lazily so the
pure logic in this package can be imported and tested without ComfyUI.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from typing import Callable, Mapping, Sequence, Union

import numpy as np
from PIL import Image

log = logging.getLogger("jezzwtf.llm_cards")

JSONScalar = Union[str, int, float, bool, None]
JSONValue = Union[JSONScalar, list["JSONValue"], dict[str, "JSONValue"]]
JSONDict = dict[str, JSONValue]

# Most images one request may carry; larger batches are evenly subsampled (payload and VRAM guard).
MAX_IMAGES = 16

CATEGORY_LLM = "JezzWTF/LLM"
CATEGORY_CARDS = "JezzWTF/Cards"


class AnyType(str):
    """A socket type that compares equal to every other type."""

    def __ne__(self, other: object) -> bool:
        return False


ANY = AnyType("*")


# --------------------------------------------------------------------------- server


def send_event(event: str, payload: Mapping[str, object]) -> None:
    """Broadcast a websocket event to every client; failures are ignored."""
    try:
        from server import PromptServer  # type: ignore[import-not-found]

        PromptServer.instance.send_sync(event, dict(payload))
    except Exception:  # noqa: BLE001 - progress events are best effort
        pass


def register_routes(register: Callable[[object], None]) -> bool:
    """Call `register(routes)` with ComfyUI's aiohttp route table, if it exists."""
    try:
        from server import PromptServer  # type: ignore[import-not-found]

        instance = getattr(PromptServer, "instance", None)
        if instance is None:
            return False
        register(instance.routes)
        return True
    except Exception as exc:  # noqa: BLE001 - running outside ComfyUI
        log.debug("jezzwtf llm_cards: routes not registered (%s)", exc)
        return False


def folder_for_type(kind: str | None, default: str = "input") -> str:
    """Resolve ComfyUI's input/temp/output directory by its `type` name."""
    import folder_paths  # type: ignore[import-not-found]

    kind = (kind or default).strip().lower()
    if kind == "output":
        return str(folder_paths.get_output_directory())
    if kind == "temp":
        return str(folder_paths.get_temp_directory())
    return str(folder_paths.get_input_directory())


# --------------------------------------------------------------------------- images


def frame_to_pil(frame: object) -> Image.Image:
    """`[H,W,C]` float 0..1 tensor/array -> RGB PIL image."""
    arr = _to_numpy(frame)
    arr = np.clip(arr, 0.0, 1.0)
    arr = np.round(arr * 255.0).astype(np.uint8)
    if arr.ndim == 3 and arr.shape[2] == 1:
        arr = arr[:, :, 0]
    img = Image.fromarray(arr)
    return img.convert("RGB") if img.mode != "RGB" else img


def frame_to_uint8(frame: object) -> np.ndarray:
    """`[H,W,C]` float tensor -> uint8 array (clip x255), single channel squeezed."""
    arr = _to_numpy(frame)
    arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    if arr.ndim == 3 and arr.shape[2] == 1:
        arr = arr[:, :, 0]
    return arr


def _to_numpy(value: object) -> np.ndarray:
    detach = getattr(value, "detach", None)
    if callable(detach):
        value = detach().cpu().float().numpy()  # type: ignore[attr-defined]
    return np.asarray(value, dtype=np.float32)


def pil_to_tensor(img: Image.Image) -> "torch.Tensor":  # noqa: F821
    import torch

    arr = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def encode_jpeg_b64(img: Image.Image, max_side: int, quality: int = 90) -> str:
    """Downscale (keeping aspect) so the long side is <= max_side, JPEG, base64."""
    img = img.convert("RGB")
    if max(img.size) > max_side > 0:
        img = img.copy()
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def linspace_indices(total: int, count: int) -> list[int]:
    """`count` evenly spaced, rounded indices over `0..total-1` (duplicates removed, ordered)."""
    if total <= 0 or count <= 0:
        return []
    if count == 1:
        return [0]
    vals = np.linspace(0, total - 1, count)
    out: list[int] = []
    for v in vals:
        i = int(round(float(v)))
        if not out or out[-1] != i:
            out.append(i)
    return out


# --------------------------------------------------------------------------- text


_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|%\x00-\x1f\x7f]')


def safe_name(name: str, limit: int = 80, empty: str = "card") -> str:
    """File-name-safe version of `name` (spec 5.3)."""
    out = _UNSAFE_NAME.sub("_", name or "")
    out = out.strip(" .")[:limit].strip(" .")
    return out or empty


def safe_prefix_path(prefix: str, empty: str = "workflow") -> str:
    """Split on / and \\, drop empty/./.. parts, sanitise each, rejoin with / (spec 6.4)."""
    parts = [p for p in re.split(r"[\\/]", prefix or "") if p not in ("", ".", "..")]
    cleaned = [safe_name(p, empty="") for p in parts]
    cleaned = [p for p in cleaned if p]
    return "/".join(cleaned) or empty


_FENCE = re.compile(r"^```[A-Za-z0-9_-]*\s*\n?(.*?)\n?```$", re.S)
_FENCE_ANY = re.compile(r"```[A-Za-z0-9_-]*[ \t]*\n?(.*?)\n?```", re.S)


def clean_json_text(text: str) -> str:
    """Strip BOM, a leading <think> block, ``` fences and prose around the outermost JSON object."""
    s = (text or "").lstrip("﻿").strip()
    if "</think>" in s:
        s = s.rpartition("</think>")[2].strip()
    else:
        s = s.replace("<think>", "", 1).strip()
    m = _FENCE.match(s)
    if m:
        s = m.group(1).strip()
    elif "```" in s:
        blocks = [b.strip() for b in _FENCE_ANY.findall(s)]
        brace = [b for b in blocks if b.startswith("{")]
        if brace:
            s = max(brace, key=len)
    if not s.startswith(("{", "[", "\"")):
        first, last = s.find("{"), s.rfind("}")
        if 0 <= first < last:
            s = s[first : last + 1]
    elif s.startswith("{") and not s.endswith("}"):
        last = s.rfind("}")
        if last > 0:
            s = s[: last + 1]
    return s


class JSONTextError(ValueError):
    pass


def repair_json_text(s: str) -> str | None:
    """Fix the usual small-model slips: unmatched closers, missing closers, trailing commas.

    Returns None when nothing could be changed (so the caller reports the original error)."""
    out: list[str] = []
    stack: list[str] = []
    in_str = False
    esc = False
    for ch in s:
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if not stack or stack[-1] != ch:
                continue  # stray or mismatched closer
            stack.pop()
        if ch in "}]":
            while out and out[-1].isspace():
                out.pop()
            if out and out[-1] == ",":
                out.pop()
        out.append(ch)
    if in_str:
        return None
    while out and out[-1].isspace():
        out.pop()
    if out and out[-1] == ",":
        out.pop()
    out.extend(reversed(stack))
    fixed = "".join(out)
    return fixed if fixed != s else None


def parse_json_text(text: str) -> JSONValue:
    """Parse JSON, raising a readable error with line, column and a snippet."""
    s = clean_json_text(text)
    if not s:
        raise JSONTextError("The JSON text is empty.")
    try:
        return json.loads(s)
    except json.JSONDecodeError as exc:
        repaired = repair_json_text(s)
        if repaired is not None:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
        start = max(0, exc.pos - 40)
        snippet = s[start : exc.pos + 20].replace("\n", "\\n")
        raise JSONTextError(
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}. Near: …{snippet}…"
        ) from exc


def first_str(values: Sequence[object]) -> str:
    for v in values:
        if isinstance(v, str) and v:
            return v
    return ""
