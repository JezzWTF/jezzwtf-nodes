from __future__ import annotations

from pathlib import Path

import pytest
import torch

import utility_core.get_image as gi
from utility_core.get_image import JWTFGetImage
from utility_core.text_nodes import Conditioning, JWTFEditPromptTemplate, JWTFTextEncodeZeroNeg


class FakeClip:
    def __init__(self) -> None:
        self.tokenized: list[str] = []

    def tokenize(self, text: str) -> str:
        self.tokenized.append(text)
        return text

    def encode_from_tokens_scheduled(self, tokens: object) -> Conditioning:
        fill = 0.0 if tokens == "" else 1.0
        return [[torch.full((1, 2, 3), fill), {"pooled_output": torch.full((1, 3), fill), "k": "v"}]]


def test_text_encode_zero_out() -> None:
    clip = FakeClip()
    pos, neg = JWTFTextEncodeZeroNeg().run(clip, "a cat", "Zero Out")
    assert clip.tokenized == ["a cat"]
    assert torch.count_nonzero(pos[0][0]) == 6
    assert torch.count_nonzero(neg[0][0]) == 0 and torch.count_nonzero(neg[0][1]["pooled_output"]) == 0
    assert neg[0][1]["k"] == "v" and torch.count_nonzero(pos[0][1]["pooled_output"]) == 3


def test_text_encode_empty_string_mode_encodes_blank() -> None:
    clip = FakeClip()
    _, neg = JWTFTextEncodeZeroNeg().run(clip, "a cat", "Empty String")
    assert clip.tokenized == ["a cat", ""]
    assert torch.count_nonzero(neg[0][0]) == 0


def test_text_encode_node_shape() -> None:
    assert JWTFTextEncodeZeroNeg.RETURN_NAMES == ("POSITIVE", "NEGATIVE")
    modes = JWTFTextEncodeZeroNeg.INPUT_TYPES()["required"]["negative_mode"][0]
    assert modes == ["Zero Out", "Empty String"]
    assert not hasattr(JWTFTextEncodeZeroNeg, "IS_CHANGED")


def test_edit_prompt_node_defaults() -> None:
    spec = JWTFEditPromptTemplate.INPUT_TYPES()
    assert spec["required"]["edit_instruction"][1]["dynamicPrompts"] is True
    assert spec["optional"]["separator"][0] == ["newline", "space", "comma"]
    (out,) = JWTFEditPromptTemplate().run("  swap the hat  ", enable_suffix=False)
    assert out == "swap the hat"


def test_get_image_run_writes_two_previews(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gi, "temp_dir", lambda: str(tmp_path))
    img = torch.rand(2, 8, 6, 4)
    out = JWTFGetImage().run(img, mask_mode="Alpha Channel")
    rgb, mask = out["result"]
    assert rgb.shape == (2, 8, 6, 3) and mask.shape == (2, 8, 6)
    assert torch.allclose(mask, 1.0 - img[..., 3])
    entries = out["ui"][gi.UI_KEY]
    assert [e["kind"] for e in entries] == ["image", "mask"]
    assert all(e["type"] == "temp" and e["subfolder"] == "" and (tmp_path / e["filename"]).is_file() for e in entries)
    assert entries[0]["filename"].endswith("_img.png") and entries[1]["filename"].endswith("_mask.png")
    assert JWTFGetImage.OUTPUT_NODE and "images" not in out["ui"]
