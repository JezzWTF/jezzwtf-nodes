"""Option vocabularies, validation helpers and mode presets for the GIF tools. Pure Python, no ComfyUI imports."""
from __future__ import annotations

import math
from dataclasses import dataclass

MODES = ("quality", "balanced", "smallest", "target_size")
PALETTES = ("auto", "global_full", "global_diff", "per_frame")
DITHERS = ("auto", "none", "bayer_1", "bayer_2", "bayer_3", "bayer_4", "bayer_5", "sierra2_4a", "floyd_steinberg")
RESIZE_FILTERS = ("lanczos", "bicubic", "bilinear", "box", "nearest")
DELAY_MODES = ("exact", "even")
DENOISE = ("auto", "off", "light", "strong")

MIN_COLORS = 16
MAX_COLORS = 256
MAX_OUTPUT_FRAMES = 10000
MAX_DIMENSION = 8192

# Mean absolute difference (0..255 scale) under which a frame counts as a duplicate of the last kept one.
DEDUPE_OFF = -1.0


@dataclass(frozen=True)
class Preset:
    colors: int
    dedupe_threshold: float
    denoise: str
    dither_bias: str  # "quality" | "balanced" | "smallest": how the auto dither picker weighs size against fidelity


PRESETS: dict[str, Preset] = {
    "quality": Preset(colors=256, dedupe_threshold=0.0, denoise="off", dither_bias="quality"),
    "balanced": Preset(colors=192, dedupe_threshold=0.4, denoise="off", dither_bias="balanced"),
    "smallest": Preset(colors=96, dedupe_threshold=1.2, denoise="light", dither_bias="smallest"),
    # target_size searches its own colour/scale/fps ladder; these are the starting point for the first trial.
    "target_size": Preset(colors=256, dedupe_threshold=0.4, denoise="off", dither_bias="balanced"),
}


def check_choice(name: str, value: object, allowed: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}; got {value!r}")
    return value


def check_int(name: str, value: object, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{name} must be an integer; got {value!r}")
    out = int(value)
    if not lo <= out <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}; got {out}")
    return out


def check_float(name: str, value: object, lo: float, hi: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number; got {value!r}")
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite; got {out}")
    if not lo <= out <= hi:
        raise ValueError(f"{name} must be between {lo:g} and {hi:g}; got {out:g}")
    return out


def check_colors(value: object) -> int:
    """0 means "by mode"; otherwise 16..256."""
    n = check_int("colors", value, 0, MAX_COLORS)
    if n != 0 and n < MIN_COLORS:
        raise ValueError(f"colors must be 0 (by mode) or between {MIN_COLORS} and {MAX_COLORS}; got {n}")
    return n
