"""Text Box, Text Encode + Zero Neg, Title Font and Edit Prompt Template."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import torch

from comfy_api.latest import io


CondItem = list[object]  # [tensor, meta dict]
Conditioning = list[CondItem]


class ClipLike(Protocol):
    def tokenize(self, text: str) -> object: ...

    def encode_from_tokens_scheduled(self, tokens: object) -> Conditioning: ...


class JWTFTextBox(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFTextBox",
            display_name='Text Box',
            category='JezzWTF/utils',
            inputs=[
                io.String.Input("text", default='', multiline=True),
            ],
            outputs=[
                io.String.Output("TEXT"),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, text: str = "") -> str:
        return text

    @classmethod
    def execute(cls, text: str) -> io.NodeOutput:
        return io.NodeOutput(text)


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


class JWTFTextEncodeZeroNeg(io.ComfyNode):
    MODES = ("Zero Out", "Empty String")

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFTextEncodeZeroNeg",
            display_name='Text Encode (Zero Negative)',
            category='JezzWTF/conditioning',
            inputs=[
                io.Clip.Input("clip"),
                io.String.Input("positive", default='', multiline=True),
                io.Combo.Input("negative_mode", options=list(cls.MODES), default=cls.MODES[0]),
            ],
            outputs=[
                io.Conditioning.Output("POSITIVE"),
                io.Conditioning.Output("NEGATIVE"),
            ],
        )

    @classmethod
    def execute(cls, clip: ClipLike, positive: str, negative_mode: str) -> io.NodeOutput:
        pos = clip.encode_from_tokens_scheduled(clip.tokenize(positive))
        if negative_mode == "Empty String":
            neg = clip.encode_from_tokens_scheduled(clip.tokenize(""))
        else:
            neg = zero_out(pos)
        return io.NodeOutput(pos, neg)


TITLE_STYLES = ("Solid", "Gradient", "Neon", "Rainbow", "Outline", "Chrome")
TITLE_ANIMATIONS = ("None", "Pulse", "Float", "Shimmer", "Rainbow Shift", "Glow Pulse")


class JWTFTitleFont(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFTitleFont",
            display_name='Title Font',
            category='JezzWTF/utils',
            inputs=[
                io.String.Input("text", default='TITLE', multiline=False),
                io.Int.Input("font_size", default=56, min=8, max=240, step=1),
                io.Boolean.Input("bold", default=True),
                io.Boolean.Input("glow", default=True),
                io.Combo.Input("style", options=list(TITLE_STYLES), default='Gradient'),
                io.String.Input("color_a", default='#ff3d7f'),
                io.String.Input("color_b", default='#3da5ff'),
                io.Combo.Input("animate", options=list(TITLE_ANIMATIONS), default='None'),
                io.String.Input("url", default=''),
            ],
            outputs=[
                io.String.Output("TEXT"),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, text: str = "", **_: object) -> str:
        return text

    @classmethod
    def execute(cls, text: str, **_: object) -> io.NodeOutput:
        return io.NodeOutput(text)


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


class JWTFEditPromptTemplate(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFEditPromptTemplate",
            display_name='Edit Prompt Template',
            category='JezzWTF/utils',
            inputs=[
                io.String.Input("edit_instruction", default='Change the [subject] into [new subject].', multiline=True, dynamic_prompts=True),
                io.Boolean.Input("enable_suffix", default=True, optional=True),
                io.String.Input("suffix", default='Leave everything else as it is: the composition, the lighting, the art style, every facial expression and the background must not change.', multiline=True, optional=True),
                io.Combo.Input("separator", options=list(SEPARATORS), default='newline', optional=True),
            ],
            outputs=[
                io.String.Output("prompt"),
            ],
        )

    @classmethod
    def execute(cls, edit_instruction: str, enable_suffix: bool = True, suffix: str | None = None,
            separator: str = "newline") -> io.NodeOutput:
        return io.NodeOutput(build_edit_prompt(edit_instruction, enable_suffix, suffix, separator))


NODES = [JWTFTextBox, JWTFTextEncodeZeroNeg, JWTFTitleFont, JWTFEditPromptTemplate]
