import json

import pytest
import torch

from refmod_h3.clip_doctor import JWTFH3ClipDoctor, inspect_clip


def test_h3_latent_is_authoritative_and_media_repairs_are_explicit():
    samples = torch.zeros(1, 24, 7, 4, 6)
    latent = {"samples": samples, "frame_rate": 30, "custom": "kept"}
    images = torch.zeros(20, 60, 90, 3)
    audio = {"sample_rate": 24000, "waveform": torch.ones(1, 2, 12000)}
    out, fixed_images, fixed_audio, checks = inspect_clip(latent, images, audio, True)
    assert out["samples"] is samples and out["frame_rate"] == 24 and latent["frame_rate"] == 30
    assert out["custom"] == "kept" and fixed_images.shape == (22, 64, 96, 3)
    assert fixed_audio["waveform"].shape[-1] == 22000
    assert audio["waveform"].shape[-1] == 12000
    assert {c["name"] for c in checks if c["status"] == "fixed"} == {"Frame rate", "Decoded images", "Audio duration"}


def test_h3_report_only_preserves_inputs_and_strict_blocks_wrong_family():
    latent = {"samples": torch.zeros(1, 16, 1, 2, 2)}
    result = JWTFH3ClipDoctor.execute(latent, strict=False)
    checks = json.loads(result.args[3])
    assert any(c["name"] == "Video channels" and c["status"] == "error" for c in checks)
    assert result.args[0]["samples"] is latent["samples"]
    with pytest.raises(ValueError, match="24"):
        JWTFH3ClipDoctor.execute(latent)


@pytest.mark.parametrize("samples", [torch.zeros(1, 24, 0, 2, 2), torch.zeros(1, 24, 2, 2), torch.zeros(1, 24, 3, 2, 2), torch.full((1, 24, 1, 2, 2), float("nan"))])
def test_h3_malformed_latents_cannot_be_silently_repaired(samples):
    with pytest.raises(ValueError, match="H3 Clip Doctor"):
        JWTFH3ClipDoctor.execute({"samples": samples}, auto_fix=True)


@pytest.mark.parametrize("tokens, frames", [(1, 1), (2, 5), (7, 22), (12, 39)])
def test_h3_frame_mapping_matches_core_vae(tokens, frames):
    images = torch.zeros(frames, 16, 16, 3)
    _, _, _, checks = inspect_clip({"samples": torch.zeros(1, 24, tokens, 1, 1)}, images)
    assert not [c for c in checks if c["status"] == "error"]
