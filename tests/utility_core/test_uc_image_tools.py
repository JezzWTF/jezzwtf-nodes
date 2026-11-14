from __future__ import annotations

import json
from io import BytesIO

import numpy as np
import pytest
import torch
from PIL import Image

from utility_core import image_compare, image_saver, mask_editor, media_files


def test_comparison_batch_resize_and_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(media_files, "temp_dir", lambda: str(tmp_path))
    a = torch.zeros(2, 8, 12, 3)
    b = torch.ones(1, 4, 6, 3)
    result = image_compare.JWTFImageCompare.execute(a, b, torch.ones(1, 8, 12))
    difference, metrics = result.args
    assert difference.shape == a.shape and torch.all(difference == 1)
    report = json.loads(metrics)
    assert report["b_resized"] and report["frames"][0]["mae"] == 1
    assert report["frames"][0]["psnr_db"] == 0
    assert len(result.ui["jwtf_compare"][0]["frames"]) == 2
    assert "mask" in result.ui["jwtf_compare"][0]["frames"][0]
    assert torch.all(a == 0) and b.shape == (1, 4, 6, 3)


def test_identical_comparison_has_json_safe_infinite_psnr(tmp_path, monkeypatch):
    monkeypatch.setattr(media_files, "temp_dir", lambda: str(tmp_path))
    image = torch.rand(1, 8, 8, 3)
    result = image_compare.JWTFImageCompare.execute(image, image)
    assert not result.args[0].any()
    assert json.loads(result.args[1])["frames"][0]["psnr_db"] is None


def test_ssim_accounts_for_colour_and_structure():
    original = Image.fromarray(np.random.default_rng(8).integers(0, 256, (48, 48, 3), dtype=np.uint8))
    assert image_saver.similarity(original, original) == 1
    assert image_saver.similarity(original, Image.new("RGB", original.size, "white")) < 0.9
    assert image_saver.similarity(Image.new("RGB", (20, 20), "red"), Image.new("RGB", (20, 20), "blue")) < 0.8


@pytest.mark.parametrize("fmt", ["png", "webp", "jpeg", "tiff"])
def test_squeeze_real_encoding_meets_or_reports_target(fmt):
    image = Image.fromarray(np.random.default_rng(3).integers(0, 256, (48, 48, 3), dtype=np.uint8))
    data, report = image_saver.squeeze(image, fmt, 8, True, 90)
    with Image.open(BytesIO(data)) as decoded:
        assert decoded.size == image.size
        score = image_saver.similarity(image, decoded)
        assert score == pytest.approx(report["ssim"])
    assert report["target_met"] == (score >= image_saver.TARGETS[8])


def test_lossless_tier_webp_and_impossible_jpeg_are_explicit():
    image = Image.fromarray(np.random.default_rng(9).integers(0, 256, (32, 32, 3), dtype=np.uint8))
    data, report = image_saver.squeeze(image, "webp", 10, True, 90)
    assert report["encoding"] == "lossless" and report["target_met"]
    with Image.open(BytesIO(data)) as decoded:
        assert np.array_equal(np.asarray(image), np.asarray(decoded))
    _, report = image_saver.squeeze(image, "jpeg", 10, True, 90)
    assert not report["target_met"] and report["target"] == 1


def test_palette_png_preserves_pixels():
    image = Image.new("RGB", (20, 20), "red")
    data, _ = image_saver.squeeze(image, "png", 8, True, 90)
    with Image.open(BytesIO(data)) as decoded:
        assert np.array_equal(np.asarray(image), np.asarray(decoded.convert("RGB")))


def test_png_squeeze_preserves_alpha():
    pixels = np.zeros((12, 12, 4), dtype=np.uint8)
    pixels[..., 0] = 230
    pixels[:, 6:, 3] = 170
    image = Image.fromarray(pixels)
    data, _ = image_saver.squeeze(image, "png", 8, True, 90)
    with Image.open(BytesIO(data)) as decoded:
        assert np.array_equal(pixels, np.asarray(decoded.convert("RGBA")))


def test_saver_reserves_unique_files_and_embeds_workflow(tmp_path, monkeypatch):
    from v3_helpers import hidden
    monkeypatch.setattr(media_files, "output_dir", lambda: str(tmp_path))
    node = image_saver.JWTFImageSaver
    with hidden(node, prompt={"1": {"class_type": "Example"}}, extra_pnginfo={"workflow": {"nodes": []}}):
        out = node.execute(torch.zeros(2, 8, 8, 3), "images/test", "png", True, 8, 90, True)
    paths = out.args[1].splitlines()
    assert len(set(paths)) == 2
    with Image.open(paths[0]) as image:
        assert json.loads(image.info["workflow"]) == {"nodes": []}
        assert "1" in json.loads(image.info["prompt"])
    with pytest.raises(ValueError, match="inside"):
        media_files.reserve_output("../escape", "png")


def test_mask_painting_resizes_and_broadcasts_without_mutating_source(tmp_path, monkeypatch):
    path = tmp_path / "paint.png"
    Image.fromarray(np.array([[0, 255], [255, 0]], dtype=np.uint8)).save(path)
    monkeypatch.setattr(mask_editor, "resolve_input_file", lambda _: str(path))
    image = torch.zeros(2, 4, 4, 3)
    incoming = torch.ones(1, 4, 4)
    result = mask_editor.edited_mask(image, incoming, "paint.png")
    assert result.shape == (2, 4, 4)
    assert result[0, 0, 0] == 0 and result[0, -1, 0] == 1
    assert torch.equal(result[0], result[1]) and torch.all(incoming == 1)
    assert mask_editor.JWTFMaskEditor.fingerprint_inputs("paint.png") != "missing"


def test_mask_defaults_and_missing_file_are_explicit(monkeypatch):
    image = torch.zeros(1, 8, 12, 3)
    assert not mask_editor.edited_mask(image, None, "").any()
    monkeypatch.setattr(mask_editor, "resolve_input_file", lambda _: None)
    with pytest.raises(ValueError, match="missing"):
        mask_editor.edited_mask(image, None, "gone.png")


def test_mask_preview_remains_raw_when_output_is_inverted(tmp_path, monkeypatch):
    monkeypatch.setattr(media_files, "temp_dir", lambda: str(tmp_path))
    image = torch.zeros(1, 8, 8, 3)
    out = mask_editor.JWTFMaskEditor.execute(image, invert=True)
    assert torch.all(out.args[1] == 1)
    descriptor = out.ui["jwtf_mask_editor"][0]["mask"]
    with Image.open(tmp_path / descriptor["subfolder"] / descriptor["filename"]) as raw:
        assert not np.asarray(raw).any()


def test_pil_image_accepts_single_channel_frames():
    assert media_files.pil_image(torch.rand(4, 6, 1)).size == (6, 4)


def test_file_sha256_matches_hashlib_across_chunks(tmp_path):
    import hashlib
    from utility_core import _comfy
    data = bytes(range(256)) * 9000  # larger than one 1 MiB read
    path = tmp_path / "blob.bin"
    path.write_bytes(data)
    with open(path, "rb") as stream:
        assert _comfy.file_sha256(stream).hexdigest() == hashlib.sha256(data).hexdigest()
