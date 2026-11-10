"""Deterministic synthetic clips for the GIF tests."""
from __future__ import annotations

import numpy as np
import pytest

from gif_tools import ffmpeg_gif
from gif_tools.frames import Clip, Frame

needs_ffmpeg = pytest.mark.skipif(ffmpeg_gif.find_ffmpeg() is None, reason="ffmpeg not available")


def _gradient(w: int, h: int, phase: float) -> Frame:
    x = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    r = 0.5 + 0.5 * np.sin(2 * np.pi * (x + phase))
    g = 0.5 + 0.5 * np.sin(2 * np.pi * (y + phase * 0.7) + 2.0)
    b = 0.5 + 0.5 * np.sin(2 * np.pi * (x * 0.6 + y * 0.6 - phase) + 4.0)
    return (np.stack(np.broadcast_arrays(r, g, b), axis=-1) * 255).astype(np.uint8)


def gradient_clip(n: int = 20, w: int = 160, h: int = 120, fps: float = 20.0) -> Clip:
    return Clip([_gradient(w, h, i / n * 0.5) for i in range(n)], [1.0 / fps] * n)


def noise_clip(n: int = 16, w: int = 128, h: int = 96, fps: float = 20.0, seed: int = 7) -> Clip:
    rng = np.random.default_rng(seed)
    return Clip([rng.integers(0, 256, (h, w, 3), dtype=np.uint8) for _ in range(n)], [1.0 / fps] * n)


def motion_clip(n: int = 24, w: int = 160, h: int = 120, fps: float = 20.0) -> Clip:
    base = _gradient(w, h, 0.0)
    frames: list[Frame] = []
    for i in range(n):
        f = base.copy()
        x = 8 + int((w - 40) * i / max(1, n - 1))
        f[40:70, x : x + 24] = (230, 40, 40)
        frames.append(f)
    return Clip(frames, [1.0 / fps] * n)


def static_clip(n: int = 30, w: int = 160, h: int = 120, fps: float = 20.0) -> Clip:
    """A still image with a brief blink: most consecutive frames are byte-identical."""
    a = _gradient(w, h, 0.0)
    b = a.copy()
    b[10:30, 10:50] = 255
    frames = [a] * (n // 2) + [b] * 2 + [a.copy() for _ in range(n - n // 2 - 2)]
    return Clip(frames, [1.0 / fps] * n)


def flat_clip(n: int = 6, w: int = 64, h: int = 48) -> Clip:
    """Few saturated colours: a GIF can represent it exactly."""
    palette = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
    frames: list[Frame] = []
    for i in range(n):
        f = np.zeros((h, w, 3), dtype=np.uint8)
        f[:, : w // 2] = palette[i % 4]
        f[:, w // 2 :] = palette[(i + 1) % 4]
        f[h // 3 : 2 * h // 3, w // 4 : 3 * w // 4] = (255, 255, 255)
        frames.append(f)
    return Clip(frames, [0.1] * n)


def noisy_static_clip(n: int = 30, w: int = 160, h: int = 120, fps: float = 20.0, seed: int = 11) -> Clip:
    """A still scene with sensor-style noise of +-2 levels per frame: no two frames are byte-identical."""
    rng = np.random.default_rng(seed)
    base = _gradient(w, h, 0.0).astype(np.int16)
    return Clip([np.clip(base + rng.integers(-2, 3, base.shape), 0, 255).astype(np.uint8) for _ in range(n)], [1.0 / fps] * n)
