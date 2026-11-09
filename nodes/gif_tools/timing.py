"""GIF frame-delay arithmetic. GIF stores delays in whole centiseconds (10 ms) and browsers treat <= 10 ms as 100 ms,
so the shortest usable delay is 2 cs (20 ms, 50 fps)."""
from __future__ import annotations

import math
from collections.abc import Sequence

MIN_DELAY_CS = 2
MAX_DELAY_CS = 65535
MAX_FPS = 100.0 / MIN_DELAY_CS


def even_fps(fps: float) -> float:
    """The nearest rate with a whole-centisecond frame period (50, 33.3, 25, 20, 16.7, 14.3, 12.5, ...)."""
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError(f"fps must be positive; got {fps}")
    centre = max(MIN_DELAY_CS, round(100.0 / fps))
    lo, hi = max(MIN_DELAY_CS, centre - 1), centre + 1
    return 100.0 / min(range(lo, hi + 1), key=lambda cs: abs(100.0 / cs - fps))


def fps_notes(fps: float, delay_mode: str) -> list[str]:
    """Warnings for a requested output rate. Empty when the rate maps onto whole centiseconds."""
    if fps > MAX_FPS + 1e-9:
        return [f"{fps:g} fps is above the 50 fps GIF ceiling (browsers play 10 ms delays as 100 ms); clamped to 50."]
    cs = 100.0 / fps
    if abs(cs - round(cs)) <= 1e-6:
        return []
    snapped = even_fps(fps)
    if delay_mode == "even":
        return [f"{fps:g} fps has no whole 10 ms period; snapped to {snapped:.3g} fps so every delay is identical."]
    return [
        f"{fps:g} fps is not a whole number of 10 ms steps; delays alternate between {math.floor(cs)} and {math.ceil(cs)} cs "
        f"to keep real-time speed. Use {snapped:.3g} fps (or 25, 20, 12.5) for a perfectly even cadence."
    ]


def resolve_fps(fps: float, delay_mode: str) -> float:
    fps = min(fps, MAX_FPS)
    return even_fps(fps) if delay_mode == "even" else fps


def quantise_delays(durations_s: Sequence[float]) -> list[int]:
    """Whole-centisecond delays whose running total tracks the true timeline (error diffusion), never below 2 cs."""
    out: list[int] = []
    ideal = 0.0
    emitted = 0
    for d in durations_s:
        if not math.isfinite(d) or d < 0:
            raise ValueError(f"duration must be finite and non-negative; got {d}")
        ideal += d * 100.0
        want = int(math.floor(ideal + 0.5)) - emitted
        want = max(MIN_DELAY_CS, min(MAX_DELAY_CS, want))
        out.append(want)
        emitted += want
    return out


def cs_to_fps(delays_cs: Sequence[int]) -> float:
    total = sum(delays_cs)
    return 100.0 * len(delays_cs) / total if total else 0.0
