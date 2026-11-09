"""Pure helpers for the folder batch loaders and the caption saver."""
from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".jfif", ".webp", ".bmp", ".tif", ".tiff", ".gif"})
VIDEO_EXTS = frozenset({".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".flv", ".wmv", ".mpg", ".mpeg",
                        ".ts", ".3gp"})
SORT_NUMERIC = "numeric (001, 002, 10...)"
SORT_ALPHA = "alphabetical"
SORT_MODES = (SORT_NUMERIC, SORT_ALPHA)

_EXT_OK = re.compile(r"[A-Za-z0-9_-]+")
BLOCKED_CAPTION_EXTS = frozenset({
    "bat", "cmd", "ps1", "psm1", "psd1", "exe", "sh", "bash", "zsh", "py", "pyw", "pyc", "js", "mjs", "cjs", "jse",
    "dll", "lnk", "com", "scr", "vbs", "vbe", "wsf", "wsh", "msi", "msc", "jar", "hta", "cpl", "reg", "pif", "url",
    "scf", "inf", "sys", "ocx", "php", "pl", "rb", "apk", "app", "command", "desktop", "run", "bin", "gadget",
})

_PCT_VAR = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")
_DIGITS = re.compile(r"(\d+)")

NaturalPart = tuple[int, int | str]


def clean_path(raw: str) -> str:
    s = (raw or "").strip()
    while len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    s = s.strip("\"'").strip()
    if not s:
        return ""
    s = os.path.expanduser(s)
    s = _PCT_VAR.sub(lambda m: os.environ.get(m.group(1), m.group(0)), s)
    return os.path.expandvars(s)


def natural_key(name: str) -> tuple[tuple[NaturalPart, ...], str]:
    parts: list[NaturalPart] = []
    for piece in _DIGITS.split(name):
        if not piece:
            continue
        parts.append((0, int(piece)) if piece.isdigit() else (1, piece.casefold()))
    return (tuple(parts), name)


def sort_names(names: Iterable[str], mode: str) -> list[str]:
    if mode == SORT_ALPHA:
        return sorted(names, key=lambda n: (n.casefold(), n))
    return sorted(names, key=natural_key)


def list_media(folder: str, kind: str, sort_mode: str = SORT_NUMERIC) -> list[str]:
    """Return sorted full paths of matching files (non-recursive)."""
    path = clean_path(folder)
    if not path:
        raise ValueError("folder_path is empty")
    if not os.path.isdir(path):
        raise FileNotFoundError(f"folder not found: {path}")
    exts = VIDEO_EXTS if kind == "video" else IMAGE_EXTS
    names = [e.name for e in os.scandir(path)
             if e.is_file() and os.path.splitext(e.name)[1].lower() in exts]
    return [os.path.join(path, n) for n in sort_names(names, sort_mode)]


def resolve_index(index: int, total: int, auto_run: bool = False) -> int:
    """Single mode wraps (index mod total). Folder mode (auto_run) never wraps: past the end is an error."""
    if total <= 0:
        raise ValueError("no files to index")
    index = int(index)
    if auto_run:
        if index >= total:
            raise ValueError(f"index {index} is past the last file ({total} found); set index to 0")
        return index
    return index % total


def next_index(idx: int, total: int, auto_run: bool) -> int:
    return idx + 1 if auto_run and idx + 1 < total else -1


def preview_name(fullpath: str, mtime_ns: int) -> str:
    digest = hashlib.md5(f"{fullpath}|{mtime_ns}".encode("utf-8")).hexdigest()[:16]
    return f"jwtf_fbl_{digest}.png"


def caption_extension(extension: str) -> str:
    """A safe caption extension: [A-Za-z0-9_-]+, never an executable or script type."""
    ext = (extension or "").strip().lstrip(".") or "txt"
    if not _EXT_OK.fullmatch(ext):
        raise ValueError(f"invalid extension '{ext}': use letters, digits, '_' or '-' only")
    if ext.lower() in BLOCKED_CAPTION_EXTS:
        raise ValueError(f"extension '{ext}' is not allowed for captions")
    return ext


def _inside(directory: str, target: str) -> bool:
    root, path = os.path.realpath(directory), os.path.realpath(target)
    try:
        return os.path.commonpath([root, path]) == root and path != root
    except ValueError:  # different drives on Windows
        return False


def caption_target(image_path: str, save_location: str, custom_folder: str, extension: str) -> str:
    path = clean_path(image_path)
    if not path:
        raise ValueError("image_path is empty")
    stem = os.path.splitext(os.path.basename(path))[0]
    ext = caption_extension(extension)
    if "\0" in stem or (os.name == "nt" and ":" in stem):
        raise ValueError("image file name is not usable for a caption")
    if save_location == "custom folder":
        directory = clean_path(custom_folder)
        if not directory:
            raise ValueError("custom_folder is empty")
    else:
        directory = os.path.dirname(path)
    target = os.path.join(directory, f"{stem}.{ext}")
    if not _inside(directory or ".", target):
        raise ValueError("caption path escapes the chosen folder")
    return target


def fit_even(w: int, h: int, longest: int) -> tuple[int, int]:
    if longest > 0 and max(w, h) > longest:
        s = longest / max(w, h)
        w, h = int(round(w * s)), int(round(h * s))
    return max(2, w - w % 2), max(2, h - h % 2)


@dataclass
class FrameSelector:
    """Decides which raw decoded frames to keep."""

    src_fps: float
    force_rate: float = 0.0
    skip_first: int = 0
    nth: int = 1
    cap: int = 0
    step: float = field(init=False)
    next_t: float = field(init=False)
    accepted: int = field(init=False, default=0)
    kept: int = field(init=False, default=0)
    last_kept_raw: int = field(init=False, default=-1)

    def __post_init__(self) -> None:
        self.nth = max(1, int(self.nth))
        self.step = self.src_fps / self.force_rate if 0 < self.force_rate < self.src_fps else 1.0
        self.next_t = float(self.skip_first)

    @property
    def done(self) -> bool:
        return self.cap > 0 and self.kept >= self.cap

    def offer(self, i: int) -> bool:
        if self.done or i < self.skip_first or i < self.next_t:
            return False
        self.next_t += self.step
        k = self.accepted
        self.accepted += 1
        if k % self.nth:
            return False
        self.kept += 1
        self.last_kept_raw = i
        return True

    @property
    def out_fps(self) -> float:
        return self.src_fps / self.step / self.nth

    def audio_window(self) -> tuple[float, float | None]:
        start = self.skip_first / self.src_fps
        end = (self.last_kept_raw + 1) / self.src_fps if self.done else None
        return start, end
