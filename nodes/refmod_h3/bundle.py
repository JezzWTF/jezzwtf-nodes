"""RefMod file formats: bundle v5 (current) and the legacy standalone mod.

Pure logic (torch + safetensors only). The on-disk layout is an interface fact shared
with the upstream ComfyUI-MiniMaxH3Mod engine and must stay byte-compatible:

- ``__metadata__["refmod_meta"]`` = JSON ``{"_format_version": 5, "kind": "bundle",
  "name": ..., "members": [...]}`` with 1-256 members;
- tensors ``ref_0``, ``ref_1``, ... (one per member, same order).
"""
from __future__ import annotations

import json
import math
import os
import struct
import tempfile
from dataclasses import dataclass, field

import torch
from safetensors import safe_open
from safetensors.torch import save_file

from ._types import JSONDict, JSONValue, RefModError

FORMAT_VERSION = 5
MEMBER_FORMAT_VERSION = 4
META_KEY = "refmod_meta"
AUDIO_META_KEY = "audio_refmod_meta"
MAX_MEMBERS = 256
VISUAL_CHANNELS = 24
AUDIO_CHANNELS = 32
AUDIO_SAMPLE_RATE = 32000
AUDIO_FRAMES_PER_SECOND = 40
AUDIO_SAMPLES_PER_FRAME = AUDIO_SAMPLE_RATE // AUDIO_FRAMES_PER_SECOND  # 800
VISUAL_KINDS = ("image", "video")
MEMBER_KINDS = ("image", "video", "audio")
HEADER_MAX_BYTES = 100 * 1024 * 1024

_KNOWN_MEMBER_KEYS = {
    "name", "kind", "latent_h", "latent_w", "latent_t", "mode", "source", "source_shape", "pool",
    "optimize_steps", "tags", "description", "concept_type", "_format_version", "sample_rate",
    "refmod_config",
}


@dataclass
class RefMod:
    """One extracted reference (visual or audio) and its member metadata."""

    name: str
    kind: str
    latent: torch.Tensor
    mode: str = "encode"
    source: str = ""
    source_shape: str = ""
    pool: str = ""
    optimize_steps: int = 0
    tags: list[str] = field(default_factory=list)
    description: str = ""
    concept_type: str = "identity"
    sample_rate: int | None = None
    refmod_config: str | None = None
    path: str | None = None
    bundle_index: int | None = None
    extra: JSONDict = field(default_factory=dict)

    @property
    def is_visual(self) -> bool:
        return self.kind in VISUAL_KINDS

    @property
    def latent_t(self) -> int:
        return int(self.latent.shape[2] if self.is_visual else self.latent.shape[-1])

    @property
    def latent_h(self) -> int:
        return int(self.latent.shape[3]) if self.is_visual else 0

    @property
    def latent_w(self) -> int:
        return int(self.latent.shape[4]) if self.is_visual else 0

    @property
    def token_count(self) -> int:
        return token_count(self.kind, self.latent)

    @property
    def seconds(self) -> float:
        return self.latent_t / AUDIO_FRAMES_PER_SECOND if self.kind == "audio" else 0.0

    def member_meta(self) -> JSONDict:
        meta: JSONDict = dict(self.extra)
        meta.update({
            "name": self.name,
            "kind": self.kind,
            "latent_h": self.latent_h,
            "latent_w": self.latent_w,
            "latent_t": self.latent_t,
            "mode": self.mode,
            "source": self.source,
            "source_shape": self.source_shape,
            "pool": self.pool,
            "optimize_steps": int(self.optimize_steps),
            "tags": list(self.tags),
            "description": self.description,
            "concept_type": self.concept_type,
            "_format_version": MEMBER_FORMAT_VERSION,
        })
        if self.kind == "audio":
            meta["sample_rate"] = int(self.sample_rate or AUDIO_SAMPLE_RATE)
        if self.refmod_config:
            meta["refmod_config"] = self.refmod_config
        return meta


# --------------------------------------------------------------------------- validation

LATENT_DTYPES = (torch.float16, torch.bfloat16, torch.float32)


def token_count(kind: str, latent: torch.Tensor) -> int:
    """Visual: ``T·(H//2)·(W//2)``; audio: ``2·T``."""
    if kind in VISUAL_KINDS:
        _, _, t, h, w = latent.shape
        return int(t) * (int(h) // 2) * (int(w) // 2)
    return 2 * int(latent.shape[-1])


def validate_latent(kind: str, latent: torch.Tensor, label: str = "refmod") -> None:
    if not isinstance(latent, torch.Tensor):
        raise RefModError(f"{label}: latent is not a tensor")
    if latent.dtype not in LATENT_DTYPES:
        raise RefModError(f"{label}: latent dtype must be float16, bfloat16 or float32, got {latent.dtype}")
    shape = tuple(int(s) for s in latent.shape)
    if kind in VISUAL_KINDS:
        if len(shape) != 5 or shape[0] != 1 or shape[1] != VISUAL_CHANNELS:
            raise RefModError(f"{label}: visual latent must be [1, {VISUAL_CHANNELS}, T, H, W], got {list(shape)}")
        _, _, t, h, w = shape
        if t <= 0 or h <= 0 or w <= 0:
            raise RefModError(f"{label}: visual latent has an empty dimension {list(shape)}")
        if h % 2 or w % 2:
            raise RefModError(f"{label}: visual latent H and W must be even, got {h}x{w}")
        if kind == "image" and t != 1:
            raise RefModError(f"{label}: image latent must have T == 1, got T={t}")
    elif kind == "audio":
        if len(shape) != 4 or shape[0] != 1 or shape[1] != AUDIO_CHANNELS or shape[2] != 2:
            raise RefModError(f"{label}: audio latent must be [1, {AUDIO_CHANNELS}, 2, T], got {list(shape)}")
        if shape[3] <= 0:
            raise RefModError(f"{label}: audio latent has T == 0")
    else:
        raise RefModError(f"{label}: unknown kind {kind!r}")
    if not torch.isfinite(latent.float()).all():
        raise RefModError(f"{label}: latent contains NaN or Inf")


# --------------------------------------------------------------------------- header

def read_header(path: str) -> tuple[dict[str, JSONValue], int]:
    """Read a safetensors header without loading tensors. Returns (header, data_offset)."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(8)
            if len(raw) != 8:
                raise RefModError(f"{os.path.basename(path)}: not a safetensors file (too short)")
            (n,) = struct.unpack("<Q", raw)
            if n < 2 or n > HEADER_MAX_BYTES:
                raise RefModError(f"{os.path.basename(path)}: implausible safetensors header length {n}")
            blob = fh.read(n)
    except OSError as exc:
        raise RefModError(f"cannot read {path}: {exc}") from exc
    if len(blob) != n:
        raise RefModError(f"{os.path.basename(path)}: truncated safetensors header")
    try:
        header = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RefModError(f"{os.path.basename(path)}: corrupt safetensors header ({exc})") from exc
    if not isinstance(header, dict):
        raise RefModError(f"{os.path.basename(path)}: safetensors header is not an object")
    return header, 8 + n


def read_metadata(path: str) -> dict[str, str]:
    header, _ = read_header(path)
    meta = header.get("__metadata__")
    if not isinstance(meta, dict):
        return {}
    return {str(k): str(v) for k, v in meta.items()}


def _parse_json_dict(text: str | None, label: str) -> JSONDict | None:
    if text is None:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RefModError(f"{label}: metadata is not valid JSON ({exc})") from exc
    if not isinstance(value, dict):
        raise RefModError(f"{label}: metadata is not a JSON object")
    return value


@dataclass
class RefModInfo:
    """Parsed metadata of a RefMod file (bundle or standalone), no tensors loaded."""

    path: str
    kind: str  # "bundle" or a member kind
    name: str
    members: list[JSONDict]

    @property
    def is_bundle(self) -> bool:
        return self.kind == "bundle"


def sidecar_json_path(path: str) -> str:
    return os.path.splitext(path)[0] + ".json"


def inspect_file(path: str) -> RefModInfo:
    """Parse a RefMod file's metadata; raises RefModError if it is not a valid RefMod."""
    label = os.path.basename(path)
    header, _ = read_header(path)
    meta_raw = header.get("__metadata__")
    meta = {str(k): str(v) for k, v in meta_raw.items()} if isinstance(meta_raw, dict) else {}
    parsed = _parse_json_dict(meta.get(META_KEY), label)
    if parsed is None:
        parsed = _parse_json_dict(meta.get(AUDIO_META_KEY), label)
    if parsed is None:
        side = sidecar_json_path(path)
        if os.path.isfile(side):
            with open(side, "r", encoding="utf-8") as fh:
                parsed = _parse_json_dict(fh.read(), os.path.basename(side))
    if parsed is None:
        raise RefModError(f"{label}: no refmod metadata")
    kind = str(parsed.get("kind", ""))
    tensors = {k: v for k, v in header.items() if k != "__metadata__"}
    if kind == "bundle":
        members = parsed.get("members")
        if not isinstance(members, list) or not (1 <= len(members) <= MAX_MEMBERS):
            raise RefModError(f"{label}: bundle must have 1-{MAX_MEMBERS} members")
        out: list[JSONDict] = []
        for i, m in enumerate(members):
            if not isinstance(m, dict):
                raise RefModError(f"{label}: member {i} is not an object")
            if str(m.get("kind", "")) not in MEMBER_KINDS:
                raise RefModError(f"{label}: member {i} has invalid kind {m.get('kind')!r}")
            if f"ref_{i}" not in tensors:
                raise RefModError(f"{label}: missing tensor ref_{i}")
            out.append(m)
        version = parsed.get("_format_version")
        if not isinstance(version, int) or version < 5:
            raise RefModError(f"{label}: unsupported bundle format version {version!r}")
        return RefModInfo(path=path, kind="bundle", name=str(parsed.get("name", "")), members=out)
    if kind not in MEMBER_KINDS:
        raise RefModError(f"{label}: invalid refmod kind {kind!r}")
    if "latent" not in tensors:
        raise RefModError(f"{label}: standalone mod has no 'latent' tensor")
    return RefModInfo(path=path, kind=kind, name=str(parsed.get("name", "")), members=[parsed])


def tensor_shape_from_header(path: str, key: str) -> list[int]:
    header, _ = read_header(path)
    entry = header.get(key)
    if not isinstance(entry, dict) or not isinstance(entry.get("shape"), list):
        raise RefModError(f"{os.path.basename(path)}: tensor {key} missing")
    return [int(s) for s in entry["shape"]]  # type: ignore[union-attr]


# --------------------------------------------------------------------------- build / load

def _str_list(value: JSONValue) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str) and value:
        return [value]
    return []


def mod_from_member(meta: JSONDict, latent: torch.Tensor, path: str | None = None,
                    bundle_index: int | None = None) -> RefMod:
    kind = str(meta.get("kind", ""))
    label = f"{os.path.basename(path) if path else 'refmod'}:{meta.get('name', bundle_index)}"
    validate_latent(kind, latent, label)
    sr = meta.get("sample_rate")
    opt = meta.get("optimize_steps", 0)
    cfg = meta.get("refmod_config")
    try:
        return _build_mod(meta, kind, latent, sr, opt, cfg, path, bundle_index)
    except (OverflowError, ValueError, TypeError) as exc:
        raise RefModError(f"{label}: invalid numeric metadata ({exc})") from exc


def _build_mod(meta: JSONDict, kind: str, latent: torch.Tensor, sr: JSONValue, opt: JSONValue, cfg: JSONValue,
               path: str | None, bundle_index: int | None) -> RefMod:
    return RefMod(
        name=str(meta.get("name", "")),
        kind=kind,
        latent=latent.contiguous(),
        mode=str(meta.get("mode", "encode")),
        source=str(meta.get("source", "")),
        source_shape=str(meta.get("source_shape", "")),
        pool=str(meta.get("pool", "")),
        optimize_steps=int(opt) if isinstance(opt, (int, float)) else 0,
        tags=_str_list(meta.get("tags")),
        description=str(meta.get("description", "") or ""),
        concept_type=str(meta.get("concept_type", "identity") or "identity"),
        sample_rate=int(sr) if isinstance(sr, (int, float)) else (AUDIO_SAMPLE_RATE if kind == "audio" else None),
        refmod_config=str(cfg) if isinstance(cfg, str) and cfg else None,
        path=path,
        bundle_index=bundle_index,
        extra={k: v for k, v in meta.items() if k not in _KNOWN_MEMBER_KEYS},
    )


def load_refmod_file(path: str, select: list[int] | None = None) -> list[RefMod]:
    """Load a bundle (optionally only the member indices in ``select``) or a standalone mod."""
    info = inspect_file(path)
    out: list[RefMod] = []
    with safe_open(path, framework="pt", device="cpu") as fh:
        if info.is_bundle:
            indices = range(len(info.members)) if select is None else select
            for i in indices:
                if i < 0 or i >= len(info.members):
                    raise RefModError(f"{os.path.basename(path)}: member index {i} out of range")
                out.append(mod_from_member(info.members[i], fh.get_tensor(f"ref_{i}"), path, i))
        else:
            out.append(mod_from_member(info.members[0], fh.get_tensor("latent"), path, None))
    return out


def dedupe_mods(mods: list[RefMod]) -> list[RefMod]:
    seen: set[int] = set()
    out: list[RefMod] = []
    for m in mods:
        if id(m) in seen:
            continue
        seen.add(id(m))
        out.append(m)
    return out


def _atomic_save(tensors: dict[str, torch.Tensor], metadata: dict[str, str], dest: str) -> None:
    folder = os.path.dirname(os.path.abspath(dest)) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".refmod-", suffix=".tmp", dir=folder)
    os.close(fd)
    try:
        save_file(tensors, tmp, metadata=metadata)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def bundle_metadata(name: str, mods: list[RefMod]) -> dict[str, str]:
    payload = {
        "_format_version": FORMAT_VERSION,
        "kind": "bundle",
        "name": name,
        "members": [m.member_meta() for m in mods],
    }
    return {META_KEY: json.dumps(payload)}


def write_bundle(dest: str, name: str, mods: list[RefMod]) -> str:
    """Write a bundle v5 file atomically. Mods are de-duplicated by identity."""
    unique = dedupe_mods(mods)
    if not unique:
        raise RefModError("bundle needs at least one member")
    if len(unique) > MAX_MEMBERS:
        raise RefModError(f"bundle can hold at most {MAX_MEMBERS} members, got {len(unique)}")
    tensors: dict[str, torch.Tensor] = {}
    for i, m in enumerate(unique):
        validate_latent(m.kind, m.latent, f"{name}:{m.name}")
        tensors[f"ref_{i}"] = m.latent.detach().to("cpu").contiguous()
    _atomic_save(tensors, bundle_metadata(name, unique), dest)
    return dest


def write_standalone(dest: str, mod: RefMod) -> str:
    """Write a legacy single-tensor mod (kept for round-trip tests and tooling)."""
    validate_latent(mod.kind, mod.latent, mod.name)
    key = AUDIO_META_KEY if mod.kind == "audio" else META_KEY
    _atomic_save({"latent": mod.latent.detach().to("cpu").contiguous()},
                 {key: json.dumps(mod.member_meta())}, dest)
    return dest


def update_bundle_member(path: str, index: int, expected_name: str,
                         meta_patch: JSONDict, latent: torch.Tensor | None = None) -> None:
    """Rewrite one member in place (verifying its name), keeping every other tensor and key."""
    with safe_open(path, framework="pt", device="cpu") as fh:
        header_meta = dict(fh.metadata() or {})
        tensors = {k: fh.get_tensor(k) for k in fh.keys()}
    parsed = _parse_json_dict(header_meta.get(META_KEY), os.path.basename(path))
    if parsed is None or parsed.get("kind") != "bundle":
        raise RefModError(f"{os.path.basename(path)}: not a bundle")
    members = parsed.get("members")
    if not isinstance(members, list) or index < 0 or index >= len(members):
        raise RefModError(f"{os.path.basename(path)}: member index {index} out of range")
    member = members[index]
    if not isinstance(member, dict) or member.get("name") != expected_name:
        raise RefModError(f"{os.path.basename(path)}: member {index} is no longer {expected_name!r}")
    member.update(meta_patch)
    if latent is not None:
        validate_latent(str(member.get("kind")), latent, expected_name)
        tensors[f"ref_{index}"] = latent.detach().to("cpu").contiguous()
    header_meta[META_KEY] = json.dumps(parsed)
    _atomic_save(tensors, header_meta, path)


def finite_unit(value: float, label: str) -> float:
    v = float(value)
    if not math.isfinite(v) or v < 0.0 or v > 1.0:
        raise RefModError(f"{label} must be a finite number in [0, 1], got {value!r}")
    return v
