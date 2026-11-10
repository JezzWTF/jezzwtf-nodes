"""The optimisation engine: preset modes and the budget-driven target-size search. Pure Python."""
from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from . import ffmpeg_gif as ff
from .encoder import EncodeResult, choose_palette, decode_result, encode_gif, naive_gif_bytes, resolve_params
from .frames import Clip, dedupe, rescale, resample
from .quality import QualityReport, compare_sequences
from .runtime import Check, check_interrupt
from .settings import MODES, PRESETS, check_choice
from .timing import cs_to_fps, even_fps

ProgressFn = Callable[[int, int], None]

MB = 1024 * 1024
MIN_SCALE = 0.15
AIM = 0.96           # aim each trial at this fraction of the budget
CONVERGED = 0.88     # a fitting trial at least this full counts as converged for its family
SIZE_EXPONENT = 1.9  # GIF size grows a little slower than scale squared
FPS_FACTORS = (1.0, 0.8, 0.67, 0.5)
COLOR_STEPS = (256, 192, 128, 96, 64, 48, 32)
MIN_SEARCH_FPS = 5.0


@dataclass(frozen=True)
class OptimiseRequest:
    mode: str = "balanced"
    palette: str = "auto"
    colors: int = 0                 # 0 = by mode
    dither: str = "auto"
    dedupe_threshold: float = -1.0  # < 0 = by mode
    transparency_opt: bool = True
    denoise: str = "auto"
    loop: int = 0                   # NETSCAPE loop value
    target_size_mb: float = 0.0
    max_trials: int = 10
    time_budget_s: float = 120.0
    compare_naive: bool = True
    timeout_s: float = ff.DEFAULT_TIMEOUT_S


@dataclass
class Trial:
    scale: float
    fps: float
    colors: int
    dither: str
    bytes: int
    ssim: float
    fits: bool


@dataclass
class OptimiseResult:
    data: bytes
    encode: EncodeResult
    clip: Clip                      # the frames actually encoded (after scale/fps/dedupe)
    reference: Clip                 # what quality is measured against
    quality: QualityReport
    dropped: int = 0
    naive_bytes: int | None = None
    naive_ssim: float | None = None
    scale: float = 1.0
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    budget_bytes: int = 0
    fits: bool | None = None
    trials: list[Trial] = field(default_factory=list)

    @property
    def width(self) -> int:
        return self.clip.size[0]

    @property
    def height(self) -> int:
        return self.clip.size[1]

    @property
    def fps(self) -> float:
        return cs_to_fps(self.encode.delays_cs)

    def stats(self) -> dict[str, float | int | str | bool | None]:
        ratio = (self.naive_bytes / len(self.data)) if self.naive_bytes else None
        saved = (1 - len(self.data) / self.naive_bytes) * 100 if self.naive_bytes else None
        return {
            "bytes": len(self.data), "frames": self.encode.frames, "fps": round(self.fps, 2), "colors": self.encode.params.colors,
            "dither": self.encode.params.dither, "palette": self.encode.params.palette, "width": self.width, "height": self.height,
            "ssim": round(self.quality.ssim_mean, 4), "ssim_min": round(self.quality.ssim_min, 4), "psnr": round(self.quality.psnr_mean, 2),
            "naive_bytes": self.naive_bytes, "naive_ssim": None if self.naive_ssim is None else round(self.naive_ssim, 4),
            "ratio_vs_naive": None if ratio is None else round(ratio, 2), "saved_pct": None if saved is None else round(saved, 1),
            "budget_bytes": self.budget_bytes or None, "fits": self.fits, "backend": self.encode.backend,
        }

    def report(self) -> str:
        s = self.stats()
        lines = [
            f"{len(self.data):,} bytes ({len(self.data) / 1024:.1f} KB), {s['width']}x{s['height']}, {s['frames']} frames, "
            f"{s['fps']} fps avg, {s['colors']} colors, dither {s['dither']}, palette {s['palette']}, encoder {s['backend']}",
            self.quality.line(),
        ]
        if self.dropped:
            lines.append(f"de-duplication merged {self.dropped} near-identical frame(s) into their neighbours")
        if self.naive_bytes:
            nq = f", SSIM {self.naive_ssim:.4f}" if self.naive_ssim is not None else ""
            lines.append(f"naive single-pass GIF of the same size and rate: {self.naive_bytes:,} bytes{nq}; "
                         f"ratio {self.naive_bytes / len(self.data):.2f}x ({s['saved_pct']}% {'smaller' if (s['saved_pct'] or 0) >= 0 else 'larger'})")
        if self.budget_bytes:
            lines.append(f"target {self.budget_bytes / MB:.2f} MB: {'fits' if self.fits else 'DOES NOT FIT'} "
                         f"({len(self.data) / self.budget_bytes * 100:.0f}% of budget, scale {self.scale:.2f}, {len(self.trials)} trials)")
        lines.extend(f"note: {n}" for n in self.notes)
        lines.extend(f"warning: {w}" for w in self.warnings)
        return "\n".join(lines)


# ------------------------------------------------------------------ presets

def optimise(clip: Clip, req: OptimiseRequest, progress: ProgressFn | None = None, check: Check = check_interrupt) -> OptimiseResult:
    check_choice("mode", req.mode, MODES)
    if req.mode == "target_size":
        if req.target_size_mb <= 0:
            raise ValueError("target_size mode needs target_size_mb > 0")
        return _target_search(clip, req, progress, check)
    preset = PRESETS[req.mode]
    step = progress or (lambda *_: None)
    step(0, 3)
    threshold = req.dedupe_threshold if req.dedupe_threshold >= 0 else preset.dedupe_threshold
    slim, dropped = dedupe(clip, threshold)
    params, notes = resolve_params(slim, req.mode, req.palette, req.colors, req.dither, req.denoise, req.transparency_opt, req.loop,
                                   req.timeout_s, check)
    step(1, 3)
    enc = encode_gif(slim, params, req.timeout_s, check)
    step(2, 3)
    result = _finish(clip, slim, clip, enc, dropped, notes, req, check)
    step(3, 3)
    return result


def _finish(reference: Clip, encoded: Clip, naive_source: Clip, enc: EncodeResult, dropped: int, notes: list[str],
            req: OptimiseRequest, check: Check, scale: float = 1.0) -> OptimiseResult:
    """Measure the encode against the reference and, if asked, against a naive one-liner GIF of the same pixels and size."""
    frames, durations = decode_result(enc)
    quality = compare_sequences(reference.frames, reference.durations, frames, durations, sample=16)
    result = OptimiseResult(enc.data, enc, encoded, reference, quality, dropped=dropped, scale=scale, notes=[*notes, *enc.notes])
    if not req.compare_naive:
        return result
    check()
    if ff.find_ffmpeg() is None:
        result.warnings.append("ffmpeg not found: Pillow encoder used, no naive baseline available")
        return result
    try:
        naive = naive_gif_bytes(naive_source, req.timeout_s, check)
    except ff.FfmpegError as exc:
        result.warnings.append(f"naive baseline failed: {exc}")
        return result
    if naive:
        result.naive_bytes = len(naive)
        n_frames, n_durs = decode_result(naive)
        result.naive_ssim = compare_sequences(reference.frames, reference.durations, n_frames, n_durs, sample=16, with_psnr=False).ssim_mean
    return result


# ------------------------------------------------------------------ target size

_COLOR_COST = {c: (math.log2(c) / 8.0) ** 0.6 for c in COLOR_STEPS}


def _unit_cost(fps: float, colors: int, base_fps: float) -> float:
    """Relative bytes of a setting at scale 1 (the part of the size model that is not resolution)."""
    return (fps / base_fps) ** 0.85 * _COLOR_COST[colors]


def _prior(scale: float, fps: float, colors: int, base_fps: float) -> float:
    """Rough perceived quality of a setting (higher is better): resolution matters most, then smoothness, then colours."""
    return scale**0.8 * (fps / base_fps) ** 0.45 * (math.log2(colors) / 8.0) ** 1.5


def _variant(clip: Clip, scale: float, fps: float, base_fps: float, threshold: float) -> tuple[Clip, int]:
    c = clip if abs(fps - base_fps) < 1e-6 else resample(clip, fps)
    c = rescale(c, scale)
    return dedupe(c, threshold)


Family = tuple[float, int, str]  # fps, colours, dither: everything except resolution


def _target_search(clip: Clip, req: OptimiseRequest, progress: ProgressFn | None, check: Check) -> OptimiseResult:
    """Find the best-looking encode under a byte budget.

    Settings split into a resolution scale and a "family" (fps, colours, dither). Size is close to a power law in scale
    within a family, so each family is solved for the scale that lands just under budget, and the families that should
    look best at their solved scale are tried first. Measured SSIM (against the full-quality clip, time-aligned and
    resized) then picks the winner among the encodes that fit.
    """
    budget = int(req.target_size_mb * MB)
    started = time.monotonic()
    max_trials = max(2, req.max_trials)
    step = progress or (lambda *_: None)
    base_fps = len(clip.frames) / max(clip.total, 1e-6)
    threshold = req.dedupe_threshold if req.dedupe_threshold >= 0 else PRESETS["target_size"].dedupe_threshold

    first, _ = dedupe(clip, threshold)
    params0, notes = resolve_params(first, "target_size", req.palette, 256 if req.colors == 0 else req.colors, req.dither, req.denoise,
                                    req.transparency_opt, req.loop, req.timeout_s, check)
    if req.palette == "auto":
        params0 = replace(params0, palette=choose_palette(clip.frames))
    top_colors = max((c for c in COLOR_STEPS if c <= params0.colors), default=COLOR_STEPS[-1])
    fps_options = sorted({round(base_fps, 3)} | {round(even_fps(base_fps * f), 3) for f in FPS_FACTORS[1:] if base_fps * f >= MIN_SEARCH_FPS}, reverse=True)
    colour_options = [c for c in dict.fromkeys((top_colors, 128, 64, 32)) if c <= top_colors]
    families: list[Family] = [(f, c, params0.dither) for f in fps_options for c in colour_options]

    trials: list[Trial] = []
    outputs: dict[tuple[float, float, int, str], tuple[EncodeResult, Clip, int]] = {}
    by_family: dict[Family, list[Trial]] = {fam: [] for fam in families}

    def run_trial(fam: Family, scale: float) -> Trial:
        scale = round(min(1.0, max(MIN_SCALE, scale)), 3)
        fps, colors, dither = fam
        variant, dropped = _variant(clip, scale, fps, base_fps, threshold)
        enc = encode_gif(variant, replace(params0, colors=colors, dither=dither), req.timeout_s, check)
        frames, durations = decode_result(enc)
        q = compare_sequences(clip.frames, clip.durations, frames, durations, sample=8, with_psnr=False)
        trial = Trial(scale, fps, colors, dither, len(enc.data), q.ssim_mean, len(enc.data) <= budget)
        trials.append(trial)
        by_family[fam].append(trial)
        outputs[(scale, fps, colors, dither)] = (enc, variant, dropped)
        step(len(trials), max_trials + 1)
        return trial

    def solve_scale(fam: Family) -> float:
        """The scale at which this family should land at AIM x budget, from its own measurements when it has any."""
        done = by_family[fam]
        if done:
            ref = min(done, key=lambda t: abs(math.log(t.bytes / (AIM * budget))))
            return ref.scale * (AIM * budget / ref.bytes) ** (1.0 / SIZE_EXPONENT)
        anchor = trials[-1]
        scale_one = anchor.bytes / (anchor.scale**SIZE_EXPONENT * _unit_cost(anchor.fps, anchor.colors, base_fps))
        return (AIM * budget / (scale_one * _unit_cost(fam[0], fam[1], base_fps))) ** (1.0 / SIZE_EXPONENT)

    run_trial(families[0], 1.0)
    while len(trials) < max_trials and time.monotonic() - started < req.time_budget_s:
        check()
        fitting = [t for t in trials if t.fits]
        best_prior = max((_prior(t.scale, t.fps, t.colors, base_fps) for t in fitting), default=0.0)
        options: list[tuple[float, Family, float]] = []
        for fam in families:
            done = by_family[fam]
            if len(done) >= 3 or any(t.fits and (t.bytes >= CONVERGED * budget or t.scale >= 0.999) for t in done):
                continue  # already as good as this family gets
            scale = min(solve_scale(fam), 1.0)
            if scale < MIN_SCALE or any(abs(scale - t.scale) < 0.012 for t in done):
                continue
            prior = _prior(scale, fam[0], fam[1], base_fps)
            if fitting and prior <= best_prior * 1.003:
                continue  # cannot beat what already fits
            options.append((prior, fam, scale))
        if not options:
            break
        _, fam, scale = max(options, key=lambda o: o[0])
        run_trial(fam, scale)

    fitting_trials = [t for t in trials if t.fits]
    warnings: list[str] = []
    if fitting_trials:
        chosen = max(fitting_trials, key=lambda t: (round(t.ssim, 4), t.bytes))
        fits = True
    else:
        chosen = min(trials, key=lambda t: t.bytes)
        fits = False
        warnings.append(f"no trial fit {budget / MB:.2f} MB within {len(trials)} trials; returning the smallest ({chosen.bytes / MB:.2f} MB). "
                        "Raise the budget, shorten or trim the clip, or lower fps and size.")
    if time.monotonic() - started >= req.time_budget_s:
        warnings.append(f"time budget of {req.time_budget_s:g}s reached after {len(trials)} trials")
    enc, variant, dropped = outputs[(chosen.scale, chosen.fps, chosen.colors, chosen.dither)]
    notes.append(f"target search chose scale {chosen.scale:.2f}, {chosen.fps:g} fps, {chosen.colors} colors, dither {chosen.dither} "
                 f"from {len(trials)} trials")
    naive_source, _ = _variant(clip, chosen.scale, chosen.fps, base_fps, -1.0)
    result = _finish(clip, variant, naive_source, enc, dropped, notes, req, check, scale=chosen.scale)
    result.warnings.extend(warnings)
    result.budget_bytes = budget
    result.fits = fits
    result.trials = trials
    step(max_trials + 1, max_trials + 1)
    return result
