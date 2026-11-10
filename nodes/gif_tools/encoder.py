"""GIF encoding: ffmpeg palette pipelines (global two-pass, per-frame) with a Pillow fallback, plus the "auto" choices."""
from __future__ import annotations

import math
import os
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

import numpy as np

from . import ffmpeg_gif as ff
from .frames import Clip, Frame, banding_risk, motion_stats, rescale, unique_color_ratio
from .gifio import encode_with_pillow, patch_gif_delays, read_delays_cs, read_gif, scan_gif
from .quality import compare_sequences
from .runtime import Check, check_interrupt
from .settings import PRESETS, Preset
from .timing import quantise_delays

RAW_NAME = "in.rgb"
PALETTE_NAME = "pal.png"
OUT_NAME = "out.gif"
RAW_FPS = 25.0  # nominal rate for the raw stream; real delays are patched in afterwards


@dataclass(frozen=True)
class EncodeParams:
    """Fully resolved settings: no "auto" left."""

    colors: int
    dither: str
    palette: str  # global_full | global_diff | per_frame
    transparency_opt: bool = True
    denoise: str = "off"
    loop: int = 0  # NETSCAPE value: 0 forever, -1 no extension, n repeats


@dataclass
class EncodeResult:
    data: bytes
    delays_cs: list[int]
    params: EncodeParams
    backend: str  # "ffmpeg" | "pillow"
    notes: list[str] = field(default_factory=list)

    @property
    def frames(self) -> int:
        return len(self.delays_cs)


def _write_raw(path: str, frames: Sequence[Frame]) -> None:
    with open(path, "wb") as fh:
        last: Frame | None = None
        blob = b""
        for f in frames:
            if f is not last:  # repeated frame objects (fps upsampling) reuse the encoded bytes
                blob = np.ascontiguousarray(f).tobytes()
                last = f
            fh.write(blob)


def encode_gif(clip: Clip, params: EncodeParams, timeout: float = ff.DEFAULT_TIMEOUT_S, check: Check = check_interrupt,
               use_gifsicle: bool = True) -> EncodeResult:
    """Encode a clip. Delays are quantised to whole centiseconds with error diffusion and patched into the file."""
    delays = quantise_delays(clip.durations)
    exe = ff.find_ffmpeg()
    notes: list[str] = []
    if exe is None:
        data = encode_with_pillow(clip.frames, delays, params.colors, params.dither if params.dither != "auto" else "floyd_steinberg",
                                  params.loop, per_frame=params.palette == "per_frame")
        notes.append("ffmpeg not found: used the Pillow encoder (single median-cut palette, no palette-aware dithering).")
        return EncodeResult(data, read_delays_cs(data), params, "pillow", notes)

    width, height = clip.size
    with ff.workdir() as tmp:
        _write_raw(os.path.join(tmp, RAW_NAME), clip.frames)
        check()
        if params.palette == "per_frame":
            argv = ff.per_frame_argv(exe, RAW_NAME, OUT_NAME, width, height, RAW_FPS, params.colors, params.dither,
                                     params.transparency_opt, params.loop, params.denoise)
            ff.run(argv, tmp, timeout, check)
        else:
            stats = "diff" if params.palette == "global_diff" else "full"
            ff.run(ff.palettegen_argv(exe, RAW_NAME, PALETTE_NAME, width, height, RAW_FPS, params.colors, stats,
                                      params.transparency_opt, params.denoise), tmp, timeout, check)
            ff.run(ff.paletteuse_argv(exe, RAW_NAME, PALETTE_NAME, OUT_NAME, width, height, RAW_FPS, params.colors,
                                      params.dither, params.transparency_opt, params.loop, params.denoise), tmp, timeout, check)
        out_path = os.path.join(tmp, OUT_NAME)
        gifsicle = ff.find_gifsicle() if use_gifsicle else None
        if gifsicle:
            try:
                ff.run(ff.gifsicle_argv(gifsicle, OUT_NAME, "opt.gif"), tmp, timeout, check)
                if os.path.getsize(os.path.join(tmp, "opt.gif")) < os.path.getsize(out_path):
                    out_path = os.path.join(tmp, "opt.gif")
                    notes.append("gifsicle -O3 shaved a few more bytes")
            except ff.FfmpegError as exc:
                notes.append(f"gifsicle skipped: {exc}")
        with open(out_path, "rb") as fh:
            raw = fh.read()
    frames_out = len(scan_gif(raw)[0])
    if frames_out != len(delays):
        raise ff.FfmpegError(f"encoder wrote {frames_out} frames, expected {len(delays)}")
    return EncodeResult(patch_gif_delays(raw, delays), delays, params, "ffmpeg", notes)


def naive_gif_bytes(clip: Clip, timeout: float = ff.DEFAULT_TIMEOUT_S, check: Check = check_interrupt) -> bytes | None:
    """The one-liner encode (`ffmpeg -i in out.gif`) of the same frames, size and rate; None without ffmpeg.
    This is the baseline compression ratios are quoted against."""
    exe = ff.find_ffmpeg()
    if exe is None:
        return None
    width, height = clip.size
    with ff.workdir() as tmp:
        _write_raw(os.path.join(tmp, RAW_NAME), clip.frames)
        fps = max(1.0, len(clip.frames) / max(clip.total, 1e-6))
        ff.run(ff.naive_argv(exe, RAW_NAME, OUT_NAME, width, height, min(fps, 50.0)), tmp, timeout, check)
        with open(os.path.join(tmp, OUT_NAME), "rb") as fh:
            return fh.read()


def decode_result(result: EncodeResult | bytes) -> tuple[list[Frame], list[float]]:
    data = result.data if isinstance(result, EncodeResult) else result
    g = read_gif(data)
    return g.frames, g.durations


def measure(clip: Clip, result: EncodeResult, sample: int = 12, max_side: int = 0) -> float:
    """Mean SSIM of the encoded GIF against the clip it came from (time-aligned, resized to the clip's frame size)."""
    frames, durations = decode_result(result)
    report = compare_sequences(clip.frames, clip.durations, frames, durations, sample=sample, with_psnr=False)
    return report.ssim_mean


# ------------------------------------------------------------------ "auto" resolution

def choose_palette(frames: Sequence[Frame]) -> str:
    """Pick a palette strategy from how the content moves. Scene cuts want their own palettes; localised motion
    over a steady scene suits statistics gathered only from changing pixels; everything else shares one full palette."""
    picks = [frames[i] for i in np.linspace(0, len(frames) - 1, num=min(40, len(frames)), dtype=int)] if len(frames) > 40 else list(frames)
    changed, cuts = motion_stats(picks)
    if cuts > 0.08:
        return "per_frame"
    if changed < 0.35:
        return "global_diff"
    return "global_full"


def _sample_clip(clip: Clip, max_frames: int = 14, max_side: int = 480) -> Clip:
    n = len(clip.frames)
    start = max(0, n // 2 - max_frames // 2)
    sub = Clip(clip.frames[start : start + max_frames], clip.durations[start : start + max_frames])
    w, h = sub.size
    return rescale(sub, max_side / max(w, h)) if max(w, h) > max_side else sub


def choose_dither(clip: Clip, base: EncodeParams, bias: str, timeout: float, check: Check) -> tuple[str, list[str]]:
    """Choose a dither by encoding a short, shrunken sample with each plausible candidate and scoring SSIM against size."""
    ratio = unique_color_ratio(clip.frames, base.colors)
    if ratio <= 1.0:
        return "none", ["dither: flat artwork fits the palette, none needed"]
    if ff.find_ffmpeg() is None:
        return "floyd_steinberg", []
    sample = _sample_clip(clip)
    results: list[tuple[str, float, int]] = []
    candidates = ["sierra2_4a", "bayer_5", "bayer_3"]
    if banding_risk(clip.frames) < 0.08:  # textured or noisy content hides banding; undithered is smaller and often scores best
        candidates.append("none")
    for cand in candidates:
        check()
        res = encode_gif(sample, replace(base, dither=cand), timeout, check, use_gifsicle=False)
        results.append((cand, measure(sample, res), len(res.data)))
    best_ssim = max(r[1] for r in results)
    min_size = min(r[2] for r in results)
    if bias == "quality":
        pick = max(results, key=lambda r: (round(r[1], 4), -r[2]))
    elif bias == "smallest":
        pick = min((r for r in results if r[1] >= best_ssim - 0.02), key=lambda r: r[2])
    else:
        pick = max(results, key=lambda r: r[1] - 0.03 * math.log2(r[2] / min_size))
    return pick[0], [f"dither auto: " + ", ".join(f"{n} ssim {s:.3f} {b // 1024}K" for n, s, b in results) + f" -> {pick[0]}"]


def resolve_params(
    clip: Clip,
    mode: str,
    palette: str = "auto",
    colors: int = 0,
    dither: str = "auto",
    denoise: str = "auto",
    transparency_opt: bool = True,
    loop: int = 0,
    timeout: float = ff.DEFAULT_TIMEOUT_S,
    check: Check = check_interrupt,
) -> tuple[EncodeParams, list[str]]:
    """Turn user choices (with "auto"/0 placeholders) into concrete encode settings; returns notes describing the picks."""
    preset: Preset = PRESETS[mode]
    notes: list[str] = []
    n_colors = colors or preset.colors
    pal = palette if palette != "auto" else choose_palette(clip.frames)
    if palette == "auto":
        notes.append(f"palette auto: {pal}")
    dn = denoise if denoise != "auto" else "off"
    base = EncodeParams(colors=n_colors, dither="sierra2_4a", palette=pal, transparency_opt=transparency_opt, denoise=dn, loop=loop)
    if dither == "auto":
        dither, dnotes = choose_dither(clip, base, preset.dither_bias, timeout, check)
        notes.extend(dnotes)
    base = replace(base, dither=dither)
    if denoise == "auto" and preset.denoise != "off" and ff.find_ffmpeg() is not None:
        base, dn_note = _maybe_denoise(clip, base, preset.denoise, timeout, check)
        notes.append(dn_note)
    return base, notes


def _maybe_denoise(clip: Clip, base: EncodeParams, level: str, timeout: float, check: Check) -> tuple[EncodeParams, str]:
    """Temporal denoising removes grain that GIF cannot compress, but on clean footage it only adds fuzz. Keep it only
    when a sample encode gets clearly smaller without a visible quality drop."""
    sample = _sample_clip(clip)
    plain = encode_gif(sample, base, timeout, check, use_gifsicle=False)
    smooth = encode_gif(sample, replace(base, denoise=level), timeout, check, use_gifsicle=False)
    q_plain, q_smooth = measure(sample, plain), measure(sample, smooth)
    keep = len(smooth.data) < len(plain.data) * 0.95 and q_plain - q_smooth <= 0.02
    verdict = f"denoise {level}: sample {len(plain.data) // 1024}K -> {len(smooth.data) // 1024}K, ssim {q_plain:.3f} -> {q_smooth:.3f}, {'kept' if keep else 'skipped'}"
    return (replace(base, denoise=level) if keep else base), verdict
