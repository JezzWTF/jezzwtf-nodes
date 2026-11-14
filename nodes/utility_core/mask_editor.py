"""Mask Editor: paint a reusable grayscale mask against an image preview."""
from __future__ import annotations


import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from comfy_api.latest import io

from ._comfy import file_sha256
from .draw_image import resolve_input_file
from .media_files import preview
from .mask_composite import soften


def edited_mask(images: torch.Tensor, mask: torch.Tensor | None, painted_mask: str) -> torch.Tensor:
    batch, height, width = images.shape[:3]
    if painted_mask:
        path = resolve_input_file(painted_mask)
        if path is None:
            raise ValueError("Mask Editor: saved mask is missing; restore it or clear the saved mask field")
        with Image.open(path) as source:
            arr = np.asarray(source.convert("L"), dtype=np.float32).copy() / 255
        mask = torch.from_numpy(arr)[None]
    if mask is None:
        return torch.zeros((batch, height, width), device=images.device)
    if mask.ndim == 2:
        mask = mask[None]
    if mask.ndim != 3 or not mask.shape[0]:
        raise ValueError("Mask Editor needs a non-empty [batch,height,width] mask")
    mask = mask.float().to(images.device)
    if mask.shape[1:] != (height, width):
        mask = F.interpolate(mask[:, None], size=(height, width), mode="bilinear", align_corners=False)[:, 0]
    return mask[torch.arange(batch, device=images.device) % mask.shape[0]].clamp(0, 1)


class JWTFMaskEditor(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFMaskEditor", display_name="Mask Editor", category="JezzWTF/image",
            description="Run once to load the image, then paint white to select or erase to black. Saved painting applies to every image in the batch. White means masked/inpaint. Optional incoming masks are used until a painting is saved.",
            inputs=[io.Image.Input("images"), io.Mask.Input("mask", optional=True),
                    io.String.Input("painted_mask", default="", optional=True, tooltip="Saved grayscale PNG under the input folder, managed by the editor. Clear to return to the incoming mask."),
                    io.Boolean.Input("invert", default=False, optional=True), io.Int.Input("feather", default=0, min=0, max=64, optional=True)],
            outputs=[io.Image.Output("images"), io.Mask.Output("mask"), io.Image.Output("mask_image")], is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, painted_mask: str = "", **_) -> str:
        if not painted_mask:
            return "unpainted"
        path = resolve_input_file(painted_mask)
        if path is None:
            return "missing"
        with open(path, "rb") as source:
            return file_sha256(source).hexdigest()

    @classmethod
    def execute(cls, images: torch.Tensor, mask: torch.Tensor | None = None, painted_mask: str = "",
                invert: bool = False, feather: int = 0) -> io.NodeOutput:
        raw = edited_mask(images, mask, painted_mask)
        result = soften(1 - raw if invert else raw, int(feather)).clamp(0, 1)
        mask_image = result[..., None].expand(-1, -1, -1, 3)
        descriptor = {"background": preview(images[0, ..., :3], "mask_background"),
                      "mask": preview(raw[0, ..., None].expand(-1, -1, 3), "mask_paint", edge=max(images.shape[1:3]))}
        return io.NodeOutput(images, result, mask_image, ui={"jwtf_mask_editor": [descriptor]})


NODES = [JWTFMaskEditor]
