"""Browsing the input and output folders for the Gallery Load window: listing, name parsing and safe path checks."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

IMAGE_EXTENSIONS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")
ROOT_KINDS: tuple[str, ...] = ("input", "output")
MAX_ENTRIES = 1500
_SUFFIX = re.compile(r"^(?P<name>.*?)(?:\s*\[(?P<kind>input|output|temp)\])?$", re.IGNORECASE)


def root_for(kind: str) -> str:
    kind = (kind or "input").lower()
    try:
        import folder_paths  # type: ignore[import-not-found]

        if kind == "output":
            return str(folder_paths.get_output_directory())
        if kind == "temp":
            return str(folder_paths.get_temp_directory())
        return str(folder_paths.get_input_directory())
    except Exception:
        return os.path.abspath(kind)


def inside(root: str, path: str) -> bool:
    base, real = os.path.realpath(root), os.path.realpath(path)
    try:
        return os.path.commonpath([base, real]) == base
    except ValueError:  # different drives on Windows
        return False


@dataclass(frozen=True)
class ImageRef:
    kind: str
    name: str  # forward-slash path relative to the root of `kind`

    def label(self) -> str:
        """The stored form: plain for input, annotated with the folder otherwise (Load Image style)."""
        return self.name if self.kind == "input" else f"{self.name} [{self.kind}]"


def parse_ref(raw: str) -> ImageRef:
    match = _SUFFIX.match((raw or "").strip())
    name = (match.group("name") if match else raw).strip().replace("\\", "/")
    kind = (match.group("kind") if match and match.group("kind") else "input").lower()
    return ImageRef(kind, name)


def resolve_ref(raw: str) -> str:
    """Absolute path of an image reference, only when it lies inside its folder and is an image file."""
    ref = parse_ref(raw)
    if not ref.name:
        raise ValueError("no image chosen")
    root = root_for(ref.kind)
    full = os.path.join(root, *ref.name.split("/"))
    if not inside(root, full):
        raise ValueError(f"image is outside the {ref.kind} folder: {ref.name}")
    if not full.lower().endswith(IMAGE_EXTENSIONS):
        raise ValueError(f"not an image file: {ref.name}")
    if not os.path.isfile(full):
        raise FileNotFoundError(f"image not found: {ref.label()}")
    return os.path.realpath(full)


def parse_selection(text: str) -> list[str]:
    """The picked names from the window's JSON list; blanks and non-strings are dropped."""
    import json

    try:
        data = json.loads(text or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    seen: list[str] = []
    for item in data:
        if isinstance(item, str) and item.strip() and item not in seen:
            seen.append(item)
    return seen


def clean_folder(folder: str) -> str:
    """A relative sub-folder without drive, `..` or empty parts."""
    parts = [p for p in (folder or "").replace("\\", "/").split("/") if p and p not in (".", "..") and ":" not in p]
    return "/".join(parts)


def list_folder(kind: str, folder: str = "", query: str = "") -> dict[str, object]:
    """Sub-folders and image files directly inside `folder` of the input/output root, newest files first."""
    kind = kind.lower() if kind.lower() in ROOT_KINDS else "input"
    rel = clean_folder(folder)
    root = root_for(kind)
    here = os.path.join(root, *rel.split("/")) if rel else root
    if not inside(root, here) or not os.path.isdir(here):
        return {"type": kind, "folder": rel, "folders": [], "files": [], "truncated": False}
    needle = (query or "").strip().lower()
    folders: list[str] = []
    files: list[dict[str, object]] = []
    with os.scandir(here) as entries:
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir(follow_symlinks=False):
                if not needle or needle in entry.name.lower():
                    folders.append(entry.name)
            elif entry.name.lower().endswith(IMAGE_EXTENSIONS) and (not needle or needle in entry.name.lower()):
                stat = entry.stat()
                files.append({"name": f"{rel}/{entry.name}" if rel else entry.name, "size": stat.st_size, "mtime": int(stat.st_mtime)})
    folders.sort(key=str.lower)
    files.sort(key=lambda f: (-int(f["mtime"]), str(f["name"]).lower()))
    return {"type": kind, "folder": rel, "folders": folders, "files": files[:MAX_ENTRIES], "truncated": len(files) > MAX_ENTRIES}
