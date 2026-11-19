"""Native WeVisOne selection and geometry-preserving regional refinement helpers."""
from __future__ import annotations

import importlib
import json
import math
from dataclasses import dataclass

import torch
from comfy_api.latest import io

from ._comfy import upscale
from .mask_composite import soften


def native_detector():
    try:
        return importlib.import_module("comfy_extras.nodes_wevisone").WeVisOneDetect
    except (ImportError, AttributeError) as exc:
        raise RuntimeError("Smart Select requires native WeVisOne-VL support. Update ComfyUI and restart.") from exc


def image_shape(images):
    if not isinstance(images, torch.Tensor) or images.ndim != 4 or min(images.shape[:3]) < 1 or images.shape[-1] < 3:
        raise ValueError("Expected non-empty IMAGE data [batch,height,width,RGB]")
    return images.shape[:3]


def frame_boxes(boxes, batch):
    if isinstance(boxes, dict):
        boxes = [[boxes]]
    elif isinstance(boxes, list) and boxes and isinstance(boxes[0], dict):
        boxes = [boxes]
    if not isinstance(boxes, list) or len(boxes) != batch or any(not isinstance(b, list) for b in boxes):
        raise ValueError("Bounding boxes must be grouped by image frame")
    return boxes


def box_bounds(box, width, height):
    try:
        x, y, w, h = (float(box[k]) for k in ("x", "y", "width", "height"))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("A region box needs finite x, y, width and height values") from exc
    if not all(math.isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
        raise ValueError("A region box needs finite coordinates and positive dimensions")
    bounds = max(0, math.floor(x)), max(0, math.floor(y)), min(width, math.ceil(x + w)), min(height, math.ceil(y + h))
    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        raise ValueError("The selected region is outside the image")
    return bounds


def source_mask(mask, batch, height, width, device):
    if mask is None:
        return None
    if mask.ndim == 2:
        mask = mask[None]
    if mask.ndim != 3 or mask.shape[0] not in (1, batch) or mask.shape[1:] != (height, width):
        raise ValueError("Selection masks must match the source image dimensions and batch (or have batch one)")
    if not torch.isfinite(mask).all():
        raise ValueError("Selection masks must contain finite values")
    return mask.to(device=device, dtype=torch.float32).clamp(0, 1).expand(batch, -1, -1)


class JWTFSmartSelect(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="JWTFSmartSelect", display_name="Smart Select (WeVisOne)", category="JezzWTF/image",
            description="Find a subject described in words with native WeVisOne-VL. Output alpha masks and pixel boxes for Mask Editor or regional refinement. Detection mode outputs rectangular masks; segmentation outputs the model's mattes.",
            inputs=[io.Clip.Input("clip", tooltip="WeVisOne-VL checkpoint loaded by CLIPLoader; native core detects this architecture automatically."), io.Image.Input("images"),
                    io.String.Input("query", default="face", multiline=True),
                    io.Combo.Input("task", options=["segmentation", "detection"], default="segmentation"),
                    io.Combo.Input("selection", options=["largest", "all", "index"], default="largest"),
                    io.Int.Input("selection_index", default=0, min=0, max=999, tooltip="Zero-based detection index, used only by index selection."),
                    io.Int.Input("max_length", default=1024, min=64, max=32768)],
            outputs=[io.Mask.Output("mask"), io.BoundingBox.Output("bboxes"), io.String.Output("report")],
        )

    @classmethod
    def execute(cls, clip, images, query, task="segmentation", selection="largest", selection_index=0, max_length=1024):
        batch, height, width = image_shape(images)
        if not query.strip() or task not in ("segmentation", "detection") or selection not in ("largest", "all", "index"):
            raise ValueError("Enter a selection query and choose a supported task/selection mode")
        if selection_index < 0:
            raise ValueError("Selection index must be zero or greater")
        detector = native_detector()
        masks, boxes_out, summaries = [], [], []
        for frame in range(batch):
            result = detector.execute(clip=clip, image=images[frame:frame + 1, ..., :3], task=task,
                                      query=query, individual_masks=True, max_length=max_length)
            native_masks, boxes, _, text = result.args
            boxes = frame_boxes(boxes, 1)[0]
            # Keep the original index so invalid boxes never shift mask pairing.
            valid = []
            for index, box in enumerate(boxes):
                try:
                    bounds = box_bounds(box, width, height)
                except ValueError:
                    continue
                valid.append((index, bounds, box.get("label", "")))
            if selection == "largest" and valid:
                valid = [max(valid, key=lambda b: (b[1][2] - b[1][0]) * (b[1][3] - b[1][1]))]
            elif selection == "index":
                valid = [b for b in valid if b[0] == selection_index]
            chosen = torch.zeros((height, width), device=images.device, dtype=torch.float32)
            selected = []
            for index, (x0, y0, x1, y1), label in valid:
                if task == "detection":
                    chosen[y0:y1, x0:x1] = 1
                else:
                    if native_masks.ndim != 3 or native_masks.shape[1:] != (height, width) or index >= native_masks.shape[0]:
                        raise ValueError("WeVisOne returned masks that do not match its detection boxes")
                    matte = native_masks[index].to(chosen.device, dtype=chosen.dtype)
                    if not torch.isfinite(matte).all():
                        raise ValueError("WeVisOne returned a non-finite matte")
                    chosen = torch.maximum(chosen, matte.clamp(0, 1))
                selected.append({"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0, "label": label})
            masks.append(chosen)
            boxes_out.append(selected)
            summaries.append({"frame": frame, "detected": len(boxes), "selected": len(selected), "answer": text})
        report = {"query": query, "task": task, "frames": summaries,
                  "note": "No match produces an empty mask and no boxes. Review multiple matches and mask boundaries before refining."}
        return io.NodeOutput(torch.stack(masks), boxes_out, json.dumps(report, indent=2))


@dataclass(frozen=True)
class ImageRegion:
    source_shape: tuple
    image_index: int
    bounds: tuple[int, int, int, int]
    mask: torch.Tensor


class JWTFRegionCrop(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="JWTFRegionCrop", display_name="Region Crop (Refine)", category="JezzWTF/image",
            description="Crop one selected box or mask, add context padding and enlarge it for refinement. Keep the region output connected to Region Composite and supply the same original image there. Empty selections stop execution.",
            inputs=[io.Image.Input("images"),
                    io.Int.Input("image_index", default=0, min=0, max=999), io.Int.Input("region_index", default=0, min=0, max=999),
                    io.Float.Input("padding", default=0.25, min=0.0, max=2.0, step=0.05, tooltip="Extra context on each side, as a fraction of the selected box dimensions."),
                    io.Int.Input("long_edge", default=768, min=64, max=2048, step=16, tooltip="Refinement crop's long edge; both dimensions round to a 16-pixel grid."),
                    io.BoundingBox.Input("bboxes", optional=True), io.Mask.Input("mask", optional=True)],
            outputs=[io.Image.Output("crop"), io.Mask.Output("crop_mask"), io.Custom("JWTF_IMAGE_REGION").Output("region")],
        )

    @classmethod
    def execute(cls, images, image_index=0, region_index=0, padding=0.25, long_edge=768, bboxes=None, mask=None):
        batch, height, width = image_shape(images)
        if not 0 <= image_index < batch or region_index < 0:
            raise ValueError("The selected image or region index does not exist")
        if not math.isfinite(padding) or not 0 <= padding <= 2 or not 64 <= long_edge <= 2048 or long_edge % 16:
            raise ValueError("Use padding 0..2 and a crop long edge divisible by 16, between 64 and 2048")
        masks = source_mask(mask, batch, height, width, images.device)
        if bboxes is not None:
            boxes = frame_boxes(bboxes, batch)[image_index]
            if region_index >= len(boxes):
                raise ValueError("No selected region. Adjust Smart Select's query/index or supply a non-empty mask.")
            x0, y0, x1, y1 = box_bounds(boxes[region_index], width, height)
        elif masks is not None:
            coordinates = torch.nonzero(masks[image_index] > 0.1)
            if not len(coordinates):
                raise ValueError("No selected pixels. Paint or select a region before refining.")
            y0, x0 = coordinates.amin(dim=0).tolist()
            y1, x1 = (coordinates.amax(dim=0) + 1).tolist()
        else:
            raise ValueError("Region Crop needs bounding boxes or a non-empty selection mask")
        dx, dy = (x1 - x0) * padding, (y1 - y0) * padding
        x0, y0, x1, y1 = max(0, math.floor(x0 - dx)), max(0, math.floor(y0 - dy)), min(width, math.ceil(x1 + dx)), min(height, math.ceil(y1 + dy))
        coverage = torch.ones((1, y1 - y0, x1 - x0), device=images.device) if masks is None else masks[image_index:image_index + 1, y0:y1, x0:x1].clone()
        if not torch.any(coverage > 0):
            raise ValueError("The selected box contains no masked pixels; adjust the selection or mask")
        scale = long_edge / max(x1 - x0, y1 - y0)
        tw, th = max(16, round((x1 - x0) * scale / 16) * 16), max(16, round((y1 - y0) * scale / 16) * 16)
        crop = images[image_index:image_index + 1, y0:y1, x0:x1, :3]
        crop = upscale(crop.movedim(-1, 1), tw, th, "bicubic", "disabled").movedim(1, -1).clamp(0, 1)
        crop_mask = upscale(coverage[:, None], tw, th, "bilinear", "disabled")[:, 0].clamp(0, 1)
        region = ImageRegion(tuple(images.shape), image_index, (x0, y0, x1, y1), coverage)
        return io.NodeOutput(crop, crop_mask, region)


class JWTFRegionComposite(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="JWTFRegionComposite", display_name="Region Composite (Refine)", category="JezzWTF/image",
            description="Resize a refined crop back to its recorded region and blend through the original selection. Unselected frames, pixels outside the crop and original alpha channels are preserved.",
            inputs=[io.Image.Input("images", tooltip="The same original image batch supplied to Region Crop."),
                    io.Image.Input("refined_crop"), io.Custom("JWTF_IMAGE_REGION").Input("region"),
                    io.Int.Input("feather", default=16, min=0, max=128, tooltip="Blend softness in original-image pixels."),
                    io.Float.Input("opacity", default=1.0, min=0.0, max=1.0, step=0.05)],
            outputs=[io.Image.Output("image"), io.Mask.Output("blend_mask")],
        )

    @classmethod
    def execute(cls, images, refined_crop, region, feather=16, opacity=1.0):
        batch, height, width = image_shape(images)
        image_shape(refined_crop)
        if not torch.isfinite(refined_crop).all():
            raise ValueError("The refined crop contains non-finite pixels")
        if not isinstance(region, ImageRegion) or tuple(images.shape) != region.source_shape:
            raise ValueError("Region Composite needs the original source dimensions/batch and Region Crop's region output")
        if refined_crop.shape[0] != 1:
            raise ValueError("Refine one crop at a time before compositing")
        if not 0 <= feather <= 128 or not math.isfinite(opacity) or not 0 <= opacity <= 1:
            raise ValueError("Use feather 0..128 and opacity 0..1")
        x0, y0, x1, y1 = region.bounds
        w, h = x1 - x0, y1 - y0
        patch = upscale(refined_crop[..., :3].to(images.device).movedim(-1, 1), w, h, "bicubic", "disabled").movedim(1, -1).clamp(0, 1)
        amount = soften(region.mask.to(images.device), feather).clamp(0, 1)
        if feather:
            # Fade the rectangular crop boundary as well as the selection edge.
            xs = torch.arange(w, device=images.device, dtype=torch.float32)
            ys = torch.arange(h, device=images.device, dtype=torch.float32)
            ramp_x = torch.minimum(xs, w - 1 - xs).div(feather).clamp(0, 1)
            ramp_y = torch.minimum(ys, h - 1 - ys).div(feather).clamp(0, 1)
            amount = amount * ramp_y[:, None] * ramp_x[None, :]
        amount = amount * opacity
        result = images.clone()
        original = images[region.image_index:region.image_index + 1, y0:y1, x0:x1, :3]
        result[region.image_index:region.image_index + 1, y0:y1, x0:x1, :3] = original * (1 - amount[..., None]) + patch * amount[..., None]
        blend_mask = torch.zeros((batch, height, width), device=images.device, dtype=torch.float32)
        blend_mask[region.image_index:region.image_index + 1, y0:y1, x0:x1] = amount
        return io.NodeOutput(result, blend_mask)


NODES = [JWTFSmartSelect, JWTFRegionCrop, JWTFRegionComposite]
