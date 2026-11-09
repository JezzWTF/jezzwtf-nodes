"""Text Box, Text Encode + Zero Neg, Title Font and Edit Prompt Template."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import torch

from ._types import CATEGORY_CONDITIONING, CATEGORY_UTILS, InputTypes

CondItem = list[object]  # [tensor, meta dict]
Conditioning = list[CondItem]


class ClipLike(Protocol):
    def tokenize(self, text: str) -> object: ...

    def encode_from_tokens_scheduled(self, tokens: object) -> Conditioning: ...


class JWTFTextBox:
    CATEGORY = CATEGORY_UTILS
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("TEXT",)
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {"required": {"text": ("STRING", {"multiline": True, "default": ""})}}

    @classmethod
    def IS_CHANGED(cls, text: str = "") -> str:
        return text

    def run(self, text: str) -> tuple[str]:
        return (text,)


def zero_out(cond: Sequence[Sequence[object]]) -> Conditioning:
    """Same result as core ConditioningZeroOut."""
    out: Conditioning = []
    for item in cond:
        tensor, meta = item[0], item[1]
        if not isinstance(tensor, torch.Tensor) or not isinstance(meta, dict):
            raise TypeError("unexpected conditioning layout")
        meta_copy: dict[str, object] = dict(meta)
        pooled = meta_copy.get("pooled_output")
        if isinstance(pooled, torch.Tensor):
            meta_copy["pooled_output"] = torch.zeros_like(pooled)
        lyrics = meta_copy.get("conditioning_lyrics")
        if isinstance(lyrics, torch.Tensor):
            meta_copy["conditioning_lyrics"] = torch.zeros_like(lyrics)
        out.append([torch.zeros_like(tensor), meta_copy])
    return out


class JWTFTextEncodeZeroNeg:
    CATEGORY = CATEGORY_CONDITIONING
    RETURN_TYPES = ("CONDITIONING", "CONDITIONING")
    RETURN_NAMES = ("POSITIVE", "NEGATIVE")
    FUNCTION = "run"
    MODES = ("Zero Out", "Empty String")

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {
                "clip": ("CLIP",),
                "positive": ("STRING", {"multiline": True, "default": ""}),
                "negative_mode": (list(cls.MODES), {"default": "Zero Out"}),
            }
        }

    def run(self, clip: ClipLike, positive: str, negative_mode: str) -> tuple[Conditioning, Conditioning]:
        pos = clip.encode_from_tokens_scheduled(clip.tokenize(positive))
        if negative_mode == "Empty String":
            neg = clip.encode_from_tokens_scheduled(clip.tokenize(""))
        else:
            neg = zero_out(pos)
        return (pos, neg)


TITLE_STYLES = ("Solid", "Gradient", "Neon", "Rainbow", "Outline", "Chrome")
TITLE_ANIMATIONS = ("None", "Pulse", "Float", "Shimmer", "Rainbow Shift", "Glow Pulse")


class JWTFTitleFont:
    CATEGORY = CATEGORY_UTILS
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("TEXT",)
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {
                "text": ("STRING", {"default": "TITLE", "multiline": False}),
                "font_size": ("INT", {"default": 56, "min": 8, "max": 240, "step": 1}),
                "bold": ("BOOLEAN", {"default": True}),
                "glow": ("BOOLEAN", {"default": True}),
                "style": (list(TITLE_STYLES), {"default": "Gradient"}),
                "color_a": ("STRING", {"default": "#ff3d7f"}),
                "color_b": ("STRING", {"default": "#3da5ff"}),
                "animate": (list(TITLE_ANIMATIONS), {"default": "None"}),
                "url": ("STRING", {"default": ""}),
            }
        }

    @classmethod
    def IS_CHANGED(cls, text: str = "", **_: object) -> str:
        return text

    def run(self, text: str, **_: object) -> tuple[str]:
        return (text,)


DEFAULT_INSTRUCTION = "Change the [subject] into [new subject]."
DEFAULT_SUFFIX = (
    "Leave everything else as it is: the composition, the lighting, the art style, "
    "every facial expression and the background must not change."
)
SEPARATORS: dict[str, str] = {"newline": "\n", "space": " ", "comma": ", "}


def build_edit_prompt(instruction: str, enable_suffix: bool = True, suffix: str | None = None,
                      separator: str = "newline") -> str:
    out = instruction.strip()
    sfx = (DEFAULT_SUFFIX if suffix is None else suffix).strip()
    if enable_suffix and sfx:
        out = (out + SEPARATORS.get(separator, "\n") + sfx).strip()
    return out


class JWTFEditPromptTemplate:
    CATEGORY = CATEGORY_UTILS
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {
                "edit_instruction": ("STRING", {"multiline": True, "dynamicPrompts": True,
                                                "default": DEFAULT_INSTRUCTION}),
            },
            "optional": {
                "enable_suffix": ("BOOLEAN", {"default": True}),
                "suffix": ("STRING", {"multiline": True, "default": DEFAULT_SUFFIX}),
                "separator": (list(SEPARATORS), {"default": "newline"}),
            },
        }

    def run(self, edit_instruction: str, enable_suffix: bool = True, suffix: str | None = None,
            separator: str = "newline") -> tuple[str]:
        return (build_edit_prompt(edit_instruction, enable_suffix, suffix, separator),)


NODE_CLASS_MAPPINGS = {
    "JWTFTextBox": JWTFTextBox,
    "JWTFTextEncodeZeroNeg": JWTFTextEncodeZeroNeg,
    "JWTFTitleFont": JWTFTitleFont,
    "JWTFEditPromptTemplate": JWTFEditPromptTemplate,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "JWTFTextBox": "Text Box",
    "JWTFTextEncodeZeroNeg": "Text Encode (Zero Negative)",
    "JWTFTitleFont": "Title Font",
    "JWTFEditPromptTemplate": "Edit Prompt Template",
}
