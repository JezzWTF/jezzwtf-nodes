"""Image Saver: bounded quality search using local colour SSIM, with lossless alternatives."""
from __future__ import annotations

import json
import os
from io import BytesIO

import numpy as np
import torch
from PIL import Image, PngImagePlugin
from scipy.ndimage import uniform_filter
from comfy_api.latest import io

from .media_files import pil_image, reserve_output

TARGETS = {5: 0.95, 6: 0.97, 7: 0.98, 8: 0.99, 9: 0.995, 10: 1.0}
FORMATS = {"png": "PNG", "webp": "WEBP", "jpeg": "JPEG", "avif": "AVIF", "tiff": "TIFF"}


def similarity(original: Image.Image, decoded: Image.Image) -> float:
    a, b = original.convert("RGB"), decoded.convert("RGB")
    if a.size != b.size:
        raise ValueError("Cannot measure images with different dimensions")
    a.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    b = b.resize(a.size, Image.Resampling.LANCZOS)
    x, y = np.asarray(a, dtype=np.float64) / 255, np.asarray(b, dtype=np.float64) / 255
    if np.array_equal(x, y):
        return 1.0
    mean = lambda z: uniform_filter(z, size=(7, 7, 1), mode="reflect")
    ux, uy = mean(x), mean(y)
    vx, vy = np.maximum(0, mean(x * x) - ux * ux), np.maximum(0, mean(y * y) - uy * uy)
    cov = mean(x * y) - ux * uy
    score = ((2 * ux * uy + 0.01**2) * (2 * cov + 0.03**2)) / ((ux * ux + uy * uy + 0.01**2) * (vx + vy + 0.03**2))
    return float(np.clip(score.mean(), -1, 1))


def encode(image: Image.Image, fmt: str, **options: object) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format=FORMATS[fmt], **options)
    return buffer.getvalue()


def squeeze(image: Image.Image, fmt: str, tier: int, smart: bool, quality: int,
            pnginfo: PngImagePlugin.PngInfo | None = None) -> tuple[bytes, dict[str, object]]:
    if fmt not in FORMATS or tier not in TARGETS:
        raise ValueError("Unknown image format or quality tier")
    target = TARGETS[tier]
    if fmt in ("png", "tiff"):
        options = {"optimize": True, "compress_level": 9, "pnginfo": pnginfo} if fmt == "png" else {"compression": "tiff_deflate"}
        candidates = [encode(image, fmt, **options)]
        if smart and fmt == "png" and image.getcolors(257) is not None:
            palette = image.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
            if np.array_equal(np.asarray(image), np.asarray(palette.convert(image.mode))):
                candidates.append(encode(palette, fmt, **options))
        return min(candidates, key=len), {"ssim": 1.0, "target": target, "target_met": True, "encoding": "lossless"}
    if fmt == "avif" and ".avif" not in Image.registered_extensions():
        raise ValueError("This Pillow build does not support AVIF")

    def attempt(q: int) -> tuple[bytes, float]:
        options = {"quality": q}
        if fmt == "jpeg":
            options.update(optimize=True, subsampling=0)
        data = encode(image, fmt, **options)
        with Image.open(BytesIO(data)) as decoded:
            return data, similarity(image, decoded)

    if not smart:
        data, score = attempt(int(quality))
        return data, {"ssim": score, "target": target, "target_met": score >= target, "encoding": f"quality {quality}"}
    data, score = attempt(100)
    best = (data, score, "quality 100")
    if score >= target:
        lo, hi = 1, 99
        while lo <= hi:
            q = (lo + hi) // 2
            trial, result = attempt(q)
            if result >= target:
                if len(trial) < len(best[0]):
                    best = (trial, result, f"quality {q}")
                hi = q - 1
            else:
                lo = q + 1
    if fmt == "webp":
        lossless = encode(image, fmt, lossless=True, method=6)
        if best[1] < target or len(lossless) < len(best[0]):
            best = (lossless, 1.0, "lossless")
    return best[0], {"ssim": best[1], "target": target, "target_met": best[1] >= target, "encoding": best[2]}


class JWTFImageSaver(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFImageSaver", display_name="Image Saver (Smart Squeeze)", category="JezzWTF/image",
            description="Save PNG, WebP, JPEG, AVIF or TIFF. Smart Squeeze searches for the smallest tested encoding meeting a local colour SSIM target, measured at up to 1024px. PNG can embed workflow metadata.",
            inputs=[io.Image.Input("images"), io.String.Input("filename_prefix", default="images/JezzWTF"),
                    io.Combo.Input("format", options=list(FORMATS), default="webp"),
                    io.Boolean.Input("smart_squeeze", default=True), io.Int.Input("quality_tier", default=8, min=5, max=10),
                    io.Int.Input("quality", default=90, min=1, max=100, tooltip="Used when Smart Squeeze is off."),
                    io.Boolean.Input("embed_workflow", default=True, tooltip="Embed prompt and workflow in PNG files only.")],
            outputs=[io.Image.Output("images"), io.String.Output("file_paths"), io.String.Output("report")],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo], is_output_node=True,
        )

    @classmethod
    def execute(cls, images: torch.Tensor, filename_prefix: str, format: str, smart_squeeze: bool,
                quality_tier: int, quality: int, embed_workflow: bool) -> io.NodeOutput:
        metadata = PngImagePlugin.PngInfo()
        if embed_workflow and format == "png":
            hidden = getattr(cls, "hidden", None)
            prompt = getattr(hidden, "prompt", None)
            if prompt is not None:
                metadata.add_text("prompt", json.dumps(prompt))
            for key, value in (getattr(hidden, "extra_pnginfo", None) or {}).items():
                metadata.add_text(key, json.dumps(value))
        paths, previews, reports = [], [], []
        for frame in images:
            image = pil_image(frame)
            if format == "jpeg" and image.mode == "RGBA":
                background = Image.new("RGBA", image.size, "white")
                image = Image.alpha_composite(background, image).convert("RGB")
            data, report = squeeze(image, format, int(quality_tier), smart_squeeze, int(quality), metadata)
            path, descriptor = reserve_output(filename_prefix, "jpg" if format == "jpeg" else format)
            try:
                with open(path, "wb") as file:
                    file.write(data)
            except BaseException:
                os.remove(path)
                raise
            paths.append(path)
            previews.append(descriptor)
            reports.append({"path": path, "bytes": len(data), **report})
        report_text = json.dumps(reports, indent=2)
        return io.NodeOutput(images, "\n".join(paths), report_text, ui={"images": previews, "text": [report_text]})


NODES = [JWTFImageSaver]
