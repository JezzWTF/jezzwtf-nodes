from __future__ import annotations

import json
import os

import pytest
import torch

from fakes import FakeClip
from refmod_h3 import unified
from refmod_h3._types import RefModError
from refmod_h3.reference_diagnostic import JWTFRefModConditioningCheck
from test_rm_reference_families import FamilyVAE


def test_diagnostic_cache_changes_when_selected_bundle_is_replaced(refmod_root):
    handler = unified.HANDLERS["moss_image"]
    result = unified.JWTFUnifiedRefModBake.execute(
        "moss_image", torch.ones(1, 64, 64, 3), "replaced", 0, "", False, vae=FamilyVAE(handler),
    )
    before = JWTFRefModConditioningCheck.fingerprint_inputs(refmod="moss_image/replaced")
    path = result.args[0]
    stamp = os.stat(path).st_mtime
    os.utime(path, (stamp + 10, stamp + 10))
    after = JWTFRefModConditioningCheck.fingerprint_inputs(refmod="moss_image/replaced")
    assert before != after, "Replacing a selected bundle must invalidate the diagnostic and its downstream renders"


def test_diagnostic_uses_stored_images_and_reports_vae_differences(refmod_root):
    handler = unified.HANDLERS["moss_image"]
    vae = FamilyVAE(handler)
    image = torch.full((2, 64, 96, 3), 128 / 255)
    unified.JWTFUnifiedRefModBake.execute("moss_image", image, "check", 0, "", False, vae=vae)
    clip = FakeClip()
    output = JWTFRefModConditioningCheck.execute(clip, vae, "moss_image/check", "Replace the background with a beach.")
    saved_pos, saved_neg, native_pos, native_neg, target, preview, report_text = output.args
    report = json.loads(report_text)
    assert report["reference_count"] == 2
    assert report["reference_latent_max_absolute_differences"] == [0, 0]
    assert report["target_is_empty"] and torch.count_nonzero(target["samples"]) == 0
    assert target["samples"].shape == (1, 128, 48, 64)
    assert target["samples"].shape[-2:] != saved_pos[0][1]["reference_latents"][0].shape[-2:]
    assert report["output_dimensions"] == [1024, 768]
    assert preview.shape == (1, 64, 96, 3) and torch.equal(preview, image[:1])
    for saved, native in ((saved_pos, native_pos), (saved_neg, native_neg)):
        assert torch.equal(saved[0][0], native[0][0])
        assert saved[0][1]["text"] == native[0][1]["text"]
        assert len(saved[0][1]["reference_latents"]) == len(native[0][1]["reference_latents"]) == 2
    class DifferentVAE(FamilyVAE):
        def encode(self, image):
            return super().encode(image) * 3
    changed = JWTFRefModConditioningCheck.execute(FakeClip(), DifferentVAE(handler), "moss_image/check", "edit")
    assert json.loads(changed.args[-1])["reference_latent_max_absolute_differences"] == [2, 2]
    assert torch.equal(changed.args[0][0][1]["reference_latents"][0], saved_pos[0][1]["reference_latents"][0])


def test_diagnostic_rejects_missing_and_non_moss_bundles(refmod_root):
    with pytest.raises(RefModError, match="Select a saved MOSS"):
        JWTFRefModConditioningCheck.execute(FakeClip(), None, "None", "edit")
    handler = unified.HANDLERS["flux2"]
    unified.JWTFUnifiedRefModBake.execute("flux2", torch.ones(1, 64, 64, 3), "wrong", 0, "", False, vae=FamilyVAE(handler))
    with pytest.raises(RefModError, match="requires a MOSS"):
        JWTFRefModConditioningCheck.execute(FakeClip(), None, "flux2/wrong", "edit")


@pytest.mark.parametrize("width,height", [(31, 768), (1025, 768), (1024, 8193)])
def test_diagnostic_rejects_invalid_output_dimensions(width, height):
    with pytest.raises(RefModError, match="output dimensions"):
        JWTFRefModConditioningCheck.execute(FakeClip(), None, "None", "scene", output_width=width, output_height=height)
