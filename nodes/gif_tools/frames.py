"""Frame-level helpers: sources (arrays, video files), trim/speed/fps resampling, crop, resize and de-duplication."""
from __future__ import annotations

import bisect
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from .runtime import Check, check_interrupt
from .settings import MAX_DIMENSION, MAX_OUTPUT_FRAMES

Frame = NDArray[np.uint8]
Transform = Callable[[Frame], Frame]

_PIL_FILTERS: dict[str, Image.Resampling] = {
    "lanczos": Image.Resampling.LANCZOS,
    "bicubic": Image.Resampling.BICUBIC,
    "bilinear": Image.Resampling.BILINEAR,
    "box": Image.Resampling.BOX,
    "nearest": Image.Resampling.NEAREST,
}


@dataclass
class Clip:
    """Decoded RGB frames with a per-frame duration in seconds."""

    frames: list[Frame]
    durations: list[float]

    def __post_init__(self) -> None:
        if len(self.frames) != len(self.durations):
            raise ValueError("frames and durations differ in length")

    @property
    def size(self) -> tuple[int, int]:
        h, w = self.frames[0].shape[:2]
        return w, h

    @property
    def total(self) -> float:
        return float(sum(self.durations))


@dataclass
class FrameSource:
    """Where frames come from. `starts` are presentation times (s); `fetch` decodes just the wanted indices."""

    starts: list[float]
    end: float
    width: int
    height: int
    fetch: Callable[[Sequence[int], Transform], dict[int, Frame]]

    @property
    def native_fps(self) -> float:
        n = len(self.starts)
        span = self.end - self.starts[0]
        return n / span if n and span > 0 else 0.0


@dataclass(frozen=True)
class PrepOptions:
    start: float = 0.0
    end: float = 0.0  # 0 = to the end
    fps: float = 0.0  # 0 = keep the source timing
    speed: float = 1.0
    max_width: int = 0
    max_height: int = 0
    resize_filter: str = "lanczos"
    crop: tuple[int, int, int, int] = (0, 0, 0, 0)  # left, top, right, bottom in source pixels


# ------------------------------------------------------------------ geometry

def crop_box(width: int, height: int, crop: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    left, top, right, bottom = crop
    if min(crop) < 0:
        raise ValueError("crop values must be >= 0")
    x1, y1, x2, y2 = left, top, width - right, height - bottom
    if x2 - x1 < 2 or y2 - y1 < 2:
        raise ValueError(f"crop leaves nothing of the {width}x{height} frame")
    return x1, y1, x2, y2


def fit_size(width: int, height: int, max_w: int, max_h: int) -> tuple[int, int]:
    """Scale down to fit max_w x max_h (0 = unlimited), keeping aspect, never upscaling."""
    if not (0 <= max_w <= MAX_DIMENSION and 0 <= max_h <= MAX_DIMENSION):
        raise ValueError("max width/height out of range")
    scale = 1.0
    if max_w:
        scale = min(scale, max_w / width)
    if max_h:
        scale = min(scale, max_h / height)
    return max(2, round(width * scale)), max(2, round(height * scale))


def resize_frame(frame: Frame, width: int, height: int, method: str = "lanczos") -> Frame:
    if frame.shape[1] == width and frame.shape[0] == height:
        return frame
    img = Image.fromarray(frame, "RGB").resize((width, height), _PIL_FILTERS[method])
    return np.asarray(img, dtype=np.uint8)


def make_transform(src_w: int, src_h: int, opts: PrepOptions) -> tuple[Transform, tuple[int, int]]:
    """Crop then resize, returning the per-frame transform and the output (width, height)."""
    x1, y1, x2, y2 = crop_box(src_w, src_h, opts.crop)
    out_w, out_h = fit_size(x2 - x1, y2 - y1, opts.max_width, opts.max_height)
    cropped = (x1, y1, x2, y2) != (0, 0, src_w, src_h)

    def apply(frame: Frame) -> Frame:
        if cropped:
            frame = frame[y1:y2, x1:x2]
        return resize_frame(np.ascontiguousarray(frame), out_w, out_h, opts.resize_filter)

    return apply, (out_w, out_h)


# ------------------------------------------------------------------ timeline

def plan_resample(starts: Sequence[float], end: float, opts: PrepOptions) -> tuple[list[int], list[float]]:
    """Which source frame shows at each output instant, plus each output frame's duration (seconds, post-speed)."""
    if opts.speed <= 0:
        raise ValueError("speed must be positive")
    t0 = max(0.0, opts.start)
    t1 = end if opts.end <= 0 else min(opts.end, end)
    if t1 <= t0:
        raise ValueError(f"trim window is empty (start {t0:g}s, end {t1:g}s)")
    if opts.fps > 0:
        n = max(1, int((t1 - t0) / opts.speed * opts.fps + 1e-9))
        if n > MAX_OUTPUT_FRAMES:
            raise ValueError(f"{n} output frames is over the {MAX_OUTPUT_FRAMES} frame limit; lower fps or trim")
        picks: list[int] = []
        j = 0
        for k in range(n):
            t = t0 + k * opts.speed / opts.fps
            while j + 1 < len(starts) and starts[j + 1] <= t + 1e-6:
                j += 1
            picks.append(j)
        return picks, [1.0 / opts.fps] * n
    # native timing: every source frame whose display interval overlaps the window
    picks, durations = [], []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else end
        lo, hi = max(s, t0), min(e, t1)
        if hi - lo > 1e-9:
            picks.append(i)
            durations.append((hi - lo) / opts.speed)
    if not picks:
        raise ValueError("trim window contains no frames")
    if len(picks) > MAX_OUTPUT_FRAMES:
        raise ValueError(f"{len(picks)} frames is over the {MAX_OUTPUT_FRAMES} frame limit; trim or set an fps")
    return picks, durations


def make_clip(source: FrameSource, opts: PrepOptions, check: Check = check_interrupt) -> Clip:
    picks, durations = plan_resample(source.starts, source.end, opts)
    transform, _ = make_transform(source.width, source.height, opts)
    check()
    got = source.fetch(sorted(set(picks)), transform)
    return Clip([got[i] for i in picks], durations)


def resample(clip: Clip, fps: float) -> Clip:
    """Re-time a clip to a constant rate by showing, at each tick, the frame that was on screen."""
    if fps <= 0:
        raise ValueError("fps must be positive")
    starts = [0.0]
    for d in clip.durations[:-1]:
        starts.append(starts[-1] + d)
    n = max(1, int(clip.total * fps + 1e-9))
    picks = [min(len(starts) - 1, max(0, bisect.bisect_right(starts, k / fps + 1e-6) - 1)) for k in range(n)]
    return Clip([clip.frames[i] for i in picks], [1.0 / fps] * n)


def rescale(clip: Clip, scale: float, method: str = "lanczos") -> Clip:
    if scale >= 0.999:
        return clip
    w, h = clip.size
    nw, nh = max(2, round(w * scale)), max(2, round(h * scale))
    cache: dict[int, Frame] = {}
    frames: list[Frame] = []
    for f in clip.frames:  # repeated frames (fps upsampling) share one resize
        key = id(f)
        if key not in cache:
            cache[key] = resize_frame(f, nw, nh, method)
        frames.append(cache[key])
    return Clip(frames, list(clip.durations))


# ------------------------------------------------------------------ de-duplication

def _signature(frame: Frame, max_side: int = 96) -> NDArray[np.float32]:
    """A small block-averaged copy used to compare frames cheaply."""
    h, w = frame.shape[:2]
    block = max(1, max(h, w) // max_side)
    hh, ww = (h // block) * block, (w // block) * block
    view = frame[:hh, :ww].astype(np.float32).reshape(hh // block, block, ww // block, block, 3)
    return view.mean(axis=(1, 3))


def dedupe(clip: Clip, threshold: float) -> tuple[Clip, int]:
    """Drop frames that barely differ from the last kept frame, adding their time to it.

    `threshold` is the mean absolute difference on a 0..255 scale; 0 only drops byte-identical frames; negative
    disables. Returns the new clip and the number of dropped frames. Comparing with the last *kept* frame stops slow
    fades from being swallowed one tiny step at a time.
    """
    if threshold < 0 or len(clip.frames) < 2:
        return clip, 0
    kept_frames = [clip.frames[0]]
    kept_durs = [clip.durations[0]]
    ref_sig = _signature(clip.frames[0]) if threshold > 0 else None
    for frame, dur in zip(clip.frames[1:], clip.durations[1:]):
        if threshold == 0:
            same = frame is kept_frames[-1] or np.array_equal(frame, kept_frames[-1])
        else:
            sig = _signature(frame)
            same = float(np.abs(sig - ref_sig).mean()) <= threshold
        if same:
            kept_durs[-1] += dur
            continue
        kept_frames.append(frame)
        kept_durs.append(dur)
        if threshold > 0:
            ref_sig = sig
    return Clip(kept_frames, kept_durs), len(clip.frames) - len(kept_frames)


def motion_stats(frames: Sequence[Frame]) -> tuple[float, float]:
    """(changed-pixel fraction between neighbours, share of neighbour pairs that look like a scene cut)."""
    if len(frames) < 2:
        return 0.0, 0.0
    sigs = [_signature(f, 64) for f in frames]
    changed, cuts = [], 0
    for a, b in zip(sigs, sigs[1:]):
        diff = np.abs(a - b).mean(axis=2)
        changed.append(float((diff > 6.0).mean()))
        if float(diff.mean()) > 40.0:
            cuts += 1
    return float(np.mean(changed)), cuts / (len(sigs) - 1)


def unique_color_ratio(frames: Sequence[Frame], colors: int) -> float:
    """Distinct 6-bit-per-channel colours across a few frames divided by the palette size; <= 1 means flat artwork."""
    if not frames:
        return 0.0
    picks = [frames[i] for i in np.linspace(0, len(frames) - 1, num=min(4, len(frames)), dtype=int)]
    seen: set[int] = set()
    for f in picks:
        small = f[:: max(1, f.shape[0] // 240), :: max(1, f.shape[1] // 240)] >> 2
        packed = (small[..., 0].astype(np.int32) << 12) | (small[..., 1].astype(np.int32) << 6) | small[..., 2]
        seen.update(np.unique(packed).tolist())
    return len(seen) / max(1, colors)


def banding_risk(frames: Sequence[Frame]) -> float:
    """Share of 8x8 blocks that are smooth gradients (tiny but non-zero variation). Undithered palettes band there."""
    if not frames:
        return 0.0
    f = frames[len(frames) // 2]
    h, w = (f.shape[0] // 8) * 8, (f.shape[1] // 8) * 8
    if h < 8 or w < 8:
        return 0.0
    luma = f[:h, :w].astype(np.float32).mean(axis=2).reshape(h // 8, 8, w // 8, 8)
    spread = luma.max(axis=(1, 3)) - luma.min(axis=(1, 3))
    return float(((spread >= 2.0) & (spread <= 24.0)).mean())


# ------------------------------------------------------------------ sources

def source_from_arrays(frames: Sequence[Frame], fps: float) -> FrameSource:
    if not frames:
        raise ValueError("no frames given")
    if fps <= 0:
        raise ValueError("source fps must be positive")
    h, w = frames[0].shape[:2]
    starts = [i / fps for i in range(len(frames))]

    def fetch(indices: Sequence[int], transform: Transform) -> dict[int, Frame]:
        return {i: transform(frames[i]) for i in indices}

    return FrameSource(starts, len(frames) / fps, w, h, fetch)


def source_from_timed_arrays(frames: Sequence[Frame], durations: Sequence[float]) -> FrameSource:
    """Frames with their own durations (decoded GIFs)."""
    if not frames or len(frames) != len(durations):
        raise ValueError("frames and durations must be non-empty and equal in length")
    starts = [0.0]
    for d in durations[:-1]:
        starts.append(starts[-1] + d)
    h, w = frames[0].shape[:2]

    def fetch(indices: Sequence[int], transform: Transform) -> dict[int, Frame]:
        return {i: transform(frames[i]) for i in indices}

    return FrameSource(starts, starts[-1] + durations[-1], w, h, fetch)


def source_from_video_file(path: str, window: tuple[float, float] = (0.0, 0.0)) -> FrameSource:
    """Stream a video file with PyAV. `window` is a (start, duration) pre-trim from ComfyUI's VIDEO type (0 = none)."""
    import av  # imported late: only needed for video input

    with av.open(path) as container:
        stream = container.streams.video[0]
        base = float(stream.time_base) if stream.time_base else 0.0
        ts: list[float] = []
        for packet in container.demux(stream):
            if packet.pts is not None and base:
                ts.append(float(packet.pts) * base)
        width, height = stream.codec_context.width, stream.codec_context.height
        avg = float(stream.average_rate) if stream.average_rate else 0.0
        duration = float(container.duration) / 1_000_000 if container.duration else 0.0
    ts.sort()
    if not ts:
        raise ValueError("video has no decodable frames")
    t_first = ts[0]
    starts = [t - t_first for t in ts]
    last_len = 1.0 / avg if avg > 0 else (starts[-1] - starts[-2] if len(starts) > 1 else 0.04)
    end = max(starts[-1] + last_len, duration if duration > starts[-1] else 0.0)

    w_start, w_len = window
    keep = [i for i, s in enumerate(starts) if s >= w_start - 1e-6 and (w_len <= 0 or s < w_start + w_len - 1e-6)]
    if not keep:
        raise ValueError("the video's trim window contains no frames")
    offset = starts[keep[0]]
    sub_starts = [starts[i] - offset for i in keep]
    sub_end = (end - offset) if w_len <= 0 else min(end - offset, w_len)
    base_index = keep[0]

    def fetch(indices: Sequence[int], transform: Transform) -> dict[int, Frame]:
        want = {base_index + i: i for i in indices}
        out: dict[int, Frame] = {}
        with av.open(path) as container:
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"
            for pos, frame in enumerate(container.decode(stream)):
                if pos > max(want):
                    break
                hit = want.get(pos)
                if hit is not None:
                    out[hit] = transform(frame.to_ndarray(format="rgb24"))
        missing = [i for i in indices if i not in out]
        if missing:  # decoder yielded fewer frames than packets: reuse the closest decoded one
            have = sorted(out)
            if not have:
                raise ValueError("could not decode any video frames")
            for i in missing:
                out[i] = out[min(have, key=lambda h: abs(h - i))]
        return out

    return FrameSource(sub_starts, sub_end, width, height, fetch)
