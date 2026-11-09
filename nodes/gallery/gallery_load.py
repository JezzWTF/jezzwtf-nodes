"""Gallery Load: load one or several images picked in a floating gallery window (input or output folders)."""
from __future__ import annotations

import hashlib
import os

import numpy as np
import torch
from comfy_api.latest import io
from PIL import Image, ImageOps

from . import listing

MAX_PICKS = 64
PLACEHOLDER = "(open the gallery)"


def open_image(path: str) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img) or img
    img.load()
    return img


def to_tensors(img: Image.Image, size: tuple[int, int]) -> tuple[torch.Tensor, torch.Tensor]:
    """(IMAGE [1,H,W,3], MASK [1,H,W]) at `size` (width, height); the mask is 1 where the picture is transparent."""
    has_alpha = "A" in img.getbands() or "transparency" in img.info
    rgba = img.convert("RGBA")
    if rgba.size != size:
        rgba = rgba.resize(size, Image.Resampling.LANCZOS)
    arr = np.asarray(rgba, dtype=np.float32) / 255.0
    image = torch.from_numpy(arr[..., :3].copy())[None]
    mask = torch.from_numpy(1.0 - arr[..., 3].copy())[None] if has_alpha else torch.zeros((1, size[1], size[0]), dtype=torch.float32)
    return image, mask


def load_batch(names: list[str]) -> tuple[torch.Tensor, torch.Tensor, list[str]]:
    """Every picked image resized to the first one's size and stacked into one batch."""
    images: list[torch.Tensor] = []
    masks: list[torch.Tensor] = []
    labels: list[str] = []
    size: tuple[int, int] | None = None
    for raw in names[:MAX_PICKS]:
        path = listing.resolve_ref(raw)
        img = open_image(path)
        size = size or img.size
        image, mask = to_tensors(img, size)
        images.append(image)
        masks.append(mask)
        labels.append(listing.parse_ref(raw).label())
    return torch.cat(images, dim=0), torch.cat(masks, dim=0), labels


class JWTFGalleryLoad(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFGalleryLoad",
            display_name="Gallery Load",
            category="JezzWTF/image",
            description="Pick images in a floating gallery window (input or output folders, with folders and search). Several picks become one batch.",
            inputs=[
                io.String.Input("selection", default="[]", tooltip="The picked images as a JSON list; the Gallery window writes this."),
            ],
            outputs=[
                io.Image.Output("images"),
                io.Mask.Output("masks"),
                io.String.Output("names"),
                io.Int.Output("count"),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, selection: str = "[]") -> str:
        digest = hashlib.sha256()
        for name in listing.parse_selection(selection):
            digest.update(name.encode("utf-8"))
            try:
                stat = os.stat(listing.resolve_ref(name))
                digest.update(f"{stat.st_mtime_ns}:{stat.st_size}".encode())
            except (ValueError, OSError):
                digest.update(b"missing")
        return digest.hexdigest()

    @classmethod
    def validate_inputs(cls, selection: str = "[]") -> bool | str:
        names = listing.parse_selection(selection)
        if not names:
            return "Gallery Load: pick at least one image in the gallery window."
        for name in names:
            try:
                listing.resolve_ref(name)
            except (ValueError, OSError) as exc:
                return f"Gallery Load: {exc}"
        return True

    @classmethod
    def execute(cls, selection: str = "[]") -> io.NodeOutput:
        names = listing.parse_selection(selection)
        if not names:
            raise ValueError("Gallery Load: pick at least one image in the gallery window.")
        images, masks, labels = load_batch(names)
        return io.NodeOutput(images, masks, "\n".join(labels), int(images.shape[0]))


NODES = [JWTFGalleryLoad]
