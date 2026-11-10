"""LoRA stack nodes: `JWTFLoraStack` (any LoRA under models/loras, visual stack editor) and
`JWTFLoraFolderStack` / `JWTFLoraFolderStackMulti` (every `.safetensors` in one configurable
subfolder of models/loras)."""
from __future__ import annotations

import os
from collections.abc import Callable, Mapping

import torch

from comfy_api.latest import io

from ._comfy import folder_roots, log, lora_full_path
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


class JWTFLoraStack(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFLoraStack",
            display_name='LoRA Stack',
            category='JezzWTF/lora',
            description='Apply a stack of LoRAs from models/loras, edited as a visual list.',
            inputs=[
                io.Model.Input("model", tooltip="Diffusion model to patch with the enabled LoRAs."),
                io.String.Input("lora_data", default='{}', multiline=False, tooltip="JSON list of LoRA selections, enable flags and strengths written by the stack editor."),
                io.Clip.Input("clip", optional=True, tooltip="Optional text encoder to patch with the enabled LoRAs."),
            ],
            outputs=[
                io.Model.Output("MODEL", tooltip="Model with the enabled LoRAs applied in stack order."),
                io.Clip.Output("CLIP", tooltip="Text encoder with its LoRA patches applied, or empty when no encoder was connected."),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, lora_data: str = "{}", **_: object) -> str:
        return _mtime_signature(str(lora_data), lora_full_path)

    @classmethod
    def execute(cls, model: object, lora_data: str, clip: object | None = None) -> io.NodeOutput:
        m, c, applied = apply_lora_stack(model, clip, lora_data, lora_full_path)
        log.info("JWTFLoraStack applied: %s", applied)
        return io.NodeOutput(m, c)


class JWTFLoraFolderStack(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFLoraFolderStack",
            display_name='LoRA Folder Stack',
            category='JezzWTF/lora',
            description='Apply LoRAs picked from one subfolder of models/loras, each with its own on/off and strength.',
            inputs=[
                io.Model.Input("model", tooltip="Diffusion model to patch with enabled LoRAs from the selected folder."),
                io.String.Input("folder", default='', multiline=False, tooltip='Subfolder of models/loras (blank = the root folder itself).'),
                io.String.Input("lora_data", default='{}', multiline=False, tooltip="JSON list of LoRA selections, enable flags and strengths written by the stack editor."),
                io.Clip.Input("clip", optional=True, tooltip="Optional text encoder to patch with the enabled LoRAs."),
            ],
            outputs=[
                io.Model.Output("MODEL", tooltip="Model with the enabled LoRAs applied in stack order."),
                io.Clip.Output("CLIP", tooltip="Text encoder with its LoRA patches applied, or empty when no encoder was connected."),
                io.String.Output("applied", tooltip="Summary of applied LoRAs and their strengths."),
            ],
        )

    @staticmethod
    def _resolver(folder: str) -> Callable[[str], str | None]:
        files = folder_files(_lora_roots(), folder)
        return lambda name: resolve_in_folder(files, name)

    @classmethod
    def fingerprint_inputs(cls, folder: str = "", lora_data: str = "{}", **_: object) -> str:
        try:
            return f"{folder}|" + _mtime_signature(str(lora_data), cls._resolver(str(folder)))
        except ValueError as exc:
            return f"invalid:{exc}"

    @classmethod
    def execute(cls, model: object, folder: str, lora_data: str,
                clip: object | None = None) -> io.NodeOutput:
        resolve = cls._resolver(folder)
        m, c, applied = apply_lora_stack(model, clip, lora_data, resolve)
        return io.NodeOutput(m, c, applied)


class JWTFLoraFolderStackMulti(JWTFLoraFolderStack):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFLoraFolderStackMulti",
            display_name='LoRA Folder Stack (Multi-Model)',
            category='JezzWTF/lora',
            description='Folder LoRA stack applied to up to five models (CLIP only on the first).',
            inputs=[
                io.Model.Input("model", tooltip="First diffusion model to patch with the stack."),
                io.String.Input("folder", default='', multiline=False, tooltip='Subfolder of models/loras (blank = the root folder itself).'),
                io.String.Input("lora_data", default='{}', multiline=False, tooltip="JSON list of LoRA selections, enable flags and strengths written by the stack editor."),
                io.Clip.Input("clip", optional=True, tooltip="Optional text encoder patched alongside the first diffusion model."),
                io.Model.Input("model_2", optional=True, tooltip="Second model to patch with the same stack."),
                io.Model.Input("model_3", optional=True, tooltip="Third model to patch with the same stack."),
                io.Model.Input("model_4", optional=True, tooltip="Fourth model to patch with the same stack."),
                io.Model.Input("model_5", optional=True, tooltip="Fifth model to patch with the same stack."),
            ],
            outputs=[
                io.Model.Output("MODEL", tooltip="First model with the enabled LoRAs applied in stack order."),
                io.Clip.Output("CLIP", tooltip="Text encoder patched alongside the first model, or empty when no encoder was connected."),
                io.String.Output("applied", tooltip="Summary of the LoRAs applied to the first model, including their strengths."),
                io.Model.Output("MODEL 2", tooltip="Patched second model, or empty when its input is disconnected."),
                io.Model.Output("MODEL 3", tooltip="Patched third model, or empty when its input is disconnected."),
                io.Model.Output("MODEL 4", tooltip="Patched fourth model, or empty when its input is disconnected."),
                io.Model.Output("MODEL 5", tooltip="Patched fifth model, or empty when its input is disconnected."),
            ],
        )

    @classmethod
    def execute(cls, model: object, folder: str, lora_data: str,  # type: ignore[override]
                clip: object | None = None, **extra: object) -> io.NodeOutput:
        resolve = cls._resolver(folder)
        m, c, applied = apply_lora_stack(model, clip, lora_data, resolve)
        outs: list[object] = [m, c, applied]
        for i in range(2, 2 + EXTRA_MODELS):
            other = extra.get(f"model_{i}")
            outs.append(apply_lora_stack(other, None, lora_data, resolve)[0] if other is not None else None)
        return io.NodeOutput(*outs)


NODES = [JWTFLoraStack, JWTFLoraFolderStack, JWTFLoraFolderStackMulti]
