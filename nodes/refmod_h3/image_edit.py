"""One-node MiniMax H3 image edit / generate (spec section 11)."""
from __future__ import annotations

import logging
import math

import torch

from . import _comfy
from ._types import CATEGORY_REFMOD, InputTypes, RefModError

log = logging.getLogger("jezzwtf.refmod_h3")

CORE_NODE = "MiniMaxH3ImageToVideo"
PH3_NODE = "PH3ImageConditioning"        # core p-h3-image text-to-image / edit conditioning (ComfyUI 0.44+)
SIGMA_SHIFT_NODE = "MiniMaxH3SigmaShift"
PH3_VAE_CLASS = "PH3ImageVAE"
RESIZE_METHODS = ("lanczos", "bicubic", "bilinear", "area", "nearest-exact")
PROGRESS_EVENT = "jezzwtf.progress"
DEFAULT_SIZE = (1344, 768)


def snap32(v: float) -> int:
    return max(32, int(round(v / 32.0)) * 32)


def megapixel_size(w: int, h: int, megapixels: float) -> tuple[int, int]:
    s = math.sqrt(megapixels * 1024 * 1024 / max(1, w * h))
    return snap32(w * s), snap32(h * s)


def _sampler_lists() -> tuple[list[str], list[str]]:
    samplers = _comfy.optional_module("comfy.samplers")
    if samplers is None:
        return ["euler"], ["simple"]
    return list(samplers.KSampler.SAMPLERS), list(samplers.KSampler.SCHEDULERS)


def _core_node_class(name: str = CORE_NODE) -> type | None:
    nodes = _comfy.comfy_nodes()
    if nodes is None:
        return None
    cls = nodes.NODE_CLASS_MAPPINGS.get(name)
    return cls if isinstance(cls, type) else None


def is_ph3_image_vae(vae: object) -> bool:
    """True for the p-h3-image single-frame VAE (the image-model variant of MiniMax H3)."""
    return type(getattr(vae, "first_stage_model", None)).__name__ == PH3_VAE_CLASS


def ensure_unit_shift(model: object) -> object:
    """p-h3-image needs ``ModelSamplingMiniMaxH3`` at 1.0 / 1.0; patch the model only when it is not already."""
    try:
        ms = model.get_model_object("model_sampling")  # type: ignore[attr-defined]
        if float(getattr(ms, "shift", 1.0)) == 1.0 and getattr(ms, "audio_shift", 1.0) in (1.0, None):
            return model
    except Exception:
        return model
    cls = _core_node_class(SIGMA_SHIFT_NODE)
    if cls is None:
        return model
    try:
        patched = _comfy.call_node(cls, model=model, shift_video=1.0, shift_audio=1.0)[0]
    except Exception as exc:
        log.warning("H3 Image Edit: could not set the p-h3-image sigma shift (%s)", exc)
        return model
    log.info("H3 Image Edit: p-h3-image sampled with ModelSamplingMiniMaxH3 1.0 / 1.0")
    return patched


def video_part(samples: object) -> torch.Tensor:
    """The picture stream of an H3 AV latent (nested video + audio); plain latents pass through."""
    if getattr(samples, "is_nested", False):
        return samples.unbind()[0]  # type: ignore[attr-defined, no-any-return]
    return samples  # type: ignore[return-value]


def _call_core(cls: type, **kwargs: object) -> tuple[object, dict[str, torch.Tensor]]:
    """Run a core conditioning node (V3 ``execute`` or V1 ``FUNCTION``), keeping supported kwargs.

    Returns ``(positive, latent)``."""
    try:
        result = _comfy.call_node(cls, **kwargs)
    except AttributeError as exc:
        raise RefModError(f"{cls.__name__} has no callable entry point") from exc
    if len(result) < 2:
        raise RefModError(f"{cls.__name__} returned an unexpected value")
    positive, latent = result[0], result[1]
    if not isinstance(latent, dict):
        raise RefModError(f"{cls.__name__} did not return a latent")
    return positive, latent  # type: ignore[return-value]


class JWTFH3ImageEdit:
    CATEGORY = CATEGORY_REFMOD
    RETURN_TYPES = ("IMAGE", "IMAGE", "CONDITIONING", "LATENT", "INT", "INT")
    RETURN_NAMES = ("image", "native_res", "positive", "latent", "width", "height")
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        samplers, schedulers = _sampler_lists()
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "prompt": ("STRING", {"multiline": True, "dynamicPrompts": True}),
                "width": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 8}),
                "frame_length": ("INT", {"default": 1, "min": 1, "max": 257}),
                "batch_index": ("INT", {"default": 0, "min": 0, "max": 256}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2 ** 64 - 1}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 150}),
                "cfg": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "sampler_name": (samplers,),
                "scheduler": (schedulers,),
                "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": {
                "image": ("IMAGE",),
                "last_frame": ("IMAGE",),
                "megapixels": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 8.0, "step": 0.01}),
                "resize_back_method": (list(RESIZE_METHODS), {"default": "lanczos"}),
            },
            "hidden": {"prompt_id": "PROMPT_ID"},
        }

    def run(self, model: object, clip: object, vae: object, prompt: str, width: int, height: int,
            frame_length: int, batch_index: int, seed: int, steps: int, cfg: float, sampler_name: str,
            scheduler: str, denoise: float, image: torch.Tensor | None = None,
            last_frame: torch.Tensor | None = None, megapixels: float = 1.0,
            resize_back_method: str = "lanczos", prompt_id: str | None = None
            ) -> tuple[torch.Tensor, torch.Tensor, object, dict[str, torch.Tensor], int, int]:
        def progress(pct: int, stage: str) -> None:
            _comfy.send_sync(PROGRESS_EVENT, {"percent": pct, "stage": stage, "prompt_id": prompt_id})

        ph3 = is_ph3_image_vae(vae)
        core = _core_node_class(PH3_NODE if ph3 else CORE_NODE)
        if core is None:
            if ph3:
                raise RefModError(f"this ComfyUI build has no {PH3_NODE} node; update ComfyUI for p-h3-image support")
            raise RefModError(f"this ComfyUI build has no {CORE_NODE} node; update ComfyUI for MiniMax H3 support")
        edit = isinstance(image, torch.Tensor) and image.numel() > 0
        first: torch.Tensor | None = None
        if width > 0 and height > 0:
            tw, th = snap32(width), snap32(height)
            first = image if edit else None
        elif edit:
            assert image is not None
            tw, th = megapixel_size(int(image.shape[2]), int(image.shape[1]), float(megapixels))
            first = _comfy.common_upscale(image[..., :3].movedim(-1, 1), tw, th, "nearest-exact", "center").movedim(1, -1)
        else:
            tw, th = DEFAULT_SIZE
        progress(10, "conditioning")
        has_last = isinstance(last_frame, torch.Tensor) and last_frame.numel() > 0
        if ph3:
            # still-image model: image_1 is edited, any further picture rides along as a reference
            pictures: dict[str, torch.Tensor] = {}
            if first is not None:
                pictures["image_1"] = first
            if has_last and first is not None:
                assert last_frame is not None
                pictures["image_2"] = last_frame
            elif has_last:
                log.warning("H3 Image Edit: last_frame needs an image to edit; ignored")
            kwargs: dict[str, object] = {"clip": clip, "vae": vae, "prompt": prompt, "width": tw, "height": th,
                                         "images": pictures or None}
            model = ensure_unit_shift(model)
        else:
            kwargs = {"clip": clip, "vae": vae, "prompt": prompt, "width": tw, "height": th,
                      "length": int(frame_length)}
            if first is not None:
                kwargs["first_frame"] = first
            if has_last:
                kwargs["last_frame"] = last_frame
        positive, latent = _call_core(core, **kwargs)
        nodes = _comfy.comfy_nodes()
        negative: object = positive
        # CFG 1.0 never evaluates the negative (core drops it), so the empty-prompt encode is skipped there
        if nodes is not None and abs(float(cfg) - 1.0) > 1e-6:
            try:
                negative = nodes.CLIPTextEncode().encode(clip, "")[0]
            except Exception as exc:
                log.warning("H3 Image Edit: empty negative failed (%s); using the positive", exc)
        sample = _comfy.optional_module("comfy.sample")
        if sample is None:
            raise RefModError("comfy.sample unavailable")
        progress(30, "sampling")
        noise = sample.prepare_noise(latent["samples"], seed)
        samples = sample.sample(model, noise, steps, cfg, sampler_name, scheduler, positive, negative,
                                latent["samples"], denoise=denoise, seed=seed)
        out_latent = dict(latent)
        out_latent["samples"] = samples
        progress(85, "decoding")
        decoded = vae.decode(video_part(samples))  # type: ignore[attr-defined]
        if decoded.dim() == 5:
            decoded = decoded.reshape(-1, *decoded.shape[-3:])
        progress(92, "decoded")
        n = int(decoded.shape[0])
        native = decoded[min(max(batch_index, 0), n - 1)].unsqueeze(0)
        final = native
        if edit:
            assert image is not None
            progress(96, "resize")
            ow, oh = int(image.shape[2]), int(image.shape[1])
            if (ow, oh) != (int(native.shape[2]), int(native.shape[1])):
                final = _comfy.common_upscale(native.movedim(-1, 1), ow, oh, resize_back_method, "center").movedim(1, -1)
        progress(100, "done")
        return final.clamp(0, 1), native, positive, out_latent, int(final.shape[2]), int(final.shape[1])


NODE_CLASS_MAPPINGS = {"JWTFH3ImageEdit": JWTFH3ImageEdit}
NODE_DISPLAY_NAME_MAPPINGS = {"JWTFH3ImageEdit": "MiniMax H3 Image Edit"}
