"""OS clipboard reading for Paste Stack. Pure logic, importable without ComfyUI.

The clipboard is only ever held in memory and returned to the caller; nothing read from
it is written to disk. Paths come from the OS clipboard, never from the request.
"""

from __future__ import annotations

import base64
import io
import ipaddress
import mimetypes
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from typing import Optional, TypedDict
from urllib.parse import urlsplit

MAX_FILES = 10
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TOTAL_BYTES = 60 * 1024 * 1024
POWERSHELL_TIMEOUT_S = 6
CREATE_NO_WINDOW = 0x08000000

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    "png jpg jpeg webp gif bmp avif tif tiff txt md json csv tsv yaml yml log ini toml xml".split()
)

MIME_OVERRIDES: dict[str, str] = {
    "webp": "image/webp",
    "avif": "image/avif",
    "md": "text/markdown",
    "json": "application/json",
}

# Fixed script; no request or clipboard data is ever interpolated into it.
POWERSHELL_SCRIPT = (
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    "Add-Type -AssemblyName System.Windows.Forms; "
    "$files = [System.Windows.Forms.Clipboard]::GetFileDropList(); "
    "if ($files) { foreach ($f in $files) { Write-Output $f } }"
)
POWERSHELL_ARGS: tuple[str, ...] = (
    "powershell",
    "-NoProfile",
    "-NonInteractive",
    "-STA",
    "-Command",
    POWERSHELL_SCRIPT,
)

_LOOPBACK_NAMES = frozenset({"localhost"})


class ClipboardFile(TypedDict):
    name: str
    mime: str
    data: str


# --------------------------------------------------------------------------- caller checks


def _is_loopback_host(host: str) -> bool:
    candidate = host.strip().strip("[]").lower()
    if not candidate:
        return False
    if candidate in _LOOPBACK_NAMES:
        return True
    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped.is_loopback
    return ip.is_loopback


def is_local_caller(remote: Optional[str]) -> bool:
    """True only for a loopback peer address (127.0.0.0/8, ::1, ::ffff:127.x, localhost)."""
    if not remote:
        return False
    return _is_loopback_host(remote.split("%", 1)[0])


def _hostname_of_host_header(host: str) -> str:
    host = host.strip()
    if host.startswith("["):
        end = host.find("]")
        return host[1:end] if end > 0 else ""
    if host.count(":") == 1:
        return host.split(":", 1)[0]
    return host


def is_local_request_origin(host_header: Optional[str], origin: Optional[str]) -> bool:
    """Defence against DNS rebinding and cross-site calls.

    The Host header must name a loopback host; an Origin header, when sent, must too.
    """
    if not host_header or not _is_loopback_host(_hostname_of_host_header(host_header)):
        return False
    if origin is None:
        return True
    try:
        hostname = urlsplit(origin).hostname
    except ValueError:
        return False
    return bool(hostname) and _is_loopback_host(hostname or "")


# --------------------------------------------------------------------------- parsing and selection


def parse_powershell_paths(output: bytes) -> list[str]:
    """Decode the PowerShell stdout into a list of non-blank trimmed lines."""
    text = output.decode("utf-8", errors="replace").lstrip("﻿")
    return [line.strip() for line in text.splitlines() if line.strip()]


def extension_of(path: str) -> str:
    return os.path.splitext(path)[1].lower().lstrip(".")


def mime_for(path: str) -> str:
    override = MIME_OVERRIDES.get(extension_of(path))
    if override:
        return override
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def select_file_paths(
    paths: Sequence[str],
    sizes: Optional[Mapping[str, int]] = None,
) -> list[tuple[str, int]]:
    """Apply the allowlist and size limits; returns (path, size) pairs to read.

    `sizes` lets tests supply sizes; otherwise the filesystem is consulted. Folders,
    missing files, disallowed extensions and oversized files are skipped silently, and a
    skipped large file does not stop later smaller ones from being added.
    """
    chosen: list[tuple[str, int]] = []
    total = 0
    for path in paths:
        if len(chosen) >= MAX_FILES:
            break
        try:
            if "\x00" in path or extension_of(path) not in ALLOWED_EXTENSIONS:
                continue
            if sizes is not None:
                if path not in sizes:
                    continue
                size = sizes[path]
            else:
                if not os.path.isfile(path):
                    continue
                size = os.path.getsize(path)
        except (OSError, ValueError):
            continue
        if size > MAX_FILE_BYTES or total + size > MAX_TOTAL_BYTES:
            continue
        chosen.append((path, size))
        total += size
    return chosen


def read_files(paths: Sequence[str]) -> list[ClipboardFile]:
    """Read the allowed files fully into memory and return them base64-encoded."""
    files: list[ClipboardFile] = []
    total = 0
    for path, _size in select_file_paths(paths):
        try:
            with open(path, "rb") as handle:
                data = handle.read(MAX_FILE_BYTES + 1)
        except OSError:
            continue
        if len(data) > MAX_FILE_BYTES or total + len(data) > MAX_TOTAL_BYTES:
            continue
        total += len(data)
        files.append(
            {
                "name": os.path.basename(path),
                "mime": mime_for(path),
                "data": base64.b64encode(data).decode("ascii"),
            }
        )
    return files


def encode_png(image: object) -> ClipboardFile:
    """Encode a Pillow image as an in-memory PNG entry named clipboard.png."""
    from PIL import Image

    if not isinstance(image, Image.Image):
        raise TypeError("not an image")
    buffer = io.BytesIO()
    image.convert("RGBA").save(buffer, format="PNG")
    return {
        "name": "clipboard.png",
        "mime": "image/png",
        "data": base64.b64encode(buffer.getvalue()).decode("ascii"),
    }


# --------------------------------------------------------------------------- OS access


def _pillow_clipboard() -> tuple[list[str], Optional[object]]:
    try:
        from PIL import Image, ImageGrab

        grabbed = ImageGrab.grabclipboard()
        if isinstance(grabbed, (list, tuple)):
            return [str(item) for item in grabbed], None
        if isinstance(grabbed, Image.Image) and grabbed.width > 0 and grabbed.height > 0:
            return [], grabbed
    except Exception:  # noqa: BLE001 - missing Pillow or clipboard tools
        pass
    return [], None


def _powershell_paths() -> list[str]:
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            list(POWERSHELL_ARGS),
            capture_output=True,
            timeout=POWERSHELL_TIMEOUT_S,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    return parse_powershell_paths(completed.stdout)


def read_clipboard_content() -> tuple[list[str], Optional[object]]:
    """Return (file paths, raw image) from the OS clipboard."""
    paths, image = _pillow_clipboard()
    if paths or image is not None:
        return paths, image
    if sys.platform == "win32":
        return _powershell_paths(), None
    return [], None


def collect_clipboard_files() -> list[ClipboardFile]:
    """Blocking; run it in an executor. Never raises."""
    try:
        paths, image = read_clipboard_content()
        files = read_files(paths)
        if not files and image is not None:
            files = [encode_png(image)]
        return files
    except Exception:  # noqa: BLE001 - unexpected errors become an empty list
        return []
