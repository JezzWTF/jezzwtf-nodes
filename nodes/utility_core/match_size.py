"""Match Image Size: resize an IMAGE or MASK to a reference or explicit size.

Follows the behavioural spec exactly, quirks included: the `mask` output is channel 0
of the result (the red channel for an IMAGE), a MASK input yields a single-channel
`[B,H,W,1]` image, `round_to` only applies to computed sides, and every mode needs both
target dimensions to resolve.
"""
from __future__ import annotations

import torch

from ._comfy import upscale
from ._types import CATEGORY_IMAGE, InputTypes

RESIZE_TYPES = (
    "scale dimensions", "fit within", "fill (crop)", "pad to",
    "shortest side", "longest side", "fit width", "fit height",
)
SCALE_METHODS = ("nearest-exact", "bilinear", "area", "bicubic", "lanczos")


def parse_hex_color(value: str) -> tuple[float, float, float]:
    try:
        s = value.strip().lstrip("#")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        if len(s) != 6:
            raise ValueError(value)
        return (int(s[0:2], 16) / 255.0, int(s[2:4], 16) / 255.0, int(s[4:6], 16) / 255.0)
    except (ValueError, AttributeError):
        return (0.0, 0.0, 0.0)


def round_to(v: float, r: int) -> int:
    r = max(1, int(r))
    return max(r, int(round(v / r)) * r)


def resolve_target(width: int, height: int, ref_wh: tuple[int, int] | None) -> tuple[int, int]:
    """Return (tw, th); a 0 means "use the reference". Both must resolve, whatever the mode."""
    tw = width if width > 0 else (ref_wh[0] if ref_wh else 0)
    th = height if height > 0 else (ref_wh[1] if ref_wh else 0)
    if tw <= 0 or th <= 0:
        raise ValueError("Match Image Size: connect a reference_image or set width and height explicitly.")
    return tw, th


def compute_size(mode: str, w: int, h: int, tw: int, th: int, r: int = 1) -> tuple[int, int, bool]:
    """Return (out_w, out_h, center_crop) for source (w, h) and target (tw, th)."""
    r = max(1, int(r))
    if mode in ("scale dimensions", "fill (crop)"):
        return tw, th, mode == "fill (crop)"
    if mode == "fit width":
        nw, nh = tw, round_to(h * tw / w, r)
    elif mode == "fit height":
        nw, nh = round_to(w * th / h, r), th
    elif mode == "shortest side":
        nw, nh = (tw, round_to(h * tw / w, r)) if w <= h else (round_to(w * tw / h, r), tw)
    elif mode == "longest side":
        nw, nh = (tw, round_to(h * tw / w, r)) if w >= h else (round_to(w * tw / h, r), tw)
    elif mode in ("fit within", "pad to"):
        s = min(tw / w, th / h)
        nw, nh = round_to(w * s, r), round_to(h * s, r)
    else:
        raise ValueError(f"unknown resize_type: {mode}")
    return max(r, nw), max(r, nh), False


def pad_center(x: torch.Tensor, tw: int, th: int, color: tuple[float, float, float]) -> torch.Tensor:
    """Paste `[B,C,h,w]` centred on a `[B,C,th,tw]` canvas filled with `color` (channels 0..min(C,3)-1)."""
    b, c, h, w = x.shape
    canvas = torch.zeros((b, c, th, tw), dtype=x.dtype, device=x.device)
    for ch in range(min(c, 3)):
        canvas[:, ch] = color[ch]
    ox, oy = (tw - w) // 2, (th - h) // 2
    dx0, dy0 = max(0, ox), max(0, oy)
    sx0, sy0 = dx0 - ox, dy0 - oy
    cw, chh = min(w - sx0, tw - dx0), min(h - sy0, th - dy0)
    if cw > 0 and chh > 0:
        canvas[:, :, dy0:dy0 + chh, dx0:dx0 + cw] = x[:, :, sy0:sy0 + chh, sx0:sx0 + cw]
    return canvas


def _wh(t: torch.Tensor) -> tuple[int, int]:
    return (int(t.shape[-1]), int(t.shape[-2])) if t.dim() == 3 else (int(t.shape[2]), int(t.shape[1]))


def match_size(inp: torch.Tensor, resize_type: str, scale_method: str, reference: torch.Tensor | None = None,
               width: int = 0, height: int = 0, crop: str = "center", pad_color: str = "#000000",
               rnd: int = 1) -> tuple[torch.Tensor, torch.Tensor, int, int]:
    x = inp.unsqueeze(1) if inp.dim() == 3 else inp.movedim(-1, 1)
    _, _, h, w = x.shape
    tw, th = resolve_target(width, height, _wh(reference) if reference is not None else None)
    nw, nh, center = compute_size(resize_type, w, h, tw, th, rnd)
    if resize_type == "scale dimensions":
        center = crop == "center"
    y = upscale(x, nw, nh, scale_method, "center" if center else "disabled")
    if resize_type == "pad to":
        y = pad_center(y, tw, th, parse_hex_color(pad_color))
    image = y.movedim(1, -1).contiguous()
    return image, y[:, 0].contiguous(), int(y.shape[-1]), int(y.shape[-2])


class JWTFMatchImageSize:
    CATEGORY = CATEGORY_IMAGE
    RETURN_TYPES = ("IMAGE", "MASK", "INT", "INT")
    RETURN_NAMES = ("image", "mask", "width", "height")
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {
                "input": ("IMAGE,MASK",),
                "resize_type": (list(RESIZE_TYPES), {"default": "scale dimensions"}),
                "scale_method": (list(SCALE_METHODS), {"default": "lanczos"}),
            },
            "optional": {
                "reference_image": ("IMAGE,MASK",),
                "width": ("INT", {"default": 0, "min": 0, "max": 16384}),
                "height": ("INT", {"default": 0, "min": 0, "max": 16384}),
                "crop": (["center", "disabled"], {"default": "center"}),
                "pad_color": ("STRING", {"default": "#000000"}),
                "round_to": ("INT", {"default": 1, "min": 1, "max": 128}),
            },
        }

    def run(self, input: torch.Tensor, resize_type: str, scale_method: str,  # noqa: A002 - socket name
            reference_image: torch.Tensor | None = None, width: int = 0, height: int = 0,
            crop: str = "center", pad_color: str = "#000000", round_to: int = 1
            ) -> tuple[torch.Tensor, torch.Tensor, int, int]:
        return match_size(input, resize_type, scale_method, reference_image, width, height, crop, pad_color, round_to)


NODE_CLASS_MAPPINGS = {"JWTFMatchImageSize": JWTFMatchImageSize}
NODE_DISPLAY_NAME_MAPPINGS = {"JWTFMatchImageSize": "Match Image Size"}
