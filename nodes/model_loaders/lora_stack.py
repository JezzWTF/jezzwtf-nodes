"""LoRA stack nodes: `JWTFLoraStack` (any LoRA under models/loras, visual stack editor) and
`JWTFLoraFolderStack` / `JWTFLoraFolderStackMulti` (every `.safetensors` in one configurable
subfolder of models/loras)."""
from __future__ import annotations

import os
from collections.abc import Callable, Mapping

import torch

from ._comfy import CATEGORY_LORA, folder_roots, log, lora_full_path
from .lora_stack_logic import (
    StateDictCache,
    applied_summary,
    apply_planned,
    folder_files,
    parse_lora_data,
    plan_stack,
    resolve_in_folder,
)

_CACHE = StateDictCache(max_entries=8)
EXTRA_MODELS = 4  # model_2 … model_5


def _load_sd(path: str) -> Mapping[str, torch.Tensor]:
    import comfy.utils  # type: ignore[import-not-found]

    return comfy.utils.load_torch_file(path, safe_load=True)


def apply_lora_stack(model: object, clip: object | None, lora_data: str,
                     resolve: Callable[[str], str | None]) -> tuple[object, object | None, str]:
    import comfy.sd  # type: ignore[import-not-found]

    plan = plan_stack(parse_lora_data(lora_data), resolve, clip is not None, log.info)
    for p in plan:
        sd = _CACHE.get(p.path, _load_sd)
        model, clip = apply_planned(comfy.sd.load_lora_for_models, model, clip, sd, p)
    return model, clip, applied_summary(plan)


def _mtime_signature(lora_data: str, resolve: Callable[[str], str | None]) -> str:
    parts = [lora_data]
    for e in parse_lora_data(lora_data):
        path = resolve(e.name)
        try:
            parts.append(f"{e.name}:{os.path.getmtime(path) if path else 0}")
        except OSError:
            parts.append(f"{e.name}:missing")
    return "|".join(parts)


def _lora_roots() -> list[str]:
    return folder_roots("loras")


class JWTFLoraStack:
    CATEGORY = CATEGORY_LORA
    RETURN_TYPES = ("MODEL", "CLIP")
    RETURN_NAMES = ("MODEL", "CLIP")
    FUNCTION = "apply"
    DESCRIPTION = "Apply a stack of LoRAs from models/loras, edited as a visual list."

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, tuple[object, ...]]]:
        return {
            "required": {
                "model": ("MODEL",),
                "lora_data": ("STRING", {"default": "{}", "multiline": False}),
            },
            "optional": {"clip": ("CLIP",)},
        }

    @classmethod
    def IS_CHANGED(cls, lora_data: str = "{}", **_: object) -> str:
        return _mtime_signature(str(lora_data), lora_full_path)

    def apply(self, model: object, lora_data: str, clip: object | None = None) -> tuple[object, object | None]:
        m, c, applied = apply_lora_stack(model, clip, lora_data, lora_full_path)
        log.info("JWTFLoraStack applied: %s", applied)
        return (m, c)


class JWTFLoraFolderStack:
    CATEGORY = CATEGORY_LORA
    RETURN_TYPES: tuple[str, ...] = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES: tuple[str, ...] = ("MODEL", "CLIP", "applied")
    FUNCTION = "apply"
    DESCRIPTION = "Apply LoRAs picked from one subfolder of models/loras, each with its own on/off and strength."

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, tuple[object, ...]]]:
        return {
            "required": {
                "model": ("MODEL",),
                "folder": ("STRING", {"default": "", "multiline": False,
                                      "tooltip": "Subfolder of models/loras (blank = the root folder itself)."}),
                "lora_data": ("STRING", {"default": "{}", "multiline": False}),
            },
            "optional": {"clip": ("CLIP",)},
        }

    @staticmethod
    def _resolver(folder: str) -> Callable[[str], str | None]:
        files = folder_files(_lora_roots(), folder)
        return lambda name: resolve_in_folder(files, name)

    @classmethod
    def IS_CHANGED(cls, folder: str = "", lora_data: str = "{}", **_: object) -> str:
        try:
            return f"{folder}|" + _mtime_signature(str(lora_data), cls._resolver(str(folder)))
        except ValueError as exc:
            return f"invalid:{exc}"

    def apply(self, model: object, folder: str, lora_data: str,
              clip: object | None = None) -> tuple[object, ...]:
        resolve = self._resolver(folder)
        m, c, applied = apply_lora_stack(model, clip, lora_data, resolve)
        return (m, c, applied)


class JWTFLoraFolderStackMulti(JWTFLoraFolderStack):
    RETURN_TYPES = ("MODEL", "CLIP", "STRING") + ("MODEL",) * EXTRA_MODELS
    RETURN_NAMES = ("MODEL", "CLIP", "applied") + tuple(f"MODEL {i}" for i in range(2, 2 + EXTRA_MODELS))
    DESCRIPTION = "Folder LoRA stack applied to up to five models (CLIP only on the first)."

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, tuple[object, ...]]]:
        spec = super().INPUT_TYPES()
        for i in range(2, 2 + EXTRA_MODELS):
            spec["optional"][f"model_{i}"] = ("MODEL",)
        return spec

    def apply(self, model: object, folder: str, lora_data: str,  # type: ignore[override]
              clip: object | None = None, **extra: object) -> tuple[object, ...]:
        resolve = self._resolver(folder)
        m, c, applied = apply_lora_stack(model, clip, lora_data, resolve)
        outs: list[object] = [m, c, applied]
        for i in range(2, 2 + EXTRA_MODELS):
            other = extra.get(f"model_{i}")
            outs.append(apply_lora_stack(other, None, lora_data, resolve)[0] if other is not None else None)
        return tuple(outs)
