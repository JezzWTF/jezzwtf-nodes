"""Draw Image: an in-node sketch pad whose flattened PNG loads like Load Image."""
from __future__ import annotations

import hashlib
import os

import numpy as np
import torch
from PIL import Image, ImageOps

from comfy_api.latest import io

from ._comfy import input_dir

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


class JWTFDrawImage(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFDrawImage",
            display_name='Draw Image',
            category='JezzWTF/image',
            inputs=[
                io.Int.Input("width", default=1024, min=64, max=8192, step=8, tooltip="Canvas width in pixels when there is no saved drawing."),
                io.Int.Input("height", default=1024, min=64, max=8192, step=8, tooltip="Canvas height in pixels when there is no saved drawing."),
                io.Combo.Input("background", options=list(BACKGROUNDS), default='white', tooltip="Canvas background colour, with transparent mode also premultiplying the saved drawing's RGB by its alpha."),
                io.String.Input("image", default='', tooltip="Path under ComfyUI's input folder written by the drawing editor when it saves the rendered canvas."),
                io.String.Input("drawing_state", default='', tooltip="Serialized editable canvas state written by the drawing editor to restore the drawing in the workflow."),
            ],
            outputs=[
                io.Image.Output("image", tooltip="RGB pixels of the saved drawing or of a blank canvas at the requested dimensions."),
                io.Mask.Output("mask", tooltip="Inverse alpha of the drawing, with white marking transparent pixels."),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, width: int, height: int, background: str, image: str = "", drawing_state: str = "") -> str:
        path = resolve_input_file(image)
        if path is None:
            return f"blank-{width}x{height}-{background}"
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        h.update(background.encode("utf-8"))
        return h.hexdigest()

    @classmethod
    def execute(cls, width: int, height: int, background: str, image: str = "",
            drawing_state: str = "") -> io.NodeOutput:
        path = resolve_input_file(image)
        if path is None:
            return io.NodeOutput(*blank(width, height, background))
        return io.NodeOutput(*load_drawing(path, background))


NODES = [JWTFDrawImage]
