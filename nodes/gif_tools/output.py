"""Output and input path handling: containment, prefix sanitising and counter-style naming."""
from __future__ import annotations

import os
import re
from collections.abc import Sequence

OUTPUT_SUBFOLDER = "gifs"
_BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_WIN_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])$", re.IGNORECASE)
MAX_COUNTER = 99999


def is_inside(root: str, target: str) -> bool:
    """True when `target` resolves to a path strictly inside `root` (symlinks and `..` resolved)."""
    r, t = os.path.realpath(root), os.path.realpath(target)
    try:
        return os.path.commonpath([r, t]) == r and t != r
    except ValueError:  # different drives on Windows
        return False


def sanitize_prefix(prefix: str, default: str = "gif") -> list[str]:
    """Split a filename prefix into safe path segments (the last is the file stem). No absolute paths, no `..`."""
    if not isinstance(prefix, str):
        raise ValueError("filename_prefix must be a string")
    if "\x00" in prefix:
        raise ValueError("filename_prefix contains a NUL byte")
    text = prefix.strip().replace("\\", "/")
    if text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise ValueError("filename_prefix must be relative to the output folder")
    parts: list[str] = []
    for raw in text.split("/"):
        if raw in ("", "."):
            continue
        if raw == "..":
            raise ValueError("filename_prefix may not contain '..'")
        part = _BAD_CHARS.sub("_", raw).strip(" .") or "_"
        if _WIN_RESERVED.match(part.split(".")[0]):
            part = f"_{part}"
        parts.append(part[:100])
    return parts or [default]


def reserve_output_path(root: str, prefix: str, ext: str, subfolder: str = OUTPUT_SUBFOLDER) -> tuple[str, str, str]:
    """Create (exclusively) the next `<prefix>_00001.<ext>` under root/subfolder.

    Returns (absolute path, subfolder relative to root, filename). The empty file exists on return so concurrent runs
    cannot claim the same counter. Raises ValueError if the result would leave `root`.
    """
    if not re.fullmatch(r"[a-z0-9]{2,5}", ext):
        raise ValueError(f"bad extension {ext!r}")
    *dirs, stem = sanitize_prefix(prefix)
    rel_dir = "/".join([p for p in (subfolder, *dirs) if p])
    folder = os.path.join(root, *rel_dir.split("/")) if rel_dir else root
    if not is_inside(root, os.path.join(folder, "probe")):
        raise ValueError("output path escapes the output folder")
    os.makedirs(folder, exist_ok=True)
    pattern = re.compile(rf"^{re.escape(stem)}_(\d+)\.{re.escape(ext)}$", re.IGNORECASE)
    counter = 0
    for name in os.listdir(folder):
        m = pattern.match(name)
        if m:
            counter = max(counter, int(m.group(1)))
    while counter < MAX_COUNTER:
        counter += 1
        filename = f"{stem}_{counter:05d}.{ext}"
        path = os.path.join(folder, filename)
        try:
            with open(path, "xb"):
                pass
        except FileExistsError:
            continue
        if not is_inside(root, path):  # a symlinked subfolder could point elsewhere
            os.remove(path)
            raise ValueError("output path escapes the output folder")
        return path, rel_dir, filename
    raise ValueError("output folder has no free counter left for this prefix")


def resolve_existing_file(value: str, roots: Sequence[str], extensions: Sequence[str] = (".gif",)) -> str:
    """Resolve a user-supplied name or path to a real file inside one of `roots` (first root wins for relative names)."""
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError("no file given")
    text = value.strip().strip('"')
    candidates = [text] if os.path.isabs(text) else [os.path.join(r, text) for r in roots]
    for cand in candidates:
        real = os.path.realpath(cand)
        if not os.path.isfile(real):
            continue
        if not any(is_inside(r, real) for r in roots):
            raise ValueError("file must be inside the ComfyUI input, output or temp folder")
        if extensions and os.path.splitext(real)[1].lower() not in extensions:
            raise ValueError(f"unsupported file type {os.path.splitext(real)[1]!r}")
        return real
    raise ValueError(f"file not found: {text}")
