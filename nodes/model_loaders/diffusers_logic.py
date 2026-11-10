"""Pure logic for the Diffusers loader: model-root discovery, the folder/file scan and
component file lookup. No ComfyUI imports."""
from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import TypeVar

MODEL_EXT = (".safetensors", ".bin", ".gguf", ".ckpt", ".pt")
# Weight families, in preference order. Within a family a plain file beats its fp16 variant, and
# safetensors beats .bin; the fp16 variant is only used when nothing else exists.
DIFFUSION_FAMILIES = ("diffusion_pytorch_model",)
TEXT_ENCODER_FAMILIES = ("model", "pytorch_model")
WEIGHT_EXTS = (".safetensors", ".bin")
WEIGHT_VARIANTS = ("", ".fp16")
# Flux / SD3 / Qwen-Image / Wan / LTX ship `transformer/`; SD1/SDXL ship `unet/`.
DIFFUSION_SUBDIRS = ("transformer", "unet")
TEXT_ENCODER_DIRS = ("text_encoder", "text_encoder_2", "text_encoder_3")
SUBDIRS = ("diffusion_models", "unet", "diffusers")

T = TypeVar("T")

SAGE_CHOICES = ["None", "SageAttention 2", "SageAttention 3"]
FLASH_CHOICES = ["None", "FlashAttention 2", "FlashAttention 3", "FlashAttention 4"]
# ComfyUI registers a single "flash" backend; Sage 2 and 3 are separate registry entries.
BACKEND_NAMES = {
    "SageAttention 2": ("sage", "sage2", "sageattn"),
    "SageAttention 3": ("sage3", "sageattn3"),
    "FlashAttention 2": ("flash", "flash2", "flash_attention"),
    "FlashAttention 3": ("flash3", "flash"),
    "FlashAttention 4": ("flash4", "flash"),
}


def collect_roots(registered: Iterable[str], bases: Iterable[str]) -> list[str]:
    cands = list(registered)
    for b in bases:
        cands.extend(os.path.join(b, s) for s in SUBDIRS)
    out: list[str] = []
    seen: set[str] = set()
    for c in cands:
        n = os.path.normcase(os.path.abspath(c))
        if n in seen or not os.path.isdir(c):
            continue
        seen.add(n)
        out.append(os.path.abspath(c))
    return out


def is_diffusers_dir(path: str) -> bool:
    try:
        entries = os.listdir(path)
    except OSError:
        return False
    for e in entries:
        low = e.lower()
        if low in ("unet", "transformer") or low == "model_index.json" or low.startswith("diffusion_pytorch_model"):
            return True
    return False


def scan_root(root: str) -> list[str]:
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        rel_dir = os.path.relpath(dirpath, root)
        keep: list[str] = []
        for d in sorted(dirnames):
            full = os.path.join(dirpath, d)
            if is_diffusers_dir(full):
                rel = os.path.normpath(os.path.join(rel_dir, d)).replace("\\", "/")
                found.append(rel)
            else:
                keep.append(d)
        dirnames[:] = keep
        for f in filenames:
            if f.lower().endswith(MODEL_EXT):
                found.append(os.path.normpath(os.path.join(rel_dir, f)).replace("\\", "/"))
    return found


def scan_models(roots: Sequence[str]) -> list[str]:
    names: set[str] = set()
    for r in roots:
        names.update(scan_root(r))
    return sorted(names)


def resolve_model(roots: Sequence[str], name: str) -> str | None:
    rel = name.replace("\\", "/")
    if os.path.isabs(rel) or ".." in rel.split("/"):
        return None
    for r in roots:
        p = os.path.join(r, *rel.split("/"))
        if os.path.exists(p):
            return p
    return None


def first_existing(dirs: Sequence[str], files: Sequence[str]) -> str | None:
    for d in dirs:
        for f in files:
            p = os.path.join(d, f)
            if os.path.isfile(p):
                return p
    return None


def _index_shards(directory: str, index_name: str) -> list[str] | None:
    """Shard files listed by a `*.index.json`, or None when there is no readable index."""
    try:
        with open(os.path.join(directory, index_name), encoding="utf-8") as fh:
            index = json.load(fh)
    except (OSError, ValueError):
        return None
    weight_map = index.get("weight_map") if isinstance(index, dict) else None
    if not isinstance(weight_map, dict):
        return None
    names = sorted({str(v) for v in weight_map.values() if isinstance(v, str)})
    return names or None


def _numbered_shards(directory: str, stem: str, ext: str) -> list[str] | None:
    """`<stem>-00001-of-00003<ext>` files, or None when none exist. Raises if the set is incomplete."""
    pat = re.compile(rf"^{re.escape(stem)}-(\d+)-of-(\d+){re.escape(ext)}$")
    try:
        entries = os.listdir(directory)
    except OSError:
        return None
    found: dict[int, str] = {}
    totals: set[int] = set()
    for e in entries:
        m = pat.match(e)
        if m:
            found[int(m.group(1))] = e
            totals.add(int(m.group(2)))
    if not found:
        return None
    total = max(totals)
    missing = [i for i in range(1, total + 1) if i not in found]
    if len(totals) != 1 or missing:
        raise FileNotFoundError(f"{directory}: incomplete sharded weights for {stem}{ext} "
                                f"(have {sorted(found)}, expected {total} shards)")
    return [found[i] for i in sorted(found)]


def find_weights(directory: str, families: Sequence[str]) -> list[str]:
    """Weight files for one component: a single file, or every shard of a sharded checkpoint
    (via its `.index.json` or the `-0000x-of-0000y` naming). Empty list when nothing is there."""
    for ext in WEIGHT_EXTS:
        for family in families:
            for variant in WEIGHT_VARIANTS:
                stem = f"{family}{variant}"
                single = os.path.join(directory, stem + ext)
                if os.path.isfile(single):
                    return [single]
                shards = _index_shards(directory, f"{stem}{ext}.index.json")
                if shards is None:
                    shards = _numbered_shards(directory, stem, ext)
                if shards is not None:
                    paths = [os.path.join(directory, n) for n in shards]
                    missing = [n for n, pth in zip(shards, paths) if not os.path.isfile(pth)]
                    if missing:
                        raise FileNotFoundError(f"{directory}: shard files listed for {stem}{ext} are missing: {missing}")
                    return paths
    return []


@dataclass
class DiffusersComponents:
    unet: list[str] = field(default_factory=list)  # shard paths (one entry for an unsharded file)
    encoders: list[list[str]] = field(default_factory=list)  # one shard list per text encoder
    vae: list[str] = field(default_factory=list)


def diffusers_components(folder: str) -> DiffusersComponents:
    unet: list[str] = []
    for d in [os.path.join(folder, s) for s in DIFFUSION_SUBDIRS] + [folder]:
        unet = find_weights(d, DIFFUSION_FAMILIES)
        if unet:
            break
    encoders = [w for w in (find_weights(os.path.join(folder, d), TEXT_ENCODER_FAMILIES)
                            for d in TEXT_ENCODER_DIRS) if w]
    return DiffusersComponents(unet, encoders, find_weights(os.path.join(folder, "vae"), DIFFUSION_FAMILIES))


def resolve_backend(choice: str, lookup: Callable[[str], T | None]) -> tuple[T, str] | None:
    """First registered alias for `choice`: (function, registry name)."""
    for name in BACKEND_NAMES.get(choice, ()):
        fn = lookup(name)
        if fn is not None:
            return fn, name
    return None


def describe_backend(choice: str, resolved: str) -> str:
    """What was actually selected. ComfyUI only registers one generic `flash` backend, so a
    FlashAttention 3/4 request that resolves to it is not a version-specific kernel."""
    names = BACKEND_NAMES.get(choice, ())
    if names and resolved != names[0]:
        return (f"{choice} requested, but ComfyUI has no '{names[0]}' backend; using its generic "
                f"'{resolved}' backend (the installed flash-attn build, version not selectable)")
    return f"{choice} (registry '{resolved}')"


def backend_choice(sage: str, flash: str) -> str | None:
    """Sage beats Flash when both are set (matches the original's precedence)."""
    if sage != "None":
        return sage
    if flash != "None":
        return flash
    return None
