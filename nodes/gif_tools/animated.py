"""Animated WebP / APNG encoding with the same size-vs-quality ideas as the GIF engine (Pillow only)."""
from __future__ import annotations

import io
import time
from dataclasses import dataclass, field

from PIL import Image

from .frames import Clip, dedupe
from .gifio import read_gif
from .quality import QualityReport, compare_sequences
from .runtime import Check, check_interrupt

FORMATS = ("webp", "apng")
MB = 1024 * 1024


@dataclass
class AnimResult:
    data: bytes
    fmt: str
    clip: Clip
    quality: QualityReport
    quality_setting: int | None
    method: int
    lossless: bool
    trials: int = 0
    fits: bool | None = None
    budget_bytes: int = 0
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def stats(self) -> dict[str, float | int | str | bool | None]:
        w, h = self.clip.size
        total = self.clip.total
        return {
            "bytes": len(self.data), "frames": len(self.clip.frames), "fps": round(len(self.clip.frames) / total, 2) if total else 0,
            "width": w, "height": h, "ssim": round(self.quality.ssim_mean, 4), "ssim_min": round(self.quality.ssim_min, 4),
            "psnr": round(self.quality.psnr_mean, 2), "format": self.fmt, "quality": self.quality_setting,
            "lossless": self.lossless, "budget_bytes": self.budget_bytes or None, "fits": self.fits,
        }

    def report(self) -> str:
        s = self.stats()
        mode = "lossless" if self.lossless else f"lossy q{self.quality_setting}"
        lines = [f"{len(self.data):,} bytes ({len(self.data) / 1024:.1f} KB), {self.fmt}, {mode}, method {self.method}, "
                 f"{s['width']}x{s['height']}, {s['frames']} frames, {s['fps']} fps avg", self.quality.line()]
        if self.budget_bytes:
            lines.append(f"target {self.budget_bytes / MB:.2f} MB: {'fits' if self.fits else 'DOES NOT FIT'} after {self.trials} trials")
        lines.extend(f"note: {n}" for n in self.notes)
        lines.extend(f"warning: {w}" for w in self.warnings)
        return "\n".join(lines)


def _durations_ms(durations: list[float]) -> list[int]:
    out: list[int] = []
    ideal, emitted = 0.0, 0
    for d in durations:
        ideal += d * 1000.0
        want = max(1, int(ideal + 0.5) - emitted)
        out.append(want)
        emitted += want
    return out


def encode_webp(clip: Clip, quality: int, method: int, lossless: bool, loop: int = 0) -> bytes:
    pics = [Image.fromarray(f, "RGB") for f in clip.frames]
    buf = io.BytesIO()
    pics[0].save(buf, format="WEBP", save_all=True, append_images=pics[1:], duration=_durations_ms(clip.durations), loop=loop,
                 quality=quality, method=method, lossless=lossless, minimize_size=method >= 4)
    return buf.getvalue()


def encode_apng(clip: Clip, compress_level: int = 9, loop: int = 0) -> bytes:
    pics = [Image.fromarray(f, "RGB") for f in clip.frames]
    buf = io.BytesIO()
    pics[0].save(buf, format="PNG", save_all=True, append_images=pics[1:], duration=_durations_ms(clip.durations), loop=loop,
                 compress_level=compress_level, optimize=compress_level >= 7)
    return buf.getvalue()


def _quality(clip: Clip, data: bytes) -> QualityReport:
    got = read_gif(data, browser_rule=False)
    return compare_sequences(clip.frames, clip.durations, got.frames, got.durations, sample=12)


def encode_animated(clip: Clip, fmt: str, quality: int = 80, method: int = 4, lossless: bool = False, dedupe_threshold: float = 0.0,
                    target_size_mb: float = 0.0, loop: int = 0, time_budget_s: float = 60.0, check: Check = check_interrupt) -> AnimResult:
    """Encode to WebP or APNG. With a target size on lossy WebP, binary-search the highest quality that fits."""
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}")
    slim, dropped = dedupe(clip, dedupe_threshold)
    notes = [f"de-duplication merged {dropped} frame(s)"] if dropped else []
    if fmt == "apng":
        if target_size_mb > 0:
            notes.append("APNG is lossless: the size budget is reported, not searched")
        data = encode_apng(slim, 9, loop)
        res = AnimResult(data, fmt, slim, _quality(clip, data), None, 9, True, notes=notes)
        if target_size_mb > 0:
            res.budget_bytes = int(target_size_mb * MB)
            res.fits = len(data) <= res.budget_bytes
            if not res.fits:
                res.warnings.append("APNG is over the budget; try WebP lossy or fewer/smaller frames")
        return res

    if target_size_mb <= 0 or lossless:
        data = encode_webp(slim, quality, method, lossless, loop)
        res = AnimResult(data, fmt, slim, _quality(clip, data), None if lossless else quality, method, lossless, 1, notes=notes)
        if target_size_mb > 0:
            res.budget_bytes = int(target_size_mb * MB)
            res.fits = len(data) <= res.budget_bytes
            if not res.fits:
                res.warnings.append("lossless WebP is over the budget; turn lossless off to search quality")
        return res

    budget = int(target_size_mb * MB)
    started = time.monotonic()
    lo, hi = 1, 100
    best: tuple[int, bytes] | None = None
    smallest: tuple[int, bytes] | None = None
    trials = 0
    while lo <= hi and time.monotonic() - started < time_budget_s:
        check()
        mid = (lo + hi) // 2
        data = encode_webp(slim, mid, method, False, loop)
        trials += 1
        if smallest is None or len(data) < len(smallest[1]):
            smallest = (mid, data)
        if len(data) <= budget:
            best = (mid, data)
            lo = mid + 1
        else:
            hi = mid - 1
    fits = best is not None
    q, data = best if best else (smallest if smallest else (1, encode_webp(slim, 1, method, False, loop)))
    res = AnimResult(data, fmt, slim, _quality(clip, data), q, method, False, trials, fits, budget, notes)
    if not fits:
        res.warnings.append(f"even quality {q} is over {budget / MB:.2f} MB; shrink the frames or trim the clip")
    return res
