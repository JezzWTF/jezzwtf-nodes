"""Draw Image: an in-node sketch pad whose flattened PNG loads like Load Image."""
from __future__ import annotations

import hashlib
import os

import numpy as np
import torch
from PIL import Image, ImageOps

from ._comfy import input_dir
from ._types import CATEGORY_IMAGE, InputTypes

SUBFOLDER = "jezzwtf_draw"
BACKGROUNDS = ("white", "black", "transparent")


def resolve_input_file(name: str, base: str | None = None) -> str | None:
    """Join `name` under the input dir; reject escapes and non-files."""
    if not name or not name.strip():
        return None
    root = os.path.realpath(base or input_dir())
    path = os.path.realpath(os.path.join(root, name.strip()))
    try:
        if os.path.commonpath([root, path]) != root:
            return None
    except ValueError:  # different drives on Windows
        return None
    return path if os.path.isfile(path) else None


def blank(width: int, height: int, background: str) -> tuple[torch.Tensor, torch.Tensor]:
    fill = 1.0 if background == "white" else 0.0
    image = torch.full((1, height, width, 3), fill, dtype=torch.float32)
    mask = torch.full((1, height, width), 1.0 if background == "transparent" else 0.0, dtype=torch.float32)
    return image, mask


def load_drawing(path: str, background: str) -> tuple[torch.Tensor, torch.Tensor]:
    with Image.open(path) as opened:
        img = (ImageOps.exif_transpose(opened) or opened).convert("RGBA")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    rgb, alpha = arr[..., :3], arr[..., 3]
    if background == "transparent":
        rgb = rgb * alpha[..., None]
    return torch.from_numpy(np.ascontiguousarray(rgb))[None], torch.from_numpy(1.0 - alpha)[None]


class JWTFDrawImage:
    CATEGORY = CATEGORY_IMAGE
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {
                "width": ("INT", {"default": 1024, "min": 64, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 1024, "min": 64, "max": 8192, "step": 8}),
                "background": (list(BACKGROUNDS), {"default": "white"}),
                "image": ("STRING", {"default": ""}),
                "drawing_state": ("STRING", {"default": ""}),
            }
        }

    @classmethod
    def IS_CHANGED(cls, width: int, height: int, background: str, image: str = "", drawing_state: str = "") -> str:
        path = resolve_input_file(image)
        if path is None:
            return f"blank-{width}x{height}-{background}"
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        h.update(background.encode("utf-8"))
        return h.hexdigest()

    def run(self, width: int, height: int, background: str, image: str = "",
            drawing_state: str = "") -> tuple[torch.Tensor, torch.Tensor]:
        path = resolve_input_file(image)
        if path is None:
            return blank(width, height, background)
        return load_drawing(path, background)


NODE_CLASS_MAPPINGS = {"JWTFDrawImage": JWTFDrawImage}
NODE_DISPLAY_NAME_MAPPINGS = {"JWTFDrawImage": "Draw Image"}
