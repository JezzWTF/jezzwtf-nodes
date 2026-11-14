"""Small image-preview and collision-safe output helpers shared by the image tools."""
from __future__ import annotations

import os
import re
import tempfile
import uuid

import numpy as np
import torch
from PIL import Image

from ._comfy import temp_dir


def output_dir() -> str:
    try:
        import folder_paths
        return str(folder_paths.get_output_directory())
    except ImportError:
        return os.path.join(tempfile.gettempdir(), "jezzwtf_output")


def pil_image(frame: torch.Tensor) -> Image.Image:
    pixels = frame.detach().float().cpu().clamp(0, 1).numpy()
    if pixels.ndim == 3 and pixels.shape[-1] == 1:
        pixels = pixels[..., 0]
    return Image.fromarray(np.round(pixels * 255).astype(np.uint8))


def preview(frame: torch.Tensor, prefix: str, *, edge: int = 1024) -> dict[str, str]:
    image = pil_image(frame)
    image.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    folder = os.path.join(temp_dir(), "jezzwtf_image_tools")
    os.makedirs(folder, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex}.png"
    image.save(os.path.join(folder, filename))
    return {"filename": filename, "subfolder": "jezzwtf_image_tools", "type": "temp"}


def reserve_output(prefix: str, extension: str) -> tuple[str, dict[str, str]]:
    root = os.path.realpath(output_dir())
    parts = str(prefix).replace("\\", "/").split("/")
    if not parts or any(p in ("", ".", "..") for p in parts):
        raise ValueError("Use a filename prefix inside the output folder, for example images/JezzWTF")
    parts = [re.sub(r'[<>:"|?*\x00-\x1f]', "_", p).strip(" .") or "image" for p in parts]
    folder = os.path.realpath(os.path.join(root, *parts[:-1]))
    if os.path.commonpath([root, folder]) != root:
        raise ValueError("Filename prefix escapes the output folder")
    os.makedirs(folder, exist_ok=True)
    for counter in range(1, 1000000):
        filename = f"{parts[-1]}_{counter:05d}.{extension}"
        path = os.path.join(folder, filename)
        try:
            with open(path, "xb"):
                pass
        except FileExistsError:
            continue
        return path, {"filename": filename, "subfolder": "/".join(parts[:-1]), "type": "output"}
    raise ValueError("No available filename for this prefix")
