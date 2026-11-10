from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch
from PIL import Image

from utility_core.draw_image import JWTFDrawImage, resolve_input_file
from utility_core.get_image import compute_mask
from utility_core.multi_load import JWTFMultiLoadImage, parse_names
from utility_core.set_get import PLACEHOLDER, STORE, JWTFGet, JWTFSet, SetGetStore
from utility_core.text_nodes import JWTFTextBox, build_edit_prompt, zero_out
from v3_helpers import hidden, legacy


# ------------------------------------------------------------ set / get

def test_store_roundtrip_and_overwrite() -> None:
    s = SetGetStore()
    s.set("k", 1, "Neon", "3")
    s.set("k", 2, "Gold", "4")
    assert s.get("k") == 2
    entry = s.entry("k")
    assert entry is not None and entry.color == "Gold" and entry.node_id == "4"
    assert s.keys() == ["k"]
    with pytest.raises(KeyError, match="not found"):
        s.get("missing")
    with pytest.raises(KeyError):
        s.get(PLACEHOLDER)


def test_set_get_nodes() -> None:
    marker = object()
    with hidden(JWTFSet, unique_id="7"):
        assert legacy(JWTFSet.execute("set_x", marker, "Neon")) == (marker,)
    assert legacy(JWTFGet.execute("set_x")) == (marker,)
    linked = object()
    assert legacy(JWTFGet.execute("set_x", set_link=linked)) == (linked,)
    assert legacy(JWTFGet.execute("anything", set_link=None)) == (None,)
    assert JWTFGet.validate_inputs("not-a-listed-key") is True
    assert STORE.entry("set_x") is not None


def test_get_is_changed_follows_set_version() -> None:
    s = SetGetStore()
    assert s.version("k") == 0
    s.set("k", 1)
    s.set("k", 2)
    assert s.version("k") == 2
    with hidden(JWTFSet, unique_id="7"):
        legacy(JWTFSet.execute("set_ver_probe", 1))
    before = JWTFGet.fingerprint_inputs("set_ver_probe", set_link=None)
    with hidden(JWTFSet, unique_id="7"):
        legacy(JWTFSet.execute("set_ver_probe", 2))
    assert JWTFGet.fingerprint_inputs("set_ver_probe") != before


# ------------------------------------------------------------ text

def test_text_box() -> None:
    assert legacy(JWTFTextBox.execute("a\nb")) == ("a\nb",)
    assert JWTFTextBox.fingerprint_inputs("abc") == "abc"


def test_edit_prompt() -> None:
    assert build_edit_prompt("  do x  ", True, "  keep y ", "comma") == "do x, keep y"
    assert build_edit_prompt("do x", True, "keep y", "space") == "do x keep y"
    assert build_edit_prompt("do x", True, "keep y", "newline") == "do x\nkeep y"
    assert build_edit_prompt("do x", False, "keep y") == "do x"
    assert build_edit_prompt("do x", True, "   ") == "do x"
    assert build_edit_prompt("do x", True, None).startswith("do x\nLeave")


def test_zero_out() -> None:
    cond = [[torch.ones(1, 2, 3), {"pooled_output": torch.ones(1, 3), "other": 5}]]
    out = zero_out(cond)
    assert torch.count_nonzero(out[0][0]) == 0
    assert torch.count_nonzero(out[0][1]["pooled_output"]) == 0
    assert out[0][1]["other"] == 5
    assert torch.count_nonzero(cond[0][1]["pooled_output"]) == 3  # original untouched


# ------------------------------------------------------------ get image

def test_get_image_masks() -> None:
    img = torch.zeros(1, 2, 2, 4)
    img[..., 3] = 1.0
    img[0, 0, 0, 3] = 0.0
    m = compute_mask(img, "Alpha Channel")
    assert m[0, 0, 0] == 1.0 and m[0, 1, 1] == 0.0
    assert torch.count_nonzero(compute_mask(img[..., :3], "Alpha Channel")) == 0
    white = torch.ones(1, 2, 2, 3)
    assert torch.allclose(compute_mask(white, "Luminance"), torch.zeros(1, 2, 2), atol=1e-6)
    assert torch.equal(compute_mask(white, "Blank", invert=True), torch.ones(1, 2, 2))
    grey = torch.full((1, 1, 1, 3), 0.5)
    assert compute_mask(grey, "Luminance", threshold=0.4)[0, 0, 0] == 1.0
    assert compute_mask(grey, "Luminance", threshold=0.6)[0, 0, 0] == 0.0


# ------------------------------------------------------------ draw image

def test_draw_image(tmp_path: Path) -> None:
    sub = tmp_path / "jezzwtf_draw"
    sub.mkdir()
    Image.new("RGBA", (8, 6), (255, 255, 255, 128)).save(sub / "flat_x.png")
    assert resolve_input_file("jezzwtf_draw/flat_x.png", str(tmp_path)) == str((sub / "flat_x.png").resolve())
    assert resolve_input_file("../etc/passwd", str(tmp_path)) is None
    assert resolve_input_file("jezzwtf_draw", str(tmp_path)) is None
    assert resolve_input_file("", str(tmp_path)) is None
    node = JWTFDrawImage
    image, mask = legacy(node.execute(64, 72, "transparent", ""))
    assert image.shape == (1, 72, 64, 3) and torch.all(mask == 1)
    image, mask = legacy(node.execute(64, 64, "white", ""))
    assert torch.all(image == 1) and torch.all(mask == 0)
    assert JWTFDrawImage.fingerprint_inputs(64, 64, "black", "") == "blank-64x64-black"


def test_draw_image_premultiply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import utility_core.draw_image as di

    Image.new("RGBA", (4, 4), (255, 255, 255, 51)).save(tmp_path / "f.png")
    monkeypatch.setattr(di, "input_dir", lambda: str(tmp_path))
    image, mask = legacy(JWTFDrawImage.execute(64, 64, "transparent", "f.png"))
    assert image.shape == (1, 4, 4, 3)
    assert abs(float(image[0, 0, 0, 0]) - 0.2) < 1e-6 and abs(float(mask[0, 0, 0]) - 0.8) < 1e-6
    image, _ = legacy(JWTFDrawImage.execute(64, 64, "white", "f.png"))
    assert float(image[0, 0, 0, 0]) == 1.0
    assert len(JWTFDrawImage.fingerprint_inputs(64, 64, "white", "f.png")) == 64


# ------------------------------------------------------------ multi load

def test_multi_load_parse() -> None:
    assert parse_names("not json") == []
    assert parse_names('{"a": 1}') == []
    assert parse_names(json.dumps(["a.png", 3, None, "b.png [input]"])) == ["a.png", "", "", "b.png [input]"]
    assert len(parse_names(json.dumps(["x"] * 40))) == 16


def test_multi_load_placeholders() -> None:
    out = legacy(JWTFMultiLoadImage.execute('[""]'))
    assert len(out) == 16 and all(t.shape == (1, 64, 64, 3) for t in out)
