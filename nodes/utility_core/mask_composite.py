"""Mask Composite: combine two masks at an offset with a choice of operations, opacity, inversion and a soft edge."""
from __future__ import annotations

import torch
import torch.nn.functional as F

from comfy_api.latest import io

OPERATIONS = ("replace", "add", "subtract", "multiply", "min", "max", "difference", "xor")
MAX_FEATHER = 256


def _blend(dst: torch.Tensor, src: torch.Tensor, operation: str) -> torch.Tensor:
    """The two overlapping regions combined; every result stays inside 0..1."""
    if operation == "replace":
        return src
    if operation == "add":
        return (dst + src).clamp(0.0, 1.0)
    if operation == "subtract":
        return (dst - src).clamp(0.0, 1.0)
    if operation == "multiply":
        return dst * src
    if operation == "min":
        return torch.minimum(dst, src)
    if operation == "max":
        return torch.maximum(dst, src)
    if operation == "difference":
        return (dst - src).abs()
    if operation == "xor":
        return dst * (1.0 - src) + src * (1.0 - dst)
    raise ValueError(f"unknown operation {operation!r}")


def soften(mask: torch.Tensor, radius: int) -> torch.Tensor:
    """Blur a [B,H,W] mask by about `radius` pixels (two box passes, edges not darkened)."""
    if radius <= 0:
        return mask
    k = 2 * min(radius, MAX_FEATHER) + 1
    x = mask.unsqueeze(1)
    for _ in range(2):
        x = F.avg_pool2d(F.pad(x, (k // 2,) * 4, mode="replicate"), kernel_size=k, stride=1)
    return x.squeeze(1)


def composite(destination: torch.Tensor, source: torch.Tensor, x: int, y: int, operation: str = "add",
              opacity: float = 1.0, invert_source: bool = False, feather: int = 0) -> torch.Tensor:
    """`source` placed with its top-left corner at (x, y) on `destination`; the parts outside it are cut off.

    Batches broadcast: the result has as many masks as the longer of the two, repeating the shorter one.
    """
    dst = destination.float()
    src = source.float()
    if dst.dim() == 2:
        dst = dst.unsqueeze(0)
    if src.dim() == 2:
        src = src.unsqueeze(0)
    if invert_source:
        src = 1.0 - src
    src = soften(src, int(feather))
    count = max(dst.shape[0], src.shape[0])
    out = dst[torch.arange(count) % dst.shape[0]].clone()
    src = src[torch.arange(count) % src.shape[0]]
    _, height, width = out.shape
    _, sh, sw = src.shape
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(width, x + sw), min(height, y + sh)
    if x1 <= x0 or y1 <= y0:
        return out
    region = out[:, y0:y1, x0:x1]
    piece = src[:, y0 - y:y1 - y, x0 - x:x1 - x]
    amount = max(0.0, min(1.0, float(opacity)))
    out[:, y0:y1, x0:x1] = (region * (1.0 - amount) + _blend(region, piece, operation) * amount).clamp(0.0, 1.0)
    return out


class JWTFMaskComposite(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFMaskComposite",
            display_name="Mask Composite",
            category="JezzWTF/image",
            description="Combine two masks: place the source on the destination at an offset and add, subtract, multiply or compare them, with opacity and a soft edge.",
            inputs=[
                io.Mask.Input("destination", tooltip="The mask that is drawn on and returned, at its own size."),
                io.Mask.Input("source", tooltip="The mask placed on the destination. Parts that fall outside the destination are cut off."),
                io.Combo.Input("operation", options=list(OPERATIONS), default="add", tooltip="How the two overlap: replace, add, subtract (destination minus source), multiply, min, max, difference, or xor."),
                io.Int.Input("x", default=0, min=-16384, max=16384, step=1, tooltip="Horizontal position of the source's left edge on the destination, in pixels; negative moves it off the left."),
                io.Int.Input("y", default=0, min=-16384, max=16384, step=1, tooltip="Vertical position of the source's top edge on the destination, in pixels; negative moves it off the top."),
                io.Float.Input("opacity", default=1.0, min=0.0, max=1.0, step=0.01, optional=True, tooltip="How much of the combined result replaces the destination; 0 leaves it unchanged."),
                io.Boolean.Input("invert_source", default=False, optional=True, tooltip="Flip the source (black becomes white) before combining."),
                io.Int.Input("feather", default=0, min=0, max=MAX_FEATHER, step=1, optional=True, tooltip="Blur the source's edges by about this many pixels before combining; 0 keeps them hard."),
            ],
            outputs=[io.Mask.Output("MASK", tooltip="The destination with the source combined into it.")],
        )

    @classmethod
    def execute(cls, destination: torch.Tensor, source: torch.Tensor, operation: str, x: int, y: int,
                opacity: float = 1.0, invert_source: bool = False, feather: int = 0) -> io.NodeOutput:
        return io.NodeOutput(composite(destination, source, int(x), int(y), operation, opacity, invert_source, int(feather)))


NODES = [JWTFMaskComposite]
