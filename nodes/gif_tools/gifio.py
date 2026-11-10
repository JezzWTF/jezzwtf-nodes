"""GIF reading and writing: Pillow decode, raw delay patching, and the Pillow-only encode fallback."""
from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageSequence

from .frames import Frame
from .settings import MAX_OUTPUT_FRAMES
from .timing import MIN_DELAY_CS


@dataclass
class GifData:
    frames: list[Frame]          # composited RGB canvases
    alphas: list[NDArray[np.uint8]]  # 255 = opaque, per frame
    durations: list[float]       # seconds, with the browser 10 ms rule applied
    loop: int                    # NETSCAPE loop count; 0 = forever, -1 = no extension (play once)
    notes: list[str]

    @property
    def has_transparency(self) -> bool:
        return any(int(a.min()) < 255 for a in self.alphas)


def browser_delay_ms(ms: int) -> int:
    """Browsers play delays of 10 ms or less as 100 ms; mirror that so timing matches what people see."""
    return 100 if ms <= 10 else ms


def read_gif(source: str | bytes, browser_rule: bool = True) -> GifData:
    """Decode any Pillow-readable animation (GIF, WebP, APNG). `browser_rule` applies the GIF 10 ms floor."""
    notes: list[str] = []
    frames: list[Frame] = []
    alphas: list[NDArray[np.uint8]] = []
    durations: list[float] = []
    fixed = 0
    handle = io.BytesIO(source) if isinstance(source, bytes) else source
    with Image.open(handle) as im:
        loop = int(im.info.get("loop", -1))
        for n, page in enumerate(ImageSequence.Iterator(im)):
            if n >= MAX_OUTPUT_FRAMES:
                notes.append(f"GIF truncated at {MAX_OUTPUT_FRAMES} frames")
                break
            rgba = np.asarray(page.convert("RGBA"), dtype=np.uint8)
            frames.append(np.ascontiguousarray(rgba[..., :3]))
            alphas.append(np.ascontiguousarray(rgba[..., 3]))
            raw = int(page.info.get("duration", 100))
            ms = browser_delay_ms(raw) if browser_rule else max(1, raw)
            fixed += ms != raw
            durations.append(ms / 1000.0)
    if not frames:
        raise ValueError("GIF contains no frames")
    if fixed:
        notes.append(f"{fixed} frame(s) had a delay of 10 ms or less; treated as 100 ms like browsers do")
    return GifData(frames, alphas, durations, loop, notes)


# ------------------------------------------------------------------ raw structure

def _skip_sub_blocks(data: bytes, pos: int) -> int:
    while True:
        size = data[pos]
        pos += 1
        if size == 0:
            return pos
        pos += size


def scan_gif(data: bytes) -> tuple[list[int], int, int]:
    """Walk the GIF block structure. Returns (offsets of each frame's delay field, loop count (-1 if none), local-palette frames)."""
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        raise ValueError("not a GIF")
    pos = 13
    flags = data[10]
    if flags & 0x80:
        pos += 3 * (2 << (flags & 7))
    delay_offsets: list[int] = []
    loop = -1
    local_palettes = 0
    while pos < len(data):
        marker = data[pos]
        if marker == 0x3B:
            break
        if marker == 0x21:
            label = data[pos + 1]
            if label == 0xF9 and data[pos + 2] == 4:
                delay_offsets.append(pos + 4)
            elif label == 0xFF and data[pos + 2] == 11 and data[pos + 3 : pos + 14] == b"NETSCAPE2.0":
                loop = int.from_bytes(data[pos + 16 : pos + 18], "little")
            pos = _skip_sub_blocks(data, pos + 2)
        elif marker == 0x2C:
            lflags = data[pos + 9]
            pos += 10
            if lflags & 0x80:
                local_palettes += 1
                pos += 3 * (2 << (lflags & 7))
            pos = _skip_sub_blocks(data, pos + 1)
        else:
            raise ValueError(f"corrupt GIF block 0x{marker:02x} at {pos}")
    return delay_offsets, loop, local_palettes


def patch_gif_delays(data: bytes, delays_cs: Sequence[int]) -> bytes:
    """Rewrite every frame's delay field. The number of delays must equal the number of frames in the file."""
    offsets, _, _ = scan_gif(data)
    if len(offsets) != len(delays_cs):
        raise ValueError(f"GIF has {len(offsets)} frames but {len(delays_cs)} delays were given")
    out = bytearray(data)
    for off, cs in zip(offsets, delays_cs):
        if not MIN_DELAY_CS <= cs <= 0xFFFF:
            raise ValueError(f"delay {cs} cs is outside {MIN_DELAY_CS}..65535")
        out[off : off + 2] = int(cs).to_bytes(2, "little")
    return bytes(out)


def read_delays_cs(data: bytes) -> list[int]:
    offsets, _, _ = scan_gif(data)
    return [int.from_bytes(data[o : o + 2], "little") for o in offsets]


# ------------------------------------------------------------------ Pillow fallback encoder

_PIL_DITHER = {
    "none": Image.Dither.NONE,
    "floyd_steinberg": Image.Dither.FLOYDSTEINBERG,
}


def encode_with_pillow(frames: Sequence[Frame], delays_cs: Sequence[int], colors: int, dither: str, loop: int, per_frame: bool = False) -> bytes:
    """Pillow-only GIF encode: shared median-cut palette (or one per frame), optional Floyd-Steinberg, Pillow frame cropping."""
    if len(frames) != len(delays_cs) or not frames:
        raise ValueError("frames and delays must be non-empty and equal in length")
    use_dither = _PIL_DITHER.get(dither, Image.Dither.FLOYDSTEINBERG if dither != "none" else Image.Dither.NONE)
    pics = [Image.fromarray(f, "RGB") for f in frames]
    if per_frame:
        paletted = [p.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=use_dither) for p in pics]
    else:
        step = max(1, len(pics) // 12)
        sample = pics[::step][:12]
        w, h = sample[0].size
        sheet = Image.new("RGB", (w, h * len(sample)))
        for i, s in enumerate(sample):
            sheet.paste(s, (0, i * h))
        palette = sheet.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        paletted = [p.quantize(palette=palette, dither=use_dither) for p in pics]
    buf = io.BytesIO()
    kwargs: dict[str, object] = {"save_all": True, "append_images": paletted[1:], "duration": [int(c) * 10 for c in delays_cs], "optimize": False}
    if loop >= 0:
        kwargs["loop"] = loop
    paletted[0].save(buf, format="GIF", **kwargs)
    return patch_gif_delays(buf.getvalue(), delays_cs) if len(read_delays_cs(buf.getvalue())) == len(delays_cs) else buf.getvalue()
