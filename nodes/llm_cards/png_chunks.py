"""PNG text-chunk reading/writing without ComfyUI (spec 5.1, 6.3 and 7.2)."""

from __future__ import annotations

import base64
import io
import json
import struct
import zlib
from typing import Mapping

from PIL import Image
from PIL.PngImagePlugin import PngInfo

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def read_text_chunks(data: bytes) -> dict[str, str]:
    """Collect `keyword -> text` from tEXt / zTXt / iTXt chunks; the first occurrence wins."""
    if not data.startswith(PNG_SIG):
        return {}
    out: dict[str, str] = {}
    pos = len(PNG_SIG)
    end = len(data)
    while pos + 8 <= end:
        length, ctype = struct.unpack(">I4s", data[pos : pos + 8])
        body = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctype == b"IEND":
            break
        if len(body) < length:
            break
        try:
            parsed = _parse_text_chunk(ctype, body)
        except (ValueError, zlib.error, UnicodeDecodeError):
            continue
        if parsed is not None and parsed[0] not in out:
            out[parsed[0]] = parsed[1]
    return out


def _parse_text_chunk(ctype: bytes, body: bytes) -> tuple[str, str] | None:
    if ctype == b"tEXt":
        key, _, text = body.partition(b"\x00")
        return key.decode("latin-1"), text.decode("latin-1")
    if ctype == b"zTXt":
        key, _, rest = body.partition(b"\x00")
        return key.decode("latin-1"), zlib.decompress(rest[1:]).decode("utf-8")
    if ctype == b"iTXt":
        key, _, rest = body.partition(b"\x00")
        if len(rest) < 2:
            raise ValueError("short iTXt")
        flag, rest = rest[0], rest[2:]
        _lang, _, rest = rest.partition(b"\x00")
        _translated, _, text = rest.partition(b"\x00")
        if flag:
            text = zlib.decompress(text)
        return key.decode("latin-1"), text.decode("utf-8")
    return None


def sniff_image_kind(data: bytes) -> str:
    """Name the real format of a file, for error messages."""
    if data.startswith(PNG_SIG):
        return "PNG"
    if data[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WebP"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "GIF"
    return "unknown"


def encode_chara(card: Mapping[str, object]) -> str:
    """Card dict -> base64 of real-UTF-8 JSON (default separators)."""
    raw = json.dumps(card, ensure_ascii=False).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def decode_chara(value: str) -> object:
    return json.loads(base64.b64decode(value).decode("utf-8"))


def save_png_with_text(img: Image.Image, path: str, chunks: Mapping[str, str], compress_level: int = 4) -> None:
    info = PngInfo()
    for key, value in chunks.items():
        info.add_text(key, value)
    img.save(path, format="PNG", pnginfo=info, compress_level=compress_level)


def png_bytes_with_text(img: Image.Image, chunks: Mapping[str, str]) -> bytes:
    buf = io.BytesIO()
    info = PngInfo()
    for key, value in chunks.items():
        info.add_text(key, value)
    img.save(buf, format="PNG", pnginfo=info, compress_level=4)
    return buf.getvalue()


def read_png_text_from_file(path: str) -> dict[str, str]:
    with open(path, "rb") as fh:
        return read_text_chunks(fh.read())
