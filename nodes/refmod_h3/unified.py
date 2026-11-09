"""Unified image-model RefMod (spec section 8): one Bake and one Apply for edit models
that consume ``reference_latents`` (Qwen Image 2.1, Fibo 2, Flux 3).

A registry of handlers decides file format, encoding and how references reach the
conditioning. Adding a model = registering one more ``Handler``.
"""
from __future__ import annotations

from io import BytesIO
import base64
import json
import logging
import math
import os
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import torch
from PIL import Image
from safetensors import safe_open

from comfy_api.latest import io

from . import _comfy
from ._types import JSONDict, RefModError
from .bundle import _atomic_save, read_metadata
from .extract import resize_frames
from .library import RESERVED_DIRS, check_rel, is_inside, save_root, search_dirs

log = logging.getLogger("jezzwtf.refmod_h3")

AUTO = "auto (from refmod)"
NONE = "None"
EXTRA_SCALE_LABELS = ("keep aspect (resolution)", "match first reference")
TOKEN_DOWNSCALE = 16
THUMB_EDGE = 192

Cond = list[list[object]]


@dataclass
class Encoded:
    lat: torch.Tensor
    img: torch.Tensor | None  # [1,H,W,3] float RGB, for image-storing handlers
    size: tuple[int, int]     # (W, H) pixels


@dataclass
class ApplyContext:
    clip: object | None
    prompt: str
    negative_prompt: str
    positive: Cond | None
    negative: Cond | None
    ref_strength: float
    ref_on_negative: bool


@dataclass
class Handler:
    key: str
    label: str
    format: str
    meta_key: str
    subfolder: str
    max_refs: int
    latent_channels: int
    stores_images: bool
    accent: str
    apply_needs: tuple[str, ...]
    apply_uses: frozenset[str]
    encode: Callable[["Handler", object, torch.Tensor, int], Encoded]
    extras: Callable[["Handler", list[Encoded], int], JSONDict]
    validate: Callable[["Handler", torch.Tensor, torch.Tensor | None], None]
    build: Callable[["Handler", ApplyContext, list[torch.Tensor], list[torch.Tensor]], tuple[Cond, Cond]]
    token_downscale: int = TOKEN_DOWNSCALE
    bake_needs: tuple[str, ...] = ("vae",)
    bake_uses: frozenset[str] = field(default_factory=lambda: frozenset({"vae"}))

    def ui(self) -> JSONDict:
        return {
            "key": self.key, "label": self.label, "accent": self.accent, "subfolder": self.subfolder,
            "max_refs": self.max_refs, "token_downscale": self.token_downscale,
            "apply_needs": list(self.apply_needs), "apply_uses": sorted(self.apply_uses),
            "bake_needs": list(self.bake_needs), "bake_uses": sorted(self.bake_uses),
        }


# --------------------------------------------------------------------------- shared helpers

def resize32(frame: torch.Tensor, resolution: int) -> torch.Tensor:
    """[1,H,W,C] to ~resolution² px, sides on a 32 grid (R = 0 rounds the own size)."""
    _, h, w, _ = frame.shape
    if resolution > 0:
        tw = int(round(math.sqrt(resolution * resolution * w / h) / 32.0)) * 32
        th = int(round(math.sqrt(resolution * resolution * h / w) / 32.0)) * 32
    else:
        tw = int(round(w / 32.0)) * 32
        th = int(round(h / 32.0)) * 32
    tw, th = max(32, tw), max(32, th)
    if (tw, th) == (w, h):
        return frame
    bchw = frame.movedim(-1, 1)
    return _comfy.common_upscale(bchw, tw, th, "lanczos", "disabled").movedim(1, -1)


def rgb_over_white(frame: torch.Tensor) -> torch.Tensor:
    if frame.shape[-1] >= 4:
        a = frame[..., 3:4]
        return (frame[..., :3] * a + (1.0 - a)).clamp(0.0, 1.0)
    return frame[..., :3]


def _encode_4d(vae: object, pixels: torch.Tensor, channels: int, label: str) -> torch.Tensor:
    lat = vae.encode(pixels)  # type: ignore[attr-defined]
    if not isinstance(lat, torch.Tensor) or lat.dim() != 4 or lat.shape[1] != channels:
        shape = list(lat.shape) if isinstance(lat, torch.Tensor) else type(lat).__name__
        raise RefModError(f"{label}: VAE returned {shape}, expected [1, {channels}, h, w]; wrong VAE for this model?")
    return lat.float()


def _as_frame(frame: torch.Tensor) -> torch.Tensor:
    f = frame if frame.dim() == 4 else frame.unsqueeze(0)
    return f[:1].float()


def _enc_qwen(h: Handler, vae: object, frame: torch.Tensor, resolution: int) -> Encoded:
    resized = resize32(_as_frame(frame), resolution)
    rgb = rgb_over_white(resized)
    # Qwen encodes the resized image as given (alpha included when present), like the original.
    lat = _encode_4d(vae, resized, h.latent_channels, h.label)
    return Encoded(lat=lat, img=rgb, size=(int(rgb.shape[2]), int(rgb.shape[1])))


def _enc_fibo(h: Handler, vae: object, frame: torch.Tensor, resolution: int) -> Encoded:
    rgb = rgb_over_white(resize32(_as_frame(frame), resolution))
    lat = _encode_4d(vae, rgb, h.latent_channels, h.label)
    return Encoded(lat=lat, img=rgb, size=(int(rgb.shape[2]), int(rgb.shape[1])))


def _enc_flux3(h: Handler, vae: object, frame: torch.Tensor, resolution: int) -> Encoded:
    rgb = _as_frame(frame)[..., :3]
    if resolution > 0:
        _, ih, iw, _ = rgb.shape
        s = math.sqrt(resolution * resolution / (iw * ih))
        tw, th = max(1, int(round(iw * s))), max(1, int(round(ih * s)))
        rgb = resize_frames(rgb, tw, th)
    lat = _encode_4d(vae, rgb, h.latent_channels, h.label)
    return Encoded(lat=lat, img=None, size=(int(rgb.shape[2]), int(rgb.shape[1])))


def _extras_sizes(h: Handler, encs: list[Encoded], resolution: int) -> JSONDict:
    return {"sizes": [[e.size[0], e.size[1]] for e in encs], "latent_channels": h.latent_channels,
            "downscale": TOKEN_DOWNSCALE, "resolution": resolution}


def _extras_flux3(h: Handler, encs: list[Encoded], resolution: int) -> JSONDict:
    return {"latent_channels": h.latent_channels, "shapes": [list(e.lat.shape) for e in encs],
            "megapixels": resolution * resolution / (1024.0 * 1024.0)}


def _validate_with_image(h: Handler, lat: torch.Tensor, img: torch.Tensor | None) -> None:
    if lat.dim() != 4 or lat.shape[0] != 1 or lat.shape[1] != h.latent_channels:
        raise RefModError(f"{h.label} refmod: latent must be [1, {h.latent_channels}, h, w], got {list(lat.shape)}")
    if img is None or img.dim() != 4 or img.shape[0] != 1 or img.shape[-1] != 3:
        raise RefModError(f"{h.label} refmod: image must be [1, H, W, 3]")
    if img.shape[1] // 16 != lat.shape[2] or img.shape[2] // 16 != lat.shape[3]:
        raise RefModError(f"{h.label} refmod: image {img.shape[2]}x{img.shape[1]} does not match latent "
                          f"{lat.shape[3]}x{lat.shape[2]}")


def _validate_flux3(h: Handler, lat: torch.Tensor, img: torch.Tensor | None) -> None:
    if lat.dim() != 4 or lat.shape[0] != 1 or lat.shape[1] != 128 or lat.shape[2] < 1 or lat.shape[3] < 1:
        raise RefModError(f"Flux 3 refmod: latent must be [1, 128, h, w], got {list(lat.shape)}")


def attach(cond: Cond, lats: list[torch.Tensor]) -> Cond:
    nh = _comfy.optional_module("node_helpers")
    if nh is not None and hasattr(nh, "conditioning_set_values"):
        return nh.conditioning_set_values(cond, {"reference_latents": lats}, append=True)
    out: Cond = []
    for t in cond:
        d = dict(t[1])  # type: ignore[arg-type]
        d["reference_latents"] = list(d.get("reference_latents") or []) + list(lats)
        out.append([t[0], d])
    return out


def _set_values(cond: Cond, values: dict[str, float]) -> Cond:
    nh = _comfy.optional_module("node_helpers")
    if nh is not None and hasattr(nh, "conditioning_set_values"):
        return nh.conditioning_set_values(cond, values)
    return [[t[0], {**t[1], **values}] for t in cond]  # type: ignore[dict-item]


def schedule(with_refs: Cond, without: Cond, s: float) -> Cond:
    """``ref_strength`` is "how long": refs for the first ``s`` of the steps."""
    if s >= 1.0:
        return with_refs
    if s <= 0.0:
        return without
    return _set_values(with_refs, {"start_percent": 0.0, "end_percent": s}) + \
        _set_values(without, {"start_percent": s, "end_percent": 1.0})


def _require_clip(ctx: ApplyContext, label: str) -> object:
    if ctx.clip is None:
        raise RefModError(f"{label} RefMod Apply needs a CLIP (connect the model's text encoder)")
    return ctx.clip


def _build_qwen(h: Handler, ctx: ApplyContext, lats: list[torch.Tensor], imgs: list[torch.Tensor]) -> tuple[Cond, Cond]:
    clip = _require_clip(ctx, h.label)

    def enc(text: str, images: list[torch.Tensor], keep_vision: bool) -> Cond:
        tokens = clip.tokenize(text, images=images, keep_vision=keep_vision, prevent_empty_text=True)  # type: ignore[attr-defined]
        return clip.encode_from_tokens_scheduled(tokens)  # type: ignore[attr-defined]

    keep = not lats
    pos = enc(ctx.prompt, imgs, keep)
    neg = enc(ctx.negative_prompt, imgs, keep)
    if lats:
        pos_r = attach(pos, lats)
        pos = schedule(pos_r, enc(ctx.prompt, [], True), ctx.ref_strength) if ctx.ref_strength < 1 else pos_r
        if ctx.ref_on_negative:
            neg_r = attach(neg, lats)
            neg = schedule(neg_r, enc(ctx.negative_prompt, [], True), ctx.ref_strength) if ctx.ref_strength < 1 else neg_r
    return pos, neg


def _build_fibo(h: Handler, ctx: ApplyContext, lats: list[torch.Tensor], imgs: list[torch.Tensor]) -> tuple[Cond, Cond]:
    clip = _require_clip(ctx, h.label)

    def enc(text: str, images: list[torch.Tensor]) -> Cond:
        return clip.encode_from_tokens_scheduled(clip.tokenize(text, images=images))  # type: ignore[attr-defined]

    pos = enc(ctx.prompt, imgs)
    neg = enc(ctx.negative_prompt, [])
    if lats:
        pos_r = attach(pos, lats)
        pos = schedule(pos_r, enc(ctx.prompt, []), ctx.ref_strength) if ctx.ref_strength < 1 else pos_r
        if ctx.ref_on_negative:
            neg = schedule(attach(neg, lats), neg, ctx.ref_strength)
    return pos, neg


def _build_flux3(h: Handler, ctx: ApplyContext, lats: list[torch.Tensor], imgs: list[torch.Tensor]) -> tuple[Cond, Cond]:
    if ctx.positive is None:
        raise RefModError("Flux 3 RefMod Apply needs the positive conditioning connected")
    pos = schedule(attach(ctx.positive, lats), ctx.positive, ctx.ref_strength) if lats else ctx.positive
    if ctx.negative is not None:
        neg = schedule(attach(ctx.negative, lats), ctx.negative, ctx.ref_strength) \
            if lats and ctx.ref_on_negative else ctx.negative
    else:
        neg = pos
    return pos, neg


_STD_USES = frozenset({"ref_strength", "ref_on_negative"})

HANDLERS: dict[str, Handler] = {}


def register_handler(h: Handler) -> None:
    HANDLERS[h.key] = h


register_handler(Handler("qwen21", "Qwen 2.1", "jezzwtf_qwen21_refmod", "jezzwtf_qwen21", "qwen21", 16, 64, True,
                         "#22d3ee", ("clip",), _STD_USES | {"clip"}, _enc_qwen, _extras_sizes,
                         _validate_with_image, _build_qwen))
register_handler(Handler("fibo2", "Fibo 2", "jezzwtf_fibo2_refmod", "jezzwtf_fibo2", "fibo2", 8, 128, True,
                         "#f472b6", ("clip",), _STD_USES | {"clip"}, _enc_fibo, _extras_sizes,
                         _validate_with_image, _build_fibo))
register_handler(Handler("flux3", "Flux 3", "jezzwtf_flux3_refmod", "jezzwtf_flux3", "flux3", 16, 128, False,
                         "#fbbf24", ("positive",), _STD_USES | {"positive"}, _enc_flux3, _extras_flux3,
                         _validate_flux3, _build_flux3))


# --------------------------------------------------------------------------- file format

def thumb_b64(frame: torch.Tensor) -> str:
    arr = (frame[0, ..., :3].clamp(0, 1).cpu().numpy() * 255.0).round().astype(np.uint8)
    im = Image.fromarray(arr)
    im.thumbnail((THUMB_EDGE, THUMB_EDGE))
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def build_file(h: Handler, name: str, encs: list[Encoded], resolution: int, first_frame: torch.Tensor
               ) -> tuple[dict[str, torch.Tensor], dict[str, str]]:
    tensors: dict[str, torch.Tensor] = {}
    for i, e in enumerate(encs):
        tensors[f"lat_{i}"] = e.lat.detach().to("cpu", torch.float32).contiguous()
        if h.stores_images and e.img is not None:
            tensors[f"img_{i}"] = (e.img.clamp(0, 1) * 255.0).round().to(torch.uint8).cpu().contiguous()
    meta: JSONDict = {"format": h.format, "version": 1, "name": name, "count": len(encs)}
    meta.update(h.extras(h, encs, resolution))
    try:
        meta["thumb"] = thumb_b64(rgb_over_white(_as_frame(first_frame)))
    except Exception as exc:
        log.warning("refmod: thumbnail failed: %s", exc)
    return tensors, {h.meta_key: json.dumps(meta)}


def detect(path: str) -> tuple[Handler, JSONDict] | None:
    try:
        meta = read_metadata(path)
    except Exception:
        return None
    for h in HANDLERS.values():
        raw = meta.get(h.meta_key)
        if raw is None:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and parsed.get("format") == h.format:
            return h, parsed
    return None


def load_refs(path: str) -> tuple[Handler, list[torch.Tensor], list[torch.Tensor]]:
    found = detect(path)
    if found is None:
        raise RefModError(f"{os.path.basename(path)} is not a Qwen/Fibo/Flux RefMod")
    h, meta = found
    count = int(meta.get("count", 0) or 0)  # type: ignore[arg-type]
    lats: list[torch.Tensor] = []
    imgs: list[torch.Tensor] = []
    with safe_open(path, framework="pt", device="cpu") as fh:
        keys = set(fh.keys())
        for i in range(count):
            if f"lat_{i}" not in keys:
                raise RefModError(f"{os.path.basename(path)}: missing lat_{i}")
            lat = fh.get_tensor(f"lat_{i}").float()
            img = fh.get_tensor(f"img_{i}").float() / 255.0 if f"img_{i}" in keys else None
            h.validate(h, lat, img)
            lats.append(lat)
            if img is not None:
                imgs.append(img)
    return h, lats, imgs


# --------------------------------------------------------------------------- index

_INDEX_LOCK = threading.Lock()
_DETECT_CACHE: dict[str, tuple[int, tuple[Handler, JSONDict] | None]] = {}


def _detect_cached(path: str) -> tuple[Handler, JSONDict] | None:
    try:
        mt = os.stat(path).st_mtime_ns
    except OSError:
        return None
    with _INDEX_LOCK:
        hit = _DETECT_CACHE.get(path)
        if hit is not None and hit[0] == mt:
            return hit[1]
    res = detect(path)
    with _INDEX_LOCK:
        _DETECT_CACHE[path] = (mt, res)
    return res


def invalidate(path: str) -> None:
    with _INDEX_LOCK:
        _DETECT_CACHE.pop(path, None)
        _THUMB_CACHE.pop(path, None)


def index() -> dict[str, tuple[str, Handler, JSONDict]]:
    """name -> (path, handler, metadata) for every detected image-model RefMod."""
    return index_with_errors()[0]


def index_with_errors() -> tuple[dict[str, tuple[str, Handler, JSONDict]], list[str]]:
    """``index()`` plus one message per file that failed; a bad file never hides the others."""
    out: dict[str, tuple[str, Handler, JSONDict]] = {}
    errors: list[str] = []
    for root in search_dirs():
        for d, dirnames, files in os.walk(root):
            dirnames[:] = sorted(x for x in dirnames if x not in RESERVED_DIRS)
            for f in sorted(files):
                if not f.endswith(".safetensors"):
                    continue
                p = os.path.join(d, f)
                name = os.path.relpath(p, root).replace("\\", "/")[: -len(".safetensors")]
                if name in out:
                    continue
                try:
                    res = _detect_cached(p)
                except Exception as exc:
                    log.warning("unified refmod: skipped %s (%s)", name, exc)
                    errors.append(f"{name}: {exc}")
                    continue
                if res is not None:
                    out[name] = (p, res[0], res[1])
    return out, errors


def choices() -> list[str]:
    try:
        return [NONE] + sorted(index(), key=str.casefold)
    except Exception as exc:  # pragma: no cover
        log.warning("unified refmod index failed: %s", exc)
        return [NONE]


def entry_sizes(h: Handler, meta: JSONDict) -> list[list[int]]:
    for key in ("sizes", "ref_sizes"):
        v = meta.get(key)
        if isinstance(v, list):
            return [[int(s[0]), int(s[1])] for s in v if isinstance(s, list) and len(s) >= 2]  # type: ignore[arg-type]
    shapes = meta.get("shapes")
    if isinstance(shapes, list):
        return [[int(s[-1]) * 16, int(s[-2]) * 16] for s in shapes if isinstance(s, list) and len(s) >= 2]  # type: ignore[arg-type]
    return []


def library_payload() -> JSONDict:
    try:
        found, errors = index_with_errors()
    except Exception as exc:
        return {"models": [], "refmods": [], "error": str(exc)}
    refmods: list[JSONDict] = []
    for name, (path, h, meta) in sorted(found.items(), key=lambda kv: kv[0].casefold()):
        try:
            sizes = entry_sizes(h, meta)
            refmods.append({
                "name": name, "model": h.key, "count": int(meta.get("count", 0) or 0),  # type: ignore[arg-type]
                "sizes": sizes, "tokens": sum((w // 16) * (hh // 16) for w, hh in sizes),
                "stamp": int(os.path.getmtime(path)), "thumb": bool(meta.get("thumb")) or h.stores_images,
            })
        except Exception as exc:  # malformed metadata, or the file vanished since it was listed
            log.warning("unified refmod: skipped %s (%s)", name, exc)
            errors.append(f"{name}: {exc}")
    payload: JSONDict = {"models": [h.ui() for h in HANDLERS.values()], "refmods": refmods}
    if errors:
        payload["errors"] = errors
    return payload


_THUMB_CACHE: dict[str, tuple[int, bytes]] = {}


def thumb_bytes(name: str) -> bytes | None:
    try:
        check_rel(name)
    except RefModError:
        return None
    entry = index().get(name)
    if entry is None:
        return None
    path, h, meta = entry
    mt = os.stat(path).st_mtime_ns
    hit = _THUMB_CACHE.get(path)
    if hit is not None and hit[0] == mt:
        return hit[1]
    data: bytes | None = None
    raw = meta.get("thumb")
    if isinstance(raw, str) and raw:
        try:
            data = base64.b64decode(raw)
        except ValueError:
            data = None
    if data is None and h.stores_images:
        with safe_open(path, framework="pt", device="cpu") as fh:
            if "img_0" in fh.keys():
                arr = fh.get_tensor("img_0")[0].numpy()
                im = Image.fromarray(arr)
                im.thumbnail((THUMB_EDGE, THUMB_EDGE))
                buf = BytesIO()
                im.save(buf, format="JPEG", quality=82)
                data = buf.getvalue()
    if data is not None:
        _THUMB_CACHE[path] = (mt, data)
    return data


# --------------------------------------------------------------------------- nodes

_NAME_BAD = re.compile(r"[^\w\- .]")


def sanitise_file_name(name: str) -> str:
    s = _NAME_BAD.sub("_", str(name or "")).strip(" .")
    if not s:
        raise RefModError("name is empty")
    return s


def unified_output_path(name: str, subfolder: str, h: Handler) -> str:
    root = save_root()
    sub = str(subfolder or "").strip() or h.subfolder
    parts = check_rel(sub, allow_dot=False)
    path = os.path.join(root, *parts, sanitise_file_name(name) + ".safetensors")
    if not is_inside(path, root):
        raise RefModError(f"save path escapes {root}")
    return path


def _frames_of(*images: torch.Tensor | None) -> list[torch.Tensor]:
    out: list[torch.Tensor] = []
    for im in images:
        if isinstance(im, torch.Tensor) and im.numel():
            batch = im if im.dim() == 4 else im.unsqueeze(0)
            out.extend(batch[i:i + 1] for i in range(batch.shape[0]))
    return out


class JWTFUnifiedRefModBake(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFUnifiedRefModBake",
            display_name='Image RefMod Bake',
            category='JezzWTF/refmod',
            inputs=[
                io.Combo.Input("model", options=list(HANDLERS), default='qwen21'),
                io.Image.Input("images"),
                io.String.Input("name", default='my_character'),
                io.Int.Input("resolution", default=1024, min=0, max=4096, step=16),
                io.String.Input("subfolder", default=''),
                io.Boolean.Input("overwrite", default=False),
                io.Vae.Input("vae", optional=True),
                io.Image.Input("image_2", optional=True),
                io.Image.Input("image_3", optional=True),
                io.Image.Input("image_4", optional=True),
            ],
            outputs=[
                io.String.Output("path"),
            ],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, model: str, images: torch.Tensor, name: str, resolution: int, subfolder: str, overwrite: bool,
             vae: object | None = None, image_2: torch.Tensor | None = None, image_3: torch.Tensor | None = None,
             image_4: torch.Tensor | None = None, **_: object) -> io.NodeOutput:
        h = HANDLERS.get(model)
        if h is None:
            raise RefModError(f"unknown model {model!r}")
        frames = _frames_of(images, image_2, image_3, image_4)
        if not frames:
            raise RefModError("no reference images")
        if len(frames) > h.max_refs:
            raise RefModError(f"{h.label} takes at most {h.max_refs} references, got {len(frames)}")
        if vae is None:
            raise RefModError("connect the model's VAE")
        dest = unified_output_path(name, subfolder, h)
        if os.path.exists(dest) and not overwrite:
            return io.NodeOutput(dest, ui={"text": [f"{dest} already exists, skipped (enable overwrite to re-bake)"]})
        encs = [h.encode(h, vae, f.float(), int(resolution)) for f in frames]
        tensors, meta = build_file(h, os.path.splitext(os.path.basename(dest))[0], encs, int(resolution), frames[0])
        _atomic_save(tensors, meta, dest)
        invalidate(dest)
        sizes = ", ".join(f"{e.size[0]}x{e.size[1]}" for e in encs)
        return io.NodeOutput(dest, ui={"text": [f"{h.label}: {len(encs)} ref(s) [{sizes}] -> {dest}"]})


class JWTFUnifiedRefModApply(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFUnifiedRefModApply",
            display_name='Image RefMod Apply',
            category='JezzWTF/refmod',
            description="Apply saved RefMods to Qwen, Fibo or Flux image-edit conditioning, with the model detected from the RefMod or chosen by hand.",
            inputs=[
                io.Combo.Input("model", options=[AUTO] + list(HANDLERS), default='auto (from refmod)'),
                io.Combo.Input("refmod_1", options=choices(), default='None'),
                io.Clip.Input("clip", optional=True),
                io.String.Input("prompt", default='', multiline=True, dynamic_prompts=True, optional=True),
                io.String.Input("negative_prompt", default='', multiline=True, dynamic_prompts=True, optional=True),
                io.Conditioning.Input("positive", optional=True),
                io.Conditioning.Input("negative", optional=True),
                io.Combo.Input("refmod_2", options=choices(), default='None', optional=True),
                io.Combo.Input("refmod_3", options=choices(), default='None', optional=True),
                io.Image.Input("extra_image", optional=True),
                io.Vae.Input("vae", optional=True),
                io.Int.Input("extra_image_resolution", default=1024, min=0, max=4096, step=16, optional=True),
                io.Combo.Input("extra_image_scale", options=list(EXTRA_SCALE_LABELS), default='keep aspect (resolution)', optional=True),
                io.Float.Input("ref_strength", default=1.0, min=0.0, max=1.0, step=0.01, optional=True),
                io.Boolean.Input("ref_on_negative", default=True, optional=True),
            ],
            outputs=[
                io.Conditioning.Output("positive"),
                io.Conditioning.Output("negative"),
                io.Latent.Output("latent"),
            ],
        )

    @classmethod
    def validate_inputs(cls, **_: object) -> bool:
        return True

    @classmethod
    def fingerprint_inputs(cls, refmod_1: str = NONE, refmod_2: str = NONE, refmod_3: str = NONE, **_: object) -> str:
        idx = index()
        parts: list[str] = []
        for n in (refmod_1, refmod_2, refmod_3):
            if not n or n == NONE:
                continue
            e = idx.get(n)
            parts.append(str(os.path.getmtime(e[0])) if e else "missing")
        return "|".join(parts)

    @classmethod
    def execute(cls, model: str, refmod_1: str, clip: object | None = None, prompt: str = "",
                negative_prompt: str = "", positive: Cond | None = None, negative: Cond | None = None,
              refmod_2: str = NONE, refmod_3: str = NONE, extra_image: torch.Tensor | None = None,
              vae: object | None = None, extra_image_resolution: int = 1024, extra_image_scale: str = "",
              ref_strength: float = 1.0, ref_on_negative: bool = True) -> io.NodeOutput:
        h = HANDLERS.get(model) if model != AUTO else None
        if model != AUTO and h is None:
            raise RefModError(f"unknown model {model!r}")
        explicit = h is not None
        idx = index()
        lats: list[torch.Tensor] = []
        imgs: list[torch.Tensor] = []
        for n in (refmod_1, refmod_2, refmod_3):
            if not n or n == NONE:
                continue
            entry = idx.get(n)
            if entry is None:
                raise RefModError(f"RefMod {n!r} not found or not a Qwen/Fibo/Flux RefMod")
            fh, fl, fi = load_refs(entry[0])
            if h is None:
                h = fh
            elif fh.key != h.key:
                if explicit:
                    raise RefModError(f"{n} is a {fh.label} RefMod but the model is set to {h.label}")
                raise RefModError(f"mixed models: {n} is {fh.label}, earlier refmods are {h.label}")
            lats.extend(fl)
            imgs.extend(fi)
        if h is None:
            raise RefModError("choose a model or at least one refmod")
        if isinstance(extra_image, torch.Tensor) and extra_image.numel():
            if vae is None:
                raise RefModError("extra_image needs the vae connected")
            for f in _frames_of(extra_image):
                e = h.encode(h, vae, f.float(), int(extra_image_resolution))
                lats.append(e.lat)
                if e.img is not None:
                    imgs.append(e.img)
        if len(lats) > h.max_refs:
            raise RefModError(f"{h.label} takes at most {h.max_refs} references, got {len(lats)}")
        device = _comfy.intermediate_device()
        lats = [lat.to(device) for lat in lats]
        ctx = ApplyContext(clip=clip, prompt=prompt or "", negative_prompt=negative_prompt or "",
                           positive=positive, negative=negative, ref_strength=float(ref_strength),
                           ref_on_negative=bool(ref_on_negative))
        pos, neg = h.build(h, ctx, lats, imgs)
        empty = torch.zeros_like(lats[0]) if lats else torch.zeros([1, h.latent_channels, 64, 64], device=device)
        return io.NodeOutput(pos, neg, {"samples": empty})


NODES = [JWTFUnifiedRefModBake, JWTFUnifiedRefModApply]
