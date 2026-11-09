"""Resolution Picker: ratio + megapixels or a preset, snapped to a multiple."""
from __future__ import annotations

import math
import re

import torch

from ._comfy import intermediate_device, intermediate_dtype
from ._types import CATEGORY_UTILS, InputTypes

ASPECT_LABELS = (
    "1:1 (Square)", "5:4 (Large Format)", "4:3 (Standard)", "3:2 (Photo)", "16:10 (Laptop)",
    "16:9 (Widescreen)", "1.85:1 (Cinema Flat)", "2:1 (Univisium)", "2.35:1 (Cinemascope)",
    "2.39:1 (Anamorphic)", "21:9 (Ultrawide)", "32:9 (Super Ultrawide)", "3:1 (Banner)",
    "4:5 (Portrait Social)", "3:4 (Portrait Standard)", "2:3 (Portrait Photo)", "9:16 (Vertical Video)",
    "9:21 (Tall Ultrawide)", "1:2 (Tall)", "1:3 (Tall Banner)", "Custom",
)
PRESET_LABELS = (
    "512x512 (Square S)", "768x768 (Square M)", "1024x1024 (Square 1MP)", "1280x1280 (Square L)",
    "1536x1536 (Square XL)", "2048x2048 (Square 4MP)", "640x480 (4:3 SD)", "1024x768 (4:3 XGA)",
    "1280x960 (4:3 HD)", "1600x1200 (4:3 UXGA)", "1152x768 (3:2)", "1536x1024 (3:2)", "1920x1280 (3:2)",
    "640x360 (16:9 nHD)", "832x480 (16:9 480p)", "960x544 (16:9 540p)", "1024x576 (16:9)",
    "1280x720 (HD 720p)", "1536x864 (16:9)", "1920x1080 (Full HD 1080p)", "2560x1440 (QHD 1440p)",
    "3840x2160 (4K UHD)", "1792x768 (21:9)", "2560x1080 (21:9 UW-FHD)", "3440x1440 (21:9 UW-QHD)",
    "1152x896 (SDXL 9:7)", "1216x832 (SDXL 3:2)", "1344x768 (SDXL 16:9)", "1536x640 (SDXL 21:9)",
    "480x832 (9:16 Small)", "576x1024 (9:16)", "720x1280 (9:16 HD)", "864x1536 (9:16)",
    "1080x1920 (9:16 Full HD)", "768x1024 (3:4)", "1024x1536 (2:3)", "896x1152 (SDXL 7:9)",
    "832x1216 (SDXL 2:3)", "768x1344 (SDXL 9:16)", "640x1536 (SDXL 9:21)",
)
MODES = ("Ratio + Megapixels", "Preset Resolution")
_RATIO_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)")
_SIZE_RE = re.compile(r"^\s*(\d+)\s*x\s*(\d+)", re.IGNORECASE)


def parse_ratio(label: str) -> tuple[float, float]:
    m = _RATIO_RE.match(label)
    if not m:
        return (1.0, 1.0)
    rw, rh = float(m.group(1)), float(m.group(2))
    return (rw, rh) if rw > 0 and rh > 0 else (1.0, 1.0)


def parse_size(label: str) -> tuple[int, int]:
    m = _SIZE_RE.match(label)
    if not m:
        return (1024, 1024)
    w, h = int(m.group(1)), int(m.group(2))
    return (w, h) if w > 0 and h > 0 else (1024, 1024)


def snap(v: float, multiple: int) -> int:
    m = max(1, int(multiple))
    return max(m, int(math.floor(v / m + 0.5)) * m)


def compute_resolution(mode: str, aspect_ratio: str, custom_w: float, custom_h: float, megapixels: float,
                       preset: str, snap_presets: bool, multiple: int, swap: bool) -> tuple[int, int]:
    if mode == "Preset Resolution":
        w, h = parse_size(preset)
        if snap_presets:
            w, h = snap(w, multiple), snap(h, multiple)
    else:
        if aspect_ratio == "Custom":
            rw, rh = min(100.0, max(0.1, custom_w)), min(100.0, max(0.1, custom_h))
        else:
            rw, rh = parse_ratio(aspect_ratio)
        pixels = min(16.0, max(0.05, megapixels)) * 1024 * 1024
        s = math.sqrt(pixels / (rw * rh))
        w, h = snap(rw * s, multiple), snap(rh * s, multiple)
    return (h, w) if swap else (w, h)


class JWTFResolutionPicker:
    CATEGORY = CATEGORY_UTILS
    RETURN_TYPES = ("INT", "INT", "LATENT")
    RETURN_NAMES = ("width", "height", "latent")
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {
                "mode": (list(MODES), {"default": "Ratio + Megapixels"}),
                "aspect_ratio": (list(ASPECT_LABELS), {"default": "16:9 (Widescreen)"}),
                "custom_ratio_w": ("FLOAT", {"default": 16.0, "min": 0.1, "max": 100.0, "step": 0.01}),
                "custom_ratio_h": ("FLOAT", {"default": 9.0, "min": 0.1, "max": 100.0, "step": 0.01}),
                "megapixels": ("FLOAT", {"default": 1.0, "min": 0.05, "max": 16.0, "step": 0.05}),
                "preset_resolution": (list(PRESET_LABELS), {"default": "1280x720 (HD 720p)"}),
                "snap_presets": ("BOOLEAN", {"default": True, "label_on": "snap to multiple",
                                             "label_off": "exact preset"}),
                "multiple": ("INT", {"default": 32, "min": 1, "max": 256}),
                "swap_orientation": ("BOOLEAN", {"default": False}),
                "batch_size": ("INT", {"default": 1, "min": 1, "max": 4096}),
            }
        }

    def run(self, mode: str, aspect_ratio: str, custom_ratio_w: float, custom_ratio_h: float, megapixels: float,
            preset_resolution: str, snap_presets: bool, multiple: int, swap_orientation: bool,
            batch_size: int) -> tuple[int, int, dict[str, object]]:
        w, h = compute_resolution(mode, aspect_ratio, custom_ratio_w, custom_ratio_h, megapixels,
                                  preset_resolution, snap_presets, multiple, swap_orientation)
        latent = torch.zeros([max(1, batch_size), 4, max(1, h // 8), max(1, w // 8)], device=intermediate_device(),
                             dtype=intermediate_dtype())
        return (w, h, {"samples": latent, "downscale_ratio_spacial": 8})


NODE_CLASS_MAPPINGS = {"JWTFResolutionPicker": JWTFResolutionPicker}
NODE_DISPLAY_NAME_MAPPINGS = {"JWTFResolutionPicker": "Resolution Picker"}
