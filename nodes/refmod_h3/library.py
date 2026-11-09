"""RefMod library: search dirs, listing, name resolution, caching, save paths, sidecars."""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass

from . import _comfy
from ._types import JSONDict, RefModError
from .bundle import AUDIO_FRAMES_PER_SECOND, RefMod, RefModInfo, inspect_file, load_refmod_file

log = logging.getLogger("jezzwtf.refmod_h3")

FOLDER_NAME = "refmods"
RESERVED_DIRS = frozenset({"graph_presets", ".git", "__pycache__"})
EMPTY_NAMES = frozenset({"", "none", "(none)"})
NONE_CHOICE = "(none)"
THUMB_SUFFIX = ".jezzwtf.jpg"
SIDECAR_SUFFIX = ".jezzwtf.json"
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def register_folder() -> None:
    _comfy.register_model_folder(FOLDER_NAME, os.path.join(_comfy.models_dir(), FOLDER_NAME))


def _dedupe_existing(paths: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for p in paths:
        if not p:
            continue
        ap = os.path.normcase(os.path.realpath(os.path.abspath(p)))
        if ap in seen or not os.path.isdir(p):
            continue
        seen.add(ap)
        out.append(os.path.abspath(p))
    return out


_DIR_OVERRIDE: list[str] | None = None


def set_search_dirs_override(dirs: list[str] | None) -> None:
    """Testing hook: replace the search dirs (None restores the ComfyUI-derived list)."""
    global _DIR_OVERRIDE
    _DIR_OVERRIDE = list(dirs) if dirs is not None else None
    _LIST_CACHE.clear()


def search_dirs() -> list[str]:
    if _DIR_OVERRIDE is not None:
        return _dedupe_existing(_DIR_OVERRIDE)
    models = _comfy.models_dir()
    pack = _comfy.PACK_DIR
    candidates = _comfy.folder_paths_for(FOLDER_NAME) + [
        os.path.join(models, "refmods"),
        os.path.join(models, "mods"),
        os.path.join(os.path.dirname(pack), "models", "mods"),
        os.path.join(pack, "mods"),
        os.path.join(models, "audio_refmods"),
    ]
    return _dedupe_existing(candidates)


def save_root() -> str:
    roots = _DIR_OVERRIDE if _DIR_OVERRIDE is not None else (
        _comfy.folder_paths_for(FOLDER_NAME) or [os.path.join(_comfy.models_dir(), FOLDER_NAME)])
    root = os.path.abspath(roots[0])
    os.makedirs(root, exist_ok=True)
    return root


def normalise_name(name: object) -> str:
    if name is None:
        return ""
    s = str(name).strip()
    return "" if s.casefold() in EMPTY_NAMES else s


def check_rel(rel: str, allow_dot: bool = True) -> list[str]:
    if not rel:
        raise RefModError("empty name")
    if _DRIVE_RE.match(rel) or rel.startswith(("/", "\\")) or os.path.isabs(rel):
        raise RefModError(f"invalid refmod name {rel!r}: absolute paths are not allowed")
    parts = [p for p in re.split(r"[\\/]+", rel) if p != ""]
    for p in parts:
        if p == ".." or (not allow_dot and p == "."):
            raise RefModError(f"invalid refmod name {rel!r}: '..' is not allowed")
        if p in RESERVED_DIRS:
            raise RefModError(f"invalid refmod name {rel!r}: reserved folder {p!r}")
    if not parts:
        raise RefModError("empty name")
    return parts


def is_inside(path: str, root: str) -> bool:
    real = os.path.normcase(os.path.realpath(path))
    base = os.path.normcase(os.path.realpath(root))
    try:
        return os.path.commonpath([real, base]) == base
    except ValueError:
        return False


def resolve_stem(name: str, dirs: list[str] | None = None) -> str | None:
    """Resolve a library name to ``<dir>/<name>`` (no extension), or None."""
    n = normalise_name(name)
    if not n:
        return None
    if n.endswith(".safetensors"):
        n = n[: -len(".safetensors")]
    try:
        parts = check_rel(n)
    except RefModError:
        return None
    for d in dirs if dirs is not None else search_dirs():
        stem = os.path.join(d, *parts)
        path = stem + ".safetensors"
        if os.path.isfile(path) and is_inside(path, d):
            return stem
    return None


def resolve_path(name: str) -> str:
    stem = resolve_stem(name)
    if stem is None:
        raise RefModError(f"RefMod {name!r} not found in: {', '.join(search_dirs()) or '(no refmods folder)'}")
    return stem + ".safetensors"


def sanitise_save_name(name: str) -> str:
    s = str(name or "").strip().replace("/", "_").replace("\\", "_")
    if not s:
        raise RefModError("name is empty")
    return s


def mod_output_path(name: str, subfolder: str = "") -> str:
    root = save_root()
    sub = str(subfolder or "").strip()
    parts = check_rel(sub, allow_dot=False) if sub else []
    filename = sanitise_save_name(name)
    check_rel(filename, allow_dot=False)
    path = os.path.join(root, *parts, filename + ".safetensors")
    if not is_inside(path, root):
        raise RefModError(f"save path escapes {root}")
    return path


# --------------------------------------------------------------------------- listing

_LIST_CACHE: dict[str, tuple[tuple[object, ...], dict[str, str]]] = {}
_LIST_LOCK = threading.Lock()


def _walk(d: str) -> list[str]:
    files: list[str] = []
    for root, dirnames, filenames in os.walk(d):
        dirnames[:] = sorted(x for x in dirnames if x not in RESERVED_DIRS)
        for f in sorted(filenames):
            if f.endswith(".safetensors"):
                files.append(os.path.join(root, f))
    return files


def _stat_sig(path: str) -> tuple[int, int]:
    try:
        st = os.stat(path)
        return st.st_size, st.st_mtime_ns
    except OSError:
        return -1, -1


def list_library(dirs: list[str] | None = None) -> dict[str, str]:
    """name -> absolute .safetensors path for every valid RefMod (first dir wins)."""
    use = dirs if dirs is not None else search_dirs()
    found: list[tuple[str, str]] = []
    sig_parts: list[object] = [tuple(use)]
    for d in use:
        for f in _walk(d):
            rel = os.path.relpath(f, d).replace("\\", "/")[: -len(".safetensors")]
            found.append((rel, f))
            sig_parts.append((f, _stat_sig(f), _stat_sig(os.path.splitext(f)[0] + ".json")))
    sig = tuple(sig_parts)
    key = "|".join(use)
    with _LIST_LOCK:
        cached = _LIST_CACHE.get(key)
        if cached is not None and cached[0] == sig:
            return dict(cached[1])
    out: dict[str, str] = {}
    for rel, f in found:
        if rel in out:
            continue
        try:
            inspect_file(f)
        except Exception:
            continue
        out[rel] = f
    with _LIST_LOCK:
        _LIST_CACHE[key] = (sig, out)
    return dict(out)


def combo_choices() -> list[str]:
    try:
        return [NONE_CHOICE] + sorted(list_library(), key=str.casefold)
    except Exception as exc:  # pragma: no cover - filesystem dependent
        log.warning("refmod listing failed: %s", exc)
        return [NONE_CHOICE]


# --------------------------------------------------------------------------- mod cache

def file_stamp(path: str) -> tuple[object, ...]:
    out: list[object] = [os.path.normcase(os.path.abspath(path))]
    for p in (path, os.path.splitext(path)[0] + ".json"):
        try:
            st = os.stat(p)
            out.append((st.st_size, st.st_mtime_ns, st.st_ctime_ns))
        except OSError:
            out.append(None)
    return tuple(out)


@dataclass
class _CacheEntry:
    stamp: tuple[object, ...]
    mods: list[RefMod]
    nbytes: int


class ModCache:
    """FIFO cache: up to ``max_items`` files or ``max_bytes`` of latents."""

    def __init__(self, max_items: int = 24, max_bytes: int = 256 * 1024 * 1024) -> None:
        self.max_items = max_items
        self.max_bytes = max_bytes
        self._items: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    def load(self, path: str) -> list[RefMod]:
        key = os.path.normcase(os.path.abspath(path))
        stamp = file_stamp(path)
        with self._lock:
            hit = self._items.get(key)
            if hit is not None and hit.stamp == stamp:
                return list(hit.mods)
        mods = load_refmod_file(path)
        nbytes = sum(m.latent.numel() * m.latent.element_size() for m in mods)
        with self._lock:
            self._items.pop(key, None)
            if nbytes <= self.max_bytes:
                self._items[key] = _CacheEntry(stamp, mods, nbytes)
                while len(self._items) > self.max_items or \
                        sum(e.nbytes for e in self._items.values()) > self.max_bytes:
                    self._items.popitem(last=False)
        return list(mods)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


MOD_CACHE = ModCache()


# --------------------------------------------------------------------------- sidecars / entries

def thumb_path(stem: str) -> str:
    """Where a thumbnail sidecar is written."""
    return stem + THUMB_SUFFIX


def sidecar_path(stem: str) -> str:
    """Where a JSON sidecar is written."""
    return stem + SIDECAR_SUFFIX


def _mtime(path: str) -> float:
    """Modification time of `path`, 0.0 when it does not exist."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def read_sidecar(stem: str) -> JSONDict:
    try:
        with open(sidecar_path(stem), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


_ENTRY_CACHE: dict[str, tuple[tuple[object, ...], JSONDict]] = {}


def _member_tokens(m: JSONDict) -> tuple[str, int, int]:
    kind = str(m.get("kind", ""))
    t = int(m.get("latent_t", 0) or 0)  # type: ignore[arg-type]
    h = int(m.get("latent_h", 0) or 0)  # type: ignore[arg-type]
    w = int(m.get("latent_w", 0) or 0)  # type: ignore[arg-type]
    if kind == "audio":
        return kind, t, 2 * t
    return kind, t, t * (h // 2) * (w // 2)


def _entry_from_info(name: str, info: RefModInfo, stem: str) -> JSONDict:
    faces = vis = aud = 0
    audio_frames = 0
    desc = ""
    for m in info.members:
        kind, t, toks = _member_tokens(m)
        if kind in ("image", "video"):
            faces += t
            vis += toks
        elif kind == "audio":
            audio_frames += t
            aud += toks
        d = str(m.get("description", "") or "").strip()
        if d and not desc:
            desc = d
    side = read_sidecar(stem)
    peaks = side.get("peaks")
    thumb = thumb_path(stem)
    has_thumb = os.path.isfile(thumb)
    try:
        mtime = int(os.path.getmtime(stem + ".safetensors"))
    except OSError:
        mtime = 0
    thumb_m = int(_mtime(thumb))
    return {
        "name": name,
        "bundle": info.is_bundle,
        "faces": faces,
        "visual_tokens": vis,
        "audio_tokens": aud,
        "audio_seconds": round(audio_frames / AUDIO_FRAMES_PER_SECOND, 2),
        "description": desc,
        "peaks": peaks if isinstance(peaks, list) else [],
        "thumb": has_thumb,
        "stamp": f"{mtime}{thumb_m}",
        "path": stem + ".safetensors",
    }


def library_entry(name: str, path: str | None = None) -> JSONDict | None:
    p = path or (resolve_stem(name) or "") + ".safetensors"
    if not os.path.isfile(p):
        return None
    stem = p[: -len(".safetensors")]
    try:
        st = os.stat(p)
        th, sc = _mtime(thumb_path(stem)), _mtime(sidecar_path(stem))
    except OSError:
        return None
    sig: tuple[object, ...] = (st.st_mtime_ns, st.st_size, th, sc)
    hit = _ENTRY_CACHE.get(name)
    if hit is not None and hit[0] == sig:
        return dict(hit[1])
    try:
        entry = _entry_from_info(name, inspect_file(p), stem)
    except Exception:
        return None
    _ENTRY_CACHE[name] = (sig, entry)
    return dict(entry)


def library_entries() -> list[JSONDict]:
    out: list[JSONDict] = []
    for name, path in sorted(list_library().items(), key=lambda kv: kv[0].casefold()):
        e = library_entry(name, path)
        if e is not None:
            out.append(e)
    return out
