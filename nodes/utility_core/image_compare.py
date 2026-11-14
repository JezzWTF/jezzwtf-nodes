"""Image Compare: interactive previews plus full-resolution difference and metrics."""
from __future__ import annotations

import json
import math

import torch
import torch.nn.functional as F
from comfy_api.latest import io

from .media_files import preview


def prepare_pair(a: torch.Tensor, b: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    if a.ndim != 4 or b.ndim != 4 or not a.shape[0] or not b.shape[0]:
        raise ValueError("Image Compare needs non-empty IMAGE batches")
    a, b = a[..., :3].float(), b[..., :3].to(device=a.device, dtype=torch.float32)
    if a.shape[1:3] != b.shape[1:3]:
        b = F.interpolate(b.movedim(-1, 1), size=a.shape[1:3], mode="bilinear", align_corners=False).movedim(1, -1)
    count = max(a.shape[0], b.shape[0])
    return a[torch.arange(count, device=a.device) % a.shape[0]], b[torch.arange(count, device=b.device) % b.shape[0]]


class JWTFImageCompare(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFImageCompare", display_name="Image Compare", category="JezzWTF/image",
            description="Compare image batches with a wipe, blend, difference, toggle or mask. B is resized to A; shorter batches repeat.",
            inputs=[io.Image.Input("image_a"), io.Image.Input("image_b"), io.Mask.Input("mask", optional=True)],
            outputs=[io.Image.Output("difference"), io.String.Output("metrics")], is_output_node=True,
        )

    @classmethod
    def execute(cls, image_a: torch.Tensor, image_b: torch.Tensor, mask: torch.Tensor | None = None) -> io.NodeOutput:
        a, b = prepare_pair(image_a, image_b)
        diff = (a - b).abs()
        scores = []
        frames = []
        # Keep previews bounded; metrics and the difference output cover the entire batch.
        for i in range(a.shape[0]):
            mse = float((a[i] - b[i]).square().mean())
            scores.append({"frame": i + 1, "mae": float(diff[i].mean()), "psnr_db": None if mse == 0 else -10 * math.log10(mse)})
            if i < 32:
                entry = {"a": preview(a[i], "a"), "b": preview(b[i], "b"), "difference": preview(diff[i], "diff")}
                if mask is not None:
                    m = mask.unsqueeze(0) if mask.ndim == 2 else mask
                    m = F.interpolate(m[i % len(m)][None, None].float().to(a.device), size=a.shape[1:3], mode="bilinear", align_corners=False)[0, 0].clamp(0, 1)[..., None]
                    entry["mask"] = preview(a[i] * (1 - m) + b[i] * m, "mask")
                frames.append(entry)
        report = json.dumps({"frames": scores, "preview_count": len(frames), "b_resized": image_a.shape[1:3] != image_b.shape[1:3]}, allow_nan=False)
        return io.NodeOutput(diff, report, ui={"jwtf_compare": [{"frames": frames, "metrics": scores[:32], "total": len(scores)}]})


NODES = [JWTFImageCompare]
