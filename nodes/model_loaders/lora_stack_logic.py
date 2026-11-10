"""Pure logic for the LoRA stack nodes: `lora_data` parsing, folder listing,
name resolution and the state-dict cache. No ComfyUI imports."""
from __future__ import annotations

import json
import math
import os
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import torch

STRENGTH_LIMIT = 10.0
SD = dict[str, torch.Tensor]


@dataclass
class LoraEntry:
    name: str
    on: bool = True
    model: float = 1.0
    clip: float = 1.0
    split: bool = False

    def to_json(self) -> dict[str, object]:
        return {"on": self.on, "name": self.name, "model": self.model, "clip": self.clip, "split": self.split}


def _num(value: object, default: float) -> float:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, float, str)):
        try:
            f = float(value)
        except ValueError:
            return default
        return f if math.isfinite(f) else default
    return default


def _flag(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "off", "no")
    return bool(value)


def parse_lora_data(raw: object) -> list[LoraEntry]:
    """Lenient parse of `{"loras": [...]}` or a bare list. Invalid input → []."""
    data: object = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw) if raw.strip() else []
        except (ValueError, TypeError):
            return []
    if isinstance(data, dict):
        data = data.get("loras", [])
    if not isinstance(data, list):
        return []
    out: list[LoraEntry] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("lora")
        if not isinstance(name, str):
            continue
        name = name.strip()
        if not name or name.upper() == "NONE":
            continue
        if "strength" in item:
            model = clip = _num(item.get("strength"), 1.0)
        else:
            model = _num(item.get("model"), 1.0)
            clip = _num(item.get("clip"), model)
        out.append(LoraEntry(name=name, on=_flag(item.get("on"), True), model=model, clip=clip,
                             split=_flag(item.get("split"), False)))
    return out


def clamp_strength(v: float) -> float:
    return max(-STRENGTH_LIMIT, min(STRENGTH_LIMIT, v))


def compact_float(v: float) -> str:
    s = f"{round(v, 4):g}"
    return "0" if s == "-0" else s


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    size = float(n)
    for unit in ("KB", "MB", "GB", "TB"):
        size /= 1024.0
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
    return f"{size:.1f} TB"  # pragma: no cover


@dataclass
class PlannedLora:
    entry: LoraEntry
    path: str
    model: float
    clip: float


def plan_stack(entries: list[LoraEntry], resolve: Callable[[str], str | None], has_clip: bool,
               log: Callable[[str], None] | None = None) -> list[PlannedLora]:
    """Decide which entries get applied, in order (skips, clamps, de-duplicates)."""
    seen: set[str] = set()
    plan: list[PlannedLora] = []
    for e in entries:
        if not e.on:
            continue
        m, c = clamp_strength(e.model), clamp_strength(e.clip)
        if m == 0 and (not has_clip or c == 0):
            continue
        path = resolve(e.name)
        if not path or not os.path.isfile(path):
            if log:
                log(f"LoRA not found, skipped: {e.name}")
            continue
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            if log:
                log(f"LoRA already applied, skipped duplicate: {e.name}")
            continue
        seen.add(key)
        plan.append(PlannedLora(entry=e, path=path, model=m, clip=c))
    return plan


LoadLora = Callable[[object, object, Mapping[str, object], float, float], tuple[object, object]]


def apply_planned(load: LoadLora, model: object, clip: object | None, sd: Mapping[str, object],
                  p: PlannedLora) -> tuple[object, object | None]:
    """Patch one planned LoRA. A side with zero strength (or no clip) is passed as None so
    ComfyUI neither clones nor re-patches it: its patches_uuid, and any cache keyed on it, survive."""
    model_in = model if p.model != 0 else None
    clip_in = clip if clip is not None and p.clip != 0 else None
    new_model, new_clip = load(model_in, clip_in, sd, p.model, p.clip)
    return (new_model if new_model is not None else model), (new_clip if new_clip is not None else clip)


def applied_summary(plan: list[PlannedLora]) -> str:
    if not plan:
        return "(none)"
    return ", ".join(f"{p.entry.name}@{compact_float(p.model)}" for p in plan)


class StateDictCache:
    """LRU cache of loaded LoRA state dicts keyed by (path, mtime); hands out shallow copies
    because `load_lora_for_models` may consume the dict."""

    def __init__(self, max_entries: int = 8) -> None:
        self.max_entries = max_entries
        self._items: OrderedDict[tuple[str, float], SD] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, path: str, loader: Callable[[str], Mapping[str, torch.Tensor]]) -> SD:
        key = (os.path.abspath(path), os.path.getmtime(path))
        with self._lock:
            hit = self._items.get(key)
            if hit is not None:
                self._items.move_to_end(key)
                return dict(hit)
        sd = dict(loader(path))
        with self._lock:
            for k in [k for k in self._items if k[0] == key[0]]:
                del self._items[k]  # stale mtime for the same path
            self._items[key] = sd
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)
        return dict(sd)

    def __len__(self) -> int:
        return len(self._items)


# ---- folder stack ---------------------------------------------------------------------------

def sanitize_subfolder(folder: str) -> str:
    """Normalise a user-supplied subfolder of models/loras; reject traversal / absolute paths."""
    f = (folder or "").strip().replace("\\", "/")
    if f.startswith("/") or ":" in f or os.path.isabs(f):
        raise ValueError(f"LoRA folder must be relative to models/loras: {folder!r}")
    f = f.strip("/")
    if not f or f == ".":
        return ""
    parts = [p for p in f.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError(f"LoRA folder may not contain '..': {folder!r}")
    return "/".join(parts)


def folder_files(roots: list[str], folder: str) -> dict[str, str]:
    """basename → full path for every `.safetensors` directly inside `<root>/<folder>`
    (first root wins), ordered case-insensitively."""
    sub = sanitize_subfolder(folder)
    found: dict[str, str] = {}
    for root in roots:
        d = os.path.join(root, *sub.split("/")) if sub else root
        root_abs = os.path.abspath(root)
        d_abs = os.path.abspath(d)
        if os.path.commonpath([root_abs, d_abs]) != root_abs or not os.path.isdir(d_abs):
            continue
        for fn in os.listdir(d_abs):
            full = os.path.join(d_abs, fn)
            if fn.lower().endswith(".safetensors") and os.path.isfile(full) and fn not in found:
                found[fn] = full
    return {k: found[k] for k in sorted(found, key=str.lower)}


def resolve_in_folder(files: Mapping[str, str], name: str) -> str | None:
    """Resolve by basename only, which blocks path traversal."""
    base = os.path.basename(name.replace("\\", "/"))
    return files.get(base)


def list_subfolders(roots: list[str], max_depth: int = 4) -> list[str]:
    """Relative subfolders (forward slashes) holding at least one `.safetensors`; "" = root."""
    out: set[str] = set()
    for root in roots:
        if not os.path.isdir(root):
            continue
        root_abs = os.path.abspath(root)
        for dirpath, dirnames, filenames in os.walk(root_abs, followlinks=True):
            rel = os.path.relpath(dirpath, root_abs).replace("\\", "/")
            rel = "" if rel == "." else rel
            depth = 0 if not rel else rel.count("/") + 1
            if depth >= max_depth:
                dirnames[:] = []
            if any(f.lower().endswith(".safetensors") for f in filenames):
                out.add(rel)
    return sorted(out, key=str.lower)


def folder_listing(files: Mapping[str, str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for i, (name, path) in enumerate(files.items(), start=1):
        try:
            size = os.path.getsize(path)
            present = True
        except OSError:
            size, present = 0, False
        rows.append({"index": i, "filename": name, "present": present, "size": size,
                     "size_str": human_size(size)})
    return rows
