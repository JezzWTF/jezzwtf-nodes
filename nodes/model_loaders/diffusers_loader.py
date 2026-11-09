"""`JWTFDiffusersLoader`: load a Diffusers folder (or a single diffusion-model file) into
MODEL / CLIP / VAE, with a real attention-backend switch."""
from __future__ import annotations

import os

from ._comfy import CATEGORY_LOADERS, folder_roots, log
from .diffusers_logic import (
    FLASH_CHOICES,
    SAGE_CHOICES,
    backend_choice,
    collect_roots,
    describe_backend,
    diffusers_components,
    resolve_backend,
    resolve_model,
    scan_models,
)
from .relay_logic import AttnFn, install_override, make_backend_override


def model_roots() -> list[str]:
    registered: list[str] = []
    for key in ("unet", "diffusion_models", "diffusers"):
        registered.extend(folder_roots(key))
    bases: list[str] = []
    try:
        import folder_paths  # type: ignore[import-not-found]

        bases.append(str(folder_paths.models_dir))
        bases.append(os.path.join(str(folder_paths.get_user_directory()), "models"))
    except Exception:
        pass
    for key in ("checkpoints", "loras", "vae", "clip"):
        bases.extend(os.path.dirname(os.path.abspath(p)) for p in folder_roots(key))
    return collect_roots(registered, bases)


def list_models() -> list[str]:
    roots = model_roots()
    names = scan_models(roots)
    log.debug("Diffusers loader: %d roots, %d models (%s)", len(roots), len(names), names[:25])
    return names


def lookup_backend(choice: str) -> tuple[AttnFn, str] | None:
    try:
        from comfy.ldm.modules.attention import get_attention_function  # type: ignore[import-not-found]
    except ImportError:
        log.warning("This ComfyUI build has no attention registry; %s ignored", choice)
        return None
    found = resolve_backend(choice, lambda name: get_attention_function(name, None))
    if found is None:
        pkg = "sageattention" if choice.startswith("Sage") else "flash-attn"
        log.warning("%s is not available in this ComfyUI (install `%s` and restart); using the default attention",
                    choice, pkg)
    return found


_warned: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    if key not in _warned:
        _warned.add(key)
        log.warning(message)


def apply_backend(model: object, sage: str, flash: str) -> object:
    choice = backend_choice(sage, flash)
    if choice is None:
        return model
    found = lookup_backend(choice)
    if found is None:
        return model
    fn, resolved = found
    is_flash = choice.startswith("Flash")
    patched = model.clone()  # type: ignore[attr-defined]
    install_override(patched.model_options, lambda prev: make_backend_override(
        fn, prev, supports_mask=not is_flash,
        on_masked=lambda: _warn_once(
            choice, f"{choice} cannot take an attention mask (Prompt Relay bias or padding); "
                    "those calls use the default attention")))
    log.info("Diffusers loader: attention backend -> %s", describe_backend(choice, resolved))
    return patched


def _load_merged(paths: list[str]) -> dict[str, object]:
    """One state dict from every shard of a component."""
    import comfy.utils  # type: ignore[import-not-found]

    merged: dict[str, object] = {}
    for p in paths:
        merged.update(comfy.utils.load_torch_file(p, safe_load=True))
    return merged


def _load_diffusion_model(paths: list[str]) -> object:
    import comfy.sd  # type: ignore[import-not-found]

    if len(paths) == 1:
        return comfy.sd.load_diffusion_model(paths[0])
    model = comfy.sd.load_diffusion_model_state_dict(_load_merged(paths))
    if model is None:
        raise RuntimeError(f"Could not detect the model type of the sharded weights starting at {paths[0]}")
    return model


def _load_text_encoders(encoders: list[list[str]]) -> object:
    import comfy.sd  # type: ignore[import-not-found]

    if all(len(shards) == 1 for shards in encoders):
        return comfy.sd.load_clip([shards[0] for shards in encoders], embedding_directory=None)
    return comfy.sd.load_text_encoder_state_dicts([_load_merged(shards) for shards in encoders],
                                                  embedding_directory=None)


class JWTFDiffusersLoader:
    CATEGORY = CATEGORY_LOADERS
    RETURN_TYPES = ("MODEL", "CLIP", "VAE")
    RETURN_NAMES = ("MODEL", "CLIP", "VAE")
    FUNCTION = "load"
    DESCRIPTION = "Load a Diffusers-layout folder or a single diffusion-model file, with an optional attention backend."

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, tuple[object, ...]]]:
        return {
            "required": {
                "model_name": (list_models(),),
                "sageattention_version": (SAGE_CHOICES, {"default": "None"}),
                "flashattention_version": (FLASH_CHOICES, {"default": "None"}),
            }
        }

    def load(self, model_name: str, sageattention_version: str = "None",
             flashattention_version: str = "None") -> tuple[object, object | None, object | None]:
        import comfy.sd  # type: ignore[import-not-found]

        path = resolve_model(model_roots(), model_name)
        if path is None:
            raise FileNotFoundError(f"Diffusion model not found: {model_name}")
        clip: object | None = None
        vae: object | None = None
        if os.path.isdir(path):
            parts = diffusers_components(path)
            if not parts.unet:
                raise FileNotFoundError(
                    f"No diffusion_pytorch_model weights in {path} (looked in transformer/, unet/ and the folder itself)")
            model = _load_diffusion_model(parts.unet)
            if parts.encoders:
                clip = _load_text_encoders(parts.encoders)
            if parts.vae:
                vae = comfy.sd.VAE(sd=_load_merged(parts.vae))
        else:
            model = comfy.sd.load_diffusion_model(path)
        return apply_backend(model, sageattention_version, flashattention_version), clip, vae
