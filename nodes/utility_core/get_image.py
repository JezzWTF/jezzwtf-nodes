"""Get Image: split an IMAGE into RGB + a derived mask, with a two-up preview."""
from __future__ import annotations

import os
import time

import numpy as np
import torch
from PIL import Image

from ._comfy import temp_dir
from ._types import CATEGORY_IMAGE, InputTypes, UIPayload

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


class JWTFGetImage:
    CATEGORY = CATEGORY_IMAGE
    OUTPUT_NODE = True
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("IMAGE", "MASK")
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {"image": ("IMAGE",)},
            "optional": {
                "invert_mask": ("BOOLEAN", {"default": False}),
                "mask_threshold": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_mode": (list(MASK_MODES), {"default": "Alpha Channel"}),
            },
        }

    def run(self, image: torch.Tensor, invert_mask: bool = False, mask_threshold: float = 0.0,
            mask_mode: str = "Alpha Channel") -> dict[str, object]:
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
        return {"ui": ui, "result": (rgb, mask)}


NODE_CLASS_MAPPINGS = {"JWTFGetImage": JWTFGetImage}
NODE_DISPLAY_NAME_MAPPINGS = {"JWTFGetImage": "Get Image"}
