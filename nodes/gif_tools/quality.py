"""Quality metrics: SSIM (luma, 7x7 uniform window, matching scikit-image defaults) and PSNR, plus time-aligned
comparison of two frame sequences that may differ in size, frame count and timing."""
from __future__ import annotations

import bisect
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from .frames import Frame, resize_frame

_WIN = 7
_C1 = (0.01 * 255) ** 2
_C2 = (0.03 * 255) ** 2


def _luma(frame: Frame) -> NDArray[np.float32]:
    f = frame.astype(np.float32)
    return f[..., 0] * 0.299 + f[..., 1] * 0.587 + f[..., 2] * 0.114


def _box_mean(a: NDArray[np.float64], win: int) -> NDArray[np.float64]:
    """Mean over every win x win window that fits ("valid" mode), via an integral image."""
    c = np.zeros((a.shape[0] + 1, a.shape[1] + 1), dtype=np.float64)
    np.cumsum(np.cumsum(a, axis=0), axis=1, out=c[1:, 1:])
    s = c[win:, win:] - c[:-win, win:] - c[win:, :-win] + c[:-win, :-win]
    return s / (win * win)


def ssim_gray(a: NDArray[np.float32], b: NDArray[np.float32]) -> float:
    if a.shape != b.shape:
        raise ValueError("ssim needs equally sized images")
    if min(a.shape) < _WIN:
        return 1.0 if np.array_equal(a, b) else float(1.0 - min(1.0, np.abs(a - b).mean() / 255.0))
    x, y = a.astype(np.float64), b.astype(np.float64)
    ux, uy = _box_mean(x, _WIN), _box_mean(y, _WIN)
    n = _WIN * _WIN
    cov_norm = n / (n - 1)
    vx = cov_norm * (_box_mean(x * x, _WIN) - ux * ux)
    vy = cov_norm * (_box_mean(y * y, _WIN) - uy * uy)
    vxy = cov_norm * (_box_mean(x * y, _WIN) - ux * uy)
    s = ((2 * ux * uy + _C1) * (2 * vxy + _C2)) / ((ux * ux + uy * uy + _C1) * (vx + vy + _C2))
    return float(s.mean())


def _downscale_for_metric(frame: Frame, max_side: int) -> Frame:
    h, w = frame.shape[:2]
    if max(h, w) <= max_side:
        return frame
    k = max_side / max(h, w)
    return np.asarray(Image.fromarray(frame, "RGB").resize((max(8, round(w * k)), max(8, round(h * k))), Image.Resampling.BOX), dtype=np.uint8)


def frame_ssim(a: Frame, b: Frame, max_side: int = 480) -> float:
    """SSIM on luma, both frames brought to a common size (b is resized to a's if needed)."""
    if a.shape != b.shape:
        b = resize_frame(b, a.shape[1], a.shape[0], "bicubic")
    return ssim_gray(_luma(_downscale_for_metric(a, max_side)), _luma(_downscale_for_metric(b, max_side)))


def frame_psnr(a: Frame, b: Frame) -> float:
    if a.shape != b.shape:
        b = resize_frame(b, a.shape[1], a.shape[0], "bicubic")
    mse = float(np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2))
    return 99.0 if mse <= 1e-9 else min(99.0, 10.0 * math.log10(255.0**2 / mse))


@dataclass(frozen=True)
class QualityReport:
    ssim_mean: float
    ssim_min: float
    ssim_p5: float
    psnr_mean: float
    worst_index: int
    frames_compared: int

    def line(self) -> str:
        return (
            f"SSIM mean {self.ssim_mean:.4f}, min {self.ssim_min:.4f} (frame {self.worst_index}), p5 {self.ssim_p5:.4f}; "
            f"PSNR mean {self.psnr_mean:.2f} dB over {self.frames_compared} frames"
        )


def _starts(durations: Sequence[float]) -> list[float]:
    out = [0.0]
    for d in durations[:-1]:
        out.append(out[-1] + d)
    return out


def align(ref_durations: Sequence[float], cand_durations: Sequence[float]) -> list[int]:
    """For each reference frame, the index of the candidate frame on screen at that frame's midpoint."""
    r_starts, c_starts = _starts(ref_durations), _starts(cand_durations)
    picks = []
    for s, d in zip(r_starts, ref_durations):
        t = s + d * 0.5
        picks.append(min(len(c_starts) - 1, max(0, bisect.bisect_right(c_starts, t) - 1)))
    return picks


def compare_sequences(
    ref: Sequence[Frame],
    ref_durations: Sequence[float],
    cand: Sequence[Frame],
    cand_durations: Sequence[float],
    sample: int = 16,
    with_psnr: bool = True,
) -> QualityReport:
    """Compare two timelines. At most `sample` evenly spread reference frames are measured."""
    if not ref or not cand:
        raise ValueError("nothing to compare")
    pairing = align(ref_durations, cand_durations)
    idx = sorted({int(i) for i in np.linspace(0, len(ref) - 1, num=min(sample, len(ref)))}) if sample > 0 else list(range(len(ref)))
    ssims, psnrs = [], []
    for i in idx:
        a, b = ref[i], cand[pairing[i]]
        ssims.append(frame_ssim(a, b))
        if with_psnr:
            psnrs.append(frame_psnr(a, b))
    arr = np.asarray(ssims)
    worst = int(np.argmin(arr))
    return QualityReport(
        ssim_mean=float(arr.mean()),
        ssim_min=float(arr.min()),
        ssim_p5=float(np.percentile(arr, 5)),
        psnr_mean=float(np.mean(psnrs)) if psnrs else 0.0,
        worst_index=idx[worst],
        frames_compared=len(idx),
    )
