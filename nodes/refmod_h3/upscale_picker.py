"""H3 upscale picker: a same-scale target size on a 16-px grid (spec section 13).

The MiniMax H3 latent upscaler is conditioned on the mean of the two axis scales, so the best
target keeps both axes at (nearly) the same scale. ``js/refmod_h3/upscale_math.js`` implements
the identical function for the live preview.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from comfy_api.latest import io


MODES = ("Scale factor", "Target megapixels")
SCALE_LABELS = ("1.5x", "2x", "2.5x", "3x", "4x", "Custom")
MIN_SCALE, MAX_SCALE = 1.0, 4.0
_LABEL_RE = re.compile(r"^\s*(\d+(\.\d+)?)\s*[x×]")
_EPS = 1e-9


@dataclass(frozen=True)
class Pick:
    width: int
    height: int
    scale: float          # mean axis scale of the chosen size (what the upscaler sees)
    scale_w: float
    scale_h: float
    requested: float
    note: str
    info: str


def label_scale(label: str) -> float:
    m = _LABEL_RE.match(str(label))
    return float(m.group(1)) if m else 2.0


def grid(multiple: int) -> int:
    return max(16, math.ceil(multiple / 16) * 16)


def _snap(v: float, m: int) -> int:
    return max(m, math.floor(v / m + 0.5) * m)


def requested_scale(w: int, h: int, mode: str, scale: str, custom_scale: float, megapixels: float
                    ) -> tuple[float, str]:
    """(clamped scale, note)."""
    if mode == "Target megapixels":
        mp = min(16.0, max(0.05, float(megapixels)))
        s = math.sqrt(mp * 1024 * 1024 / (w * h))
    else:
        s = float(custom_scale) if scale == "Custom" else label_scale(scale)
    note = ""
    if s < MIN_SCALE:
        if mode == "Target megapixels":
            note = "no upscale (target <= source)"
        s = MIN_SCALE
    elif s > MAX_SCALE:
        note = "capped at 4x"
        s = MAX_SCALE
    return s, note


def candidates(w: int, h: int, s: float, m: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = [(_snap(w * s, m), _snap(h * s, m))]
    lo = max(1, math.floor(0.8 * w * s / m))
    hi = math.ceil(1.2 * w * s / m) + 1
    for k in range(lo, hi + 1):
        cw = k * m
        rows = max(1, math.floor(cw * h / w / m))
        out.append((cw, rows * m))
        out.append((cw, (rows + 1) * m))
    return out


def choose(w: int, h: int, s: float, m: int) -> tuple[int, int]:
    best: tuple[float, int, int] | None = None
    for cw, ch in candidates(w, h, s, m):
        sw, sh = cw / w, ch / h
        if sw < 1 - _EPS or sh < 1 - _EPS:
            continue
        eff = (sw + sh) / 2
        if eff > MAX_SCALE:
            continue
        cost = 20 * abs(sw - sh) / eff + abs(eff / s - 1)
        if best is None or cost < best[0] or (cost == best[0] and cw < best[1]):
            best = (cost, cw, ch)
    if best is None:
        return math.ceil(w * s / m) * m, math.ceil(h * s / m) * m
    return best[1], best[2]


def pick_target(width: int, height: int, mode: str = "Scale factor", scale: str = "2x",
                custom_scale: float = 2.0, target_megapixels: float = 0.5, multiple: int = 16) -> Pick:
    w, h = max(1, int(width)), max(1, int(height))
    m = grid(int(multiple))
    s, note = requested_scale(w, h, mode, scale, custom_scale, target_megapixels)
    tw, th = choose(w, h, s, m)
    sw, sh = tw / w, th / h
    eff = (sw + sh) / 2
    mismatch = abs(sw - sh) / eff
    match = "exact" if mismatch < 1e-6 else f"uneven {mismatch * 100:.1f}%"
    info = (f"{w}x{h} -> {tw}x{th} | {sw:.3f}x by {sh:.3f}x ({match}) | upscaler scale {eff:.3f}x"
            f" | {w * h / 1048576:.2f} -> {tw * th / 1048576:.2f} MP")
    if note:
        info += f" | {note}"
    return Pick(tw, th, eff, sw, sh, s, note, info)


class JWTFH3UpscalePicker(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFH3UpscalePicker",
            display_name='H3 Upscale Picker',
            category='JezzWTF/refmod',
            description='Same-scale target size on a 16-px grid for the MiniMax H3 latent upscaler.',
            inputs=[
                io.Int.Input("width", default=640, min=1, max=16384, tooltip="Source width in pixels."),
                io.Int.Input("height", default=352, min=1, max=16384, tooltip="Source height in pixels."),
                io.Combo.Input("mode", options=list(MODES), default='Scale factor', tooltip="Chooses whether to calculate output dimensions from a scale factor or a target pixel area."),
                io.Combo.Input("scale", options=list(SCALE_LABELS), default='2x', tooltip="Preset upscale factor, with Custom using the numeric scale."),
                io.Float.Input("custom_scale", default=2.0, min=1.0, max=4.0, step=0.01, tooltip="Upscale factor used when the scale choice is Custom."),
                io.Float.Input("target_megapixels", default=0.5, min=0.05, max=16.0, step=0.05, tooltip="Target image area in units of 1,048,576 pixels, with the requested scale clamped between 1x and 4x."),
                io.Int.Input("multiple", default=16, min=16, max=256, step=16, tooltip="Output pixel grid size, rounded up to a multiple of 16."),
            ],
            outputs=[
                io.Int.Output("width", tooltip="Selected output width in pixels on the requested grid."),
                io.Int.Output("height", tooltip="Selected output height in pixels on the requested grid."),
                io.Float.Output("scale", tooltip="Mean of the horizontal and vertical scale factors after choosing the output dimensions."),
                io.String.Output("info", tooltip="Summary of the chosen dimensions, per-axis scales, pixel area and any scale clamping."),
            ],
        )

    @classmethod
    def execute(cls, width: int, height: int, mode: str, scale: str, custom_scale: float,
             target_megapixels: float, multiple: int) -> io.NodeOutput:
        p = pick_target(width, height, mode, scale, custom_scale, target_megapixels, multiple)
        ui = {"jezzwtf_upscale": [{"sw": max(1, int(width)), "sh": max(1, int(height)),
                                   "tw": p.width, "th": p.height, "scale": p.scale}]}
        return io.NodeOutput(p.width, p.height, p.scale, p.info, ui=ui)


NODES = [JWTFH3UpscalePicker]
