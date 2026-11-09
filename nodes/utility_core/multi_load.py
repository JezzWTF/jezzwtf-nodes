"""Multi Load Image: up to 16 Load Image slots in one node."""
from __future__ import annotations

import hashlib
import json
import logging
import os

import numpy as np
import torch
from PIL import Image, ImageOps

from ._comfy import input_dir
from ._types import CATEGORY_IMAGE, InputTypes

MAX_SLOTS = 16
log = logging.getLogger("jezzwtf.utility_core.multi_load")


def parse_names(images_json: str) -> list[str]:
    try:
        data = json.loads(images_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [x if isinstance(x, str) else "" for x in data][:MAX_SLOTS]


def placeholder() -> torch.Tensor:
    return torch.zeros((1, 64, 64, 3), dtype=torch.float32)


def _safe_path(path: str) -> str | None:
    """`path` only when its real location sits inside the input, output or temp directory."""
    try:
        import folder_paths  # type: ignore[import-not-found]

        roots = [str(folder_paths.get_input_directory()), str(folder_paths.get_output_directory()),
                 str(folder_paths.get_temp_directory())]
    except Exception:
        roots = [input_dir()]
    real = os.path.realpath(path)
    for root in roots:
        base = os.path.realpath(root)
        try:
            if os.path.commonpath([base, real]) == base:
                return real
        except ValueError:  # different drives on Windows
            continue
    return None


def _annotated(name: str) -> str:
    """Resolve a Load Image style name; raise ValueError when it escapes the allowed directories."""
    import folder_paths  # type: ignore[import-not-found]

    safe = _safe_path(str(folder_paths.get_annotated_filepath(name)))
    if safe is None:
        raise ValueError(f"image path is outside the input/output/temp folders: {name}")
    return safe


def _exists(name: str) -> bool:
    import folder_paths  # type: ignore[import-not-found]

    if not folder_paths.exists_annotated_filepath(name):
        return False
    try:
        _annotated(name)
    except ValueError:
        return False
    return True


def _open(path: str) -> Image.Image:
    try:
        import node_helpers  # type: ignore[import-not-found]

        img = node_helpers.pillow(Image.open, path)
        return node_helpers.pillow(ImageOps.exif_transpose, img) or img
    except ImportError:
        img = Image.open(path)
        return ImageOps.exif_transpose(img) or img


def load_rgb(path: str) -> torch.Tensor:
    img = _open(path)
    if img.mode == "I":
        img = img.point(lambda v: v * (1 / 255))
    arr = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None]


class JWTFMultiLoadImage:
    CATEGORY = CATEGORY_IMAGE
    RETURN_TYPES = ("IMAGE",) * MAX_SLOTS
    RETURN_NAMES = tuple(f"image_{i}" for i in range(1, MAX_SLOTS + 1))
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {"required": {"images_json": ("STRING", {"default": "[]"})}}

    @classmethod
    def IS_CHANGED(cls, images_json: str = "[]") -> str:
        h = hashlib.sha256()
        for name in parse_names(images_json):
            h.update(name.encode("utf-8"))
            if not name:
                continue
            try:
                with open(_annotated(name), "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
            except Exception:
                continue
        return h.hexdigest()

    @classmethod
    def VALIDATE_INPUTS(cls, images_json: str = "[]") -> bool | str:
        for name in parse_names(images_json):
            if name and not _exists(name):
                return f"invalid image file: {name}"
        return True

    def run(self, images_json: str = "[]") -> tuple[torch.Tensor, ...]:
        out: list[torch.Tensor] = []
        for i, name in enumerate(parse_names(images_json)):
            if not name:
                log.info("Multi Load Image: slot %d is empty", i + 1)
                out.append(placeholder())
                continue
            out.append(load_rgb(_annotated(name)))
        while len(out) < MAX_SLOTS:
            out.append(placeholder())
        return tuple(out)


NODE_CLASS_MAPPINGS = {"JWTFMultiLoadImage": JWTFMultiLoadImage}
NODE_DISPLAY_NAME_MAPPINGS = {"JWTFMultiLoadImage": "Multi Load Image"}
