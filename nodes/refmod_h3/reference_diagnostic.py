"""Compare a saved MOSS reference against the native encoder with the same inputs."""
from __future__ import annotations

import json

import torch
from comfy_api.latest import io

from . import _comfy, unified
from ._types import RefModError


NEW_SCENE_PROMPT = (
    "A new full-body photograph of the person shown in the reference images, walking left to right "
    "across a snowy railway platform, wearing a red winter coat and carrying a black suitcase. "
    "Wide establishing shot from several metres away, head and feet fully visible, side-on walking pose, "
    "railway tracks and a station behind them. Preserve the person's facial identity."
)


class JWTFRefModConditioningCheck(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="JWTFRefModConditioningCheck",
            display_name="RefMod Conditioning Check (MOSS)",
            category="JezzWTF/refmod",
            description="Build saved-reference and native MOSS edit conditioning from one bundle and one prompt. Sample both with the same model, seed and target to isolate reference handling from model/runtime behaviour.",
            inputs=[
                io.Clip.Input("clip"), io.Vae.Input("vae"),
                io.Combo.Input("refmod", options=unified.choices(), default=unified.NONE),
                io.String.Input("prompt", default=NEW_SCENE_PROMPT, multiline=True),
                io.String.Input("negative_prompt", default="", multiline=True),
                io.Combo.Input("edit_format", options=["Moss-Image-Edit", "ai-toolkit", "ai-toolkit (kv_cache off)"], default="Moss-Image-Edit"),
                io.Int.Input("output_width", default=1024, min=32, max=8192, step=16),
                io.Int.Input("output_height", default=768, min=32, max=8192, step=16),
            ],
            outputs=[
                io.Conditioning.Output("saved_positive"), io.Conditioning.Output("saved_negative"),
                io.Conditioning.Output("native_positive"), io.Conditioning.Output("native_negative"),
                io.Latent.Output("target"), io.Image.Output("reference_preview"), io.String.Output("report"),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, refmod=unified.NONE, **kwargs):
        return unified.JWTFUnifiedRefModApply.fingerprint_inputs(refmod_1=refmod)

    @classmethod
    def validate_inputs(cls, **kwargs):
        # Bundle lists change on disk; resolve the current name during execution.
        return True

    @classmethod
    def execute(cls, clip, vae, refmod, prompt, negative_prompt="", edit_format="Moss-Image-Edit",
                output_width=1024, output_height=768):
        if any(not 32 <= value <= 8192 or value % 16 for value in (output_width, output_height)):
            raise RefModError("MOSS output dimensions must be multiples of 16 between 32 and 8192")
        entry = unified.index().get(refmod)
        if entry is None:
            raise RefModError("Select a saved MOSS reference bundle in RefMod Conditioning Check")
        handler, latents, images = unified.load_refs(entry[0])
        if handler.key != "moss_image" or not images:
            raise RefModError("RefMod Conditioning Check currently requires a MOSS image bundle")
        native = getattr(_comfy.optional_module("comfy_extras.nodes_moss_image"), "TextEncodeMOSSImageEdit", None)
        if native is None:
            raise RefModError("Update ComfyUI: native Text Encode MOSS-Image Edit is required")
        saved_pos, saved_neg, _ = unified.JWTFUnifiedRefModApply.execute(
            unified.AUTO, refmod, clip=clip, prompt=prompt, negative_prompt=negative_prompt,
            ref_strength=1.0, ref_on_negative=True, edit_format=edit_format,
        ).args
        # The native path deliberately re-encodes the stored RGB pixels with the
        # connected VAE; it does not reuse our reference-conditioning builder.
        pictures = {f"image_{i:04d}": image for i, image in enumerate(images)}
        native_pos = native.execute(clip, prompt, edit_format, pictures, vae).args[0]
        native_neg = native.execute(clip, negative_prompt, edit_format, pictures, vae).args[0]
        # Same contract as native EmptyFlux2LatentImage. The output canvas is
        # independent of the references' dimensions, crop and pixel contents.
        target = {"samples": torch.zeros(1, 128, output_height // 16, output_width // 16,
                                         device=_comfy.intermediate_device())}
        native_refs = native_pos[0][1]["reference_latents"]
        deltas = []
        for saved, fresh in zip(latents, native_refs):
            if saved.shape == fresh.shape:
                deltas.append(float((saved.detach().cpu().float() - fresh.detach().cpu().float()).abs().max()))
            else:
                deltas.append(None)
        report = {
            "bundle": refmod, "reference_count": len(images), "edit_format": edit_format,
            "output_dimensions": [output_width, output_height],
            "saved_shapes": [list(lat.shape) for lat in latents],
            "native_shapes": [list(lat.shape) for lat in native_refs],
            "reference_latent_max_absolute_differences": deltas,
            "target_is_empty": bool(torch.count_nonzero(target["samples"]) == 0),
            "interpretation": "Compare both identity and the requested new pose/composition. A background swap alone does not pass this task. If only the saved path fails, inspect baking/VAE compatibility. If both fail, native conditioning also fails this task; that does not distinguish model capability from adapter/runtime problems. This report cannot score identity or establish that the feature works.",
            "round_trip_note": "Native references are re-encoded from the bundle's 8-bit RGB images. Small differences from the originally baked latent are expected. A different VAE can cause larger differences. The preview shows the first reference only.",
        }
        return io.NodeOutput(saved_pos, saved_neg, native_pos, native_neg, target, images[0], json.dumps(report, indent=2))


NODES = [JWTFRefModConditioningCheck]
