"""Get Image: split an IMAGE into RGB + a derived mask, with a two-up preview."""
from __future__ import annotations

import os
import time

import numpy as np
import torch
from PIL import Image

from comfy_api.latest import io

from ._comfy import temp_dir
from ._types import UIPayload

MASK_MODES = ("Alpha Channel", "Luminance", "Blank")
UI_KEY = "jezzwtf_get_image"


def compute_mask(image: torch.Tensor, mode: str = "Alpha Channel", threshold: float = 0.0,
                 invert: bool = False) -> torch.Tensor:
    b, h, w, c = image.shape
    if mode == "Alpha Channel" and c >= 4:
        mask = 1.0 - image[..., 3]
    elif mode == "Luminance" and c >= 3:
        # Matches the original: inverted luminance (bright pixels -> 0).
        lum = 0.2126 * image[..., 0] + 0.7152 * image[..., 1] + 0.0722 * image[..., 2]
        mask = 1.0 - lum
    else:
        mask = torch.zeros((b, h, w), dtype=torch.float32, device=image.device)
    if threshold > 0:
        mask = (mask > threshold).float()
    if invert:
        mask = 1.0 - mask
    return mask.float()


def _save_png(arr: np.ndarray, path: str) -> None:
    Image.fromarray(arr).save(path, compress_level=1)


class JWTFGetImage(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFGetImage",
            display_name='Get Image',
            category='JezzWTF/image',
            inputs=[
                io.Image.Input("image", tooltip="Source pixels to preview and use for mask extraction."),
                io.Boolean.Input("invert_mask", default=False, optional=True, tooltip="Flips black and white in the mask after any threshold is applied."),
                io.Float.Input("mask_threshold", default=0.0, min=0.0, max=1.0, step=0.01, optional=True, tooltip="Binarises the mask by keeping values strictly above this cutoff, with 0 leaving the mask continuous."),
                io.Combo.Input("mask_mode", options=list(MASK_MODES), default='Alpha Channel', optional=True, tooltip="Uses inverse alpha or inverse luminance, with a zero mask when the selected channel data is unavailable."),
            ],
            outputs=[
                io.Image.Output("IMAGE", tooltip="Source image with any alpha channel removed."),
                io.Mask.Output("MASK", tooltip="Mask computed from the selected channel data, threshold and inversion."),
            ],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, image: torch.Tensor, invert_mask: bool = False, mask_threshold: float = 0.0,
            mask_mode: str = "Alpha Channel") -> io.NodeOutput:
        mask = compute_mask(image, mask_mode, mask_threshold, invert_mask)
        rgb = image[..., :3]
        out_dir = temp_dir()
        stem = f"jwtf_getimage_{int(time.time() * 1000)}"
        entries: list[dict[str, str]] = []
        try:
            rgb_arr = (rgb[0].clamp(0, 1).cpu().numpy() * 255).round().astype(np.uint8)
            mask_arr = (mask[0].clamp(0, 1).cpu().numpy() * 255).round().astype(np.uint8)
            for kind, arr in (("image", rgb_arr), ("mask", mask_arr)):
                name = f"{stem}_{'img' if kind == 'image' else 'mask'}.png"
                _save_png(arr, os.path.join(out_dir, name))
                entries.append({"filename": name, "subfolder": "", "type": "temp", "kind": kind})
        except Exception:
            entries = []
        ui: UIPayload = {UI_KEY: list(entries)}
        return io.NodeOutput(rgb, mask, ui=ui)


NODES = [JWTFGetImage]
