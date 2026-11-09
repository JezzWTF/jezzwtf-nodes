"""Where audio files may be read from and written to, and how a picker name becomes a real path."""
from __future__ import annotations

import os

AUDIO_EXTENSIONS: tuple[str, ...] = (".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wma", ".aiff")
COVER_EXTENSIONS: tuple[str, ...] = (".mp3", ".flac", ".m4a")
MAX_LISTED = 2000
MAX_DEPTH = 4


def input_dir() -> str:
    try:
        import folder_paths  # type: ignore[import-not-found]

        return str(folder_paths.get_input_directory())
    except Exception:
        return os.path.abspath("input")


def output_dir() -> str:
    try:
        import folder_paths  # type: ignore[import-not-found]

        return str(folder_paths.get_output_directory())
    except Exception:
        return os.path.abspath("output")


def temp_dir() -> str:
    try:
        import folder_paths  # type: ignore[import-not-found]

        return str(folder_paths.get_temp_directory())
    except Exception:
        return os.path.abspath("temp")


def read_roots() -> list[str]:
    return [input_dir(), output_dir(), temp_dir()]


def inside(root: str, path: str) -> bool:
    base, real = os.path.realpath(root), os.path.realpath(path)
    try:
        return os.path.commonpath([base, real]) == base
    except ValueError:  # different drives on Windows
        return False


def list_audio(root: str | None = None) -> list[str]:
    """Audio files under the input folder as forward-slash relative names, shallowest first."""
    base = root or input_dir()
    found: list[str] = []
    if not os.path.isdir(base):
        return found
    for current, dirs, files in os.walk(base):
        depth = 0 if current == base else os.path.relpath(current, base).count(os.sep) + 1
        if depth >= MAX_DEPTH:
            dirs[:] = []
        dirs.sort()
        for name in sorted(files, key=str.lower):
            if name.lower().endswith(AUDIO_EXTENSIONS):
                found.append(os.path.relpath(os.path.join(current, name), base).replace(os.sep, "/"))
        if len(found) >= MAX_LISTED:
            break
    return sorted(found[:MAX_LISTED], key=lambda n: (n.count("/"), n.lower()))


def resolve_audio(name_or_path: str) -> str:
    """A picker name (relative to input) or an absolute path, only when it lies in input, output or temp."""
    raw = (name_or_path or "").strip().strip('"')
    if not raw:
        raise ValueError("no audio file chosen")
    candidates = [raw] if os.path.isabs(raw) else [os.path.join(root, raw) for root in read_roots()]
    for candidate in candidates:
        if os.path.isfile(candidate) and any(inside(root, candidate) for root in read_roots()):
            return os.path.realpath(candidate)
    if any(os.path.isfile(c) for c in candidates):
        raise ValueError("audio files can only be read from the input, output or temp folders")
    raise FileNotFoundError(f"audio file not found: {raw}")
