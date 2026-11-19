from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import torch

from utility_core import smart_selection as smart


def detector(monkeypatch, boxes, masks):
    calls = []

    class Native:
        @classmethod
        def execute(cls, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(args=(masks, [boxes], "[]", "native answer"))

    monkeypatch.setattr(smart, "native_detector", lambda: Native)
    return calls


def test_selection_keeps_native_box_mask_pairing_and_processes_frames(monkeypatch):
    boxes = [{"x": -10, "y": 0, "width": 2, "height": 2},
             {"x": 1, "y": 1, "width": 3, "height": 3},
             {"x": 4, "y": 2, "width": 6, "height": 6}]
    masks = torch.stack([torch.ones(10, 12), torch.full((10, 12), .3), torch.full((10, 12), .8)])
    calls = detector(monkeypatch, boxes, masks)
    mask, found, report = smart.JWTFSmartSelect.execute(None, torch.zeros(2, 10, 12, 3), "face").args
    assert len(calls) == 2 and all(c["individual_masks"] is True for c in calls)
    assert calls[0]["query"] == "face" and calls[0]["task"] == "segmentation"
    assert mask.shape == (2, 10, 12) and torch.allclose(mask, torch.full_like(mask, .8))
    assert found[0][0]["x"] == 4 and found[1] == found[0]
    assert json.loads(report)["frames"][0]["selected"] == 1


def test_index_and_all_selection_use_original_detection_indices(monkeypatch):
    boxes = [{"x": 0, "y": 0, "width": 2, "height": 2}, {"x": 3, "y": 2, "width": 4, "height": 4}]
    masks = torch.zeros(2, 8, 8)
    masks[0, :2, :2], masks[1, 2:6, 3:7] = .4, .9
    detector(monkeypatch, boxes, masks)
    image = torch.zeros(1, 8, 8, 3)
    selected = smart.JWTFSmartSelect.execute(None, image, "face", selection="index", selection_index=1).args
    assert torch.equal(selected[0][0], masks[1])
    combined = smart.JWTFSmartSelect.execute(None, image, "face", selection="all").args
    assert torch.equal(combined[0][0], masks.amax(0)) and len(combined[1][0]) == 2
    missing = smart.JWTFSmartSelect.execute(None, image, "face", selection="index", selection_index=9).args
    assert not missing[0].any() and missing[1] == [[]]


def test_detection_rectangles_no_match_and_nonfinite_mattes(monkeypatch):
    image = torch.zeros(1, 8, 8, 3)
    detector(monkeypatch, [{"x": 2, "y": 1, "width": 3, "height": 4}], torch.zeros(1, 8, 8))
    result = smart.JWTFSmartSelect.execute(None, image, "face", task="detection").args
    assert result[0].sum() == 12
    detector(monkeypatch, [], torch.zeros(1, 8, 8))
    empty = smart.JWTFSmartSelect.execute(None, image, "face").args
    assert empty[1] == [[]] and not empty[0].any()
    detector(monkeypatch, [{"x": 0, "y": 0, "width": 2, "height": 2}], torch.full((1, 8, 8), float("nan")))
    with pytest.raises(ValueError, match="non-finite"):
        smart.JWTFSmartSelect.execute(None, image, "face")


def test_crop_clamps_padding_and_composite_preserves_other_frames_alpha_and_background():
    image = torch.zeros(2, 80, 100, 4)
    image[..., 3] = .7
    image[0, ..., :3] = .2
    boxes = [[], [{"x": 70, "y": 50, "width": 40, "height": 40}]]
    crop, crop_mask, region = smart.JWTFRegionCrop.execute(image, image_index=1, padding=.5, long_edge=128, bboxes=boxes).args
    assert region.bounds == (55, 35, 100, 80)
    assert crop.shape == (1, 128, 128, 3) and crop_mask.shape == (1, 128, 128)
    assert torch.equal(image[..., 3], torch.full((2, 80, 100), .7))
    output, blend = smart.JWTFRegionComposite.execute(image, torch.ones_like(crop), region, feather=0).args
    assert torch.equal(output[0], image[0])
    assert torch.equal(output[..., 3], image[..., 3])
    assert torch.equal(output[1, :35], image[1, :35]) and torch.equal(output[1, :, :55], image[1, :, :55])
    assert output[1, 40:70, 60:90, :3].min().item() == pytest.approx(1, abs=1e-5)
    assert blend[0].sum() == 0
    assert torch.equal(image[1, ..., :3], torch.zeros(80, 100, 3)), "compositing must not mutate the source"


def test_mask_only_crop_and_feathered_recomposition():
    image = torch.zeros(1, 80, 100, 3)
    mask = torch.zeros(1, 80, 100)
    mask[:, 25:45, 30:60] = 1
    crop, _, region = smart.JWTFRegionCrop.execute(image, mask=mask, padding=.5, long_edge=128).args
    assert region.bounds == (15, 15, 75, 55)
    output, blend = smart.JWTFRegionComposite.execute(image, torch.ones_like(crop), region, feather=3).args
    assert output[0, 35, 45].min() > .99
    assert 0 < output[0, 24, 45, 0] < 1
    assert output[0, 15].sum() == 0 and output[0, :15].sum() == 0
    assert torch.allclose(output[..., 0], blend)
    unchanged = smart.JWTFRegionComposite.execute(image, torch.ones_like(crop), region, opacity=0).args[0]
    assert torch.equal(unchanged, image)


def test_empty_selection_and_wrong_source_stop_before_whole_image_refinement():
    image = torch.zeros(1, 32, 32, 3)
    with pytest.raises(ValueError, match="No selected region"):
        smart.JWTFRegionCrop.execute(image, bboxes=[[]])
    with pytest.raises(ValueError, match="No selected pixels"):
        smart.JWTFRegionCrop.execute(image, mask=torch.zeros(1, 32, 32))
    with pytest.raises(ValueError, match="match the source"):
        smart.JWTFRegionCrop.execute(image, mask=torch.ones(1, 8, 8))
    crop, _, region = smart.JWTFRegionCrop.execute(image, bboxes=[[{"x": 5, "y": 5, "width": 10, "height": 10}]]).args
    with pytest.raises(ValueError, match="original source"):
        smart.JWTFRegionComposite.execute(torch.zeros(1, 64, 64, 3), crop, region)
    with pytest.raises(ValueError, match="non-finite pixels"):
        smart.JWTFRegionComposite.execute(image, torch.full_like(crop, float("nan")), region)


def test_missing_native_support_has_actionable_error(monkeypatch):
    def missing(name):
        raise ImportError("not installed")
    monkeypatch.setattr(smart.importlib, "import_module", missing)
    with pytest.raises(RuntimeError, match="Update ComfyUI"):
        smart.native_detector()
