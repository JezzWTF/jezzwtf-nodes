from __future__ import annotations

from types import SimpleNamespace

import pytest
import torch
from comfy_api.latest import io

from fakes import FakeClip
from refmod_h3 import unified
from refmod_h3._types import RefModError


class FamilyVAE:
    def __init__(self, handler):
        self.handler = handler
        self.downscale_index_formula = (8, 32, 32)

    def encode(self, image):
        h = self.handler
        shape = (1, h.latent_channels, image.shape[1] // h.spatial_downscale, image.shape[2] // h.spatial_downscale)
        if h.key in ("krea2", "ltxv"):
            shape = shape[:2] + (1,) + shape[2:]
        return torch.ones(shape)


@pytest.mark.parametrize("family", ["moss_image", "krea2", "flux_kontext", "flux2", "ltxv"])
def test_new_family_bundle_roundtrip(refmod_root, family):
    h = unified.HANDLERS[family]
    result = unified.JWTFUnifiedRefModBake.execute(family, torch.rand(2, 64, 96, 3), "refs", 64, "", True, vae=FamilyVAE(h))
    path = result.args[0]
    handler, lats, images = unified.load_refs(path)
    assert handler is h and len(lats) == 2
    assert len(images) == (2 if h.stores_images else 0)
    assert lats[0].shape[1] == h.latent_channels
    assert lats[0].ndim == (5 if family in ("krea2", "ltxv") else 4)
    assert unified.index()[f"{family}/refs"][1] is h


@pytest.mark.parametrize("layout, method, vision", [
    ("ai-toolkit", "index_timestep_zero_isolated", True),
    ("ai-toolkit (kv_cache off)", "index_timestep_zero", True),
    ("Moss-Image-Edit", "index_timestep_zero_text_start", False),
])
def test_moss_training_layout_controls_latents_and_text_vision(layout, method, vision):
    h = unified.HANDLERS["moss_image"]
    clip = FakeClip()
    ctx = unified.ApplyContext(clip, "edit", "bad", None, None, 1, True, layout)
    latent, image = torch.ones(1, 128, 4, 4), torch.ones(1, 64, 64, 3)
    pos, neg = h.build(h, ctx, [latent], [image])
    assert pos[0][1]["reference_latents_method"] == neg[0][1]["reference_latents_method"] == method
    assert pos[0][1]["reference_latents"][0] is latent
    assert clip.tokenize_calls[0]["text"].startswith("Picture 1:") == vision
    assert len(clip.tokenize_calls[0]["images"]) == int(vision)


@pytest.mark.parametrize("layout", [name for name in unified.EDIT_FORMATS if name != "Krea2 style reference"])
def test_moss_saved_reference_conditioning_matches_native_edit_node(refmod_root, layout):
    from comfy_extras.nodes_moss_image import TextEncodeMOSSImageEdit
    h = unified.HANDLERS["moss_image"]
    vae = FamilyVAE(h)
    # Exact 8-bit pixels avoid a rounding difference from storing the RGB image.
    image = torch.randint(0, 256, (1, 64, 64, 3)).float() / 255
    unified.JWTFUnifiedRefModBake.execute("moss_image", image, "native_parity", 0, "", False, vae=vae)
    actual_clip, native_clip = FakeClip(), FakeClip()
    pos, neg, _ = unified.JWTFUnifiedRefModApply.execute(unified.AUTO, "moss_image/native_parity", clip=actual_clip,
                                                       prompt="A portrait", negative_prompt="bad", edit_format=layout).args
    for actual, prompt in ((pos, "A portrait"), (neg, "bad")):
        expected = TextEncodeMOSSImageEdit.execute(native_clip, prompt, layout, {"image_1": image}, vae).args[0]
        assert torch.equal(actual[0][0], expected[0][0])
        assert actual[0][1].keys() == expected[0][1].keys()
        for key in actual[0][1]:
            if key == "reference_latents":
                assert torch.equal(actual[0][1][key][0], expected[0][1][key][0])
            else:
                assert actual[0][1][key] == expected[0][1][key]
    assert actual_clip.tokenize_calls[0]["text"] == native_clip.tokenize_calls[0]["text"]
    for actual, expected in zip(actual_clip.tokenize_calls[0]["images"], native_clip.tokenize_calls[0]["images"]):
        assert torch.equal(actual, expected)


def test_moss_old_native_backend_fails_before_sampling(monkeypatch):
    previous = unified._comfy.optional_module
    monkeypatch.setattr(unified._comfy, "optional_module", lambda name: None if name == "comfy_extras.nodes_moss_image" else previous(name))
    with pytest.raises(RefModError, match="native Text Encode MOSS-Image Edit"):
        h = unified.HANDLERS["moss_image"]
        h.build(h, unified.ApplyContext(FakeClip(), "portrait", "", None, None, 1, True), [], [])


@pytest.mark.parametrize("family", ["qwen21", "fibo2", "krea2"])
def test_saved_references_match_native_edit_conditioning(refmod_root, family):
    from comfy_extras.nodes_qwen import TextEncodeQwenImage21, TextEncodeQwenImageEditPlus
    from comfy_extras.nodes_fibo2 import TextEncodeFibo2
    h = unified.HANDLERS[family]
    vae = FamilyVAE(h)
    edge = 1024 if family == "krea2" else 64
    image = torch.full((1, edge, edge, 3), 128 / 255)
    resolution = 1024 if family in ("fibo2", "krea2") else 0
    unified.JWTFUnifiedRefModBake.execute(family, image, "native_parity", resolution, "", False, vae=vae)
    actual_clip, native_clip = FakeClip(), FakeClip()
    layout = "Krea2 style reference" if family == "krea2" else "ai-toolkit"
    positive, negative, _ = unified.JWTFUnifiedRefModApply.execute(unified.AUTO, f"{family}/native_parity", clip=actual_clip,
                                                              prompt="change the coat", negative_prompt="distorted clothing", edit_format=layout).args
    if family == "qwen21":
        expected = TextEncodeQwenImage21.execute(native_clip, "change the coat", "distorted clothing", vae, 0, {"image_1": image}).args
    elif family == "fibo2":
        expected = TextEncodeFibo2.execute(native_clip, "change the coat", "distorted clothing", vae, {"image_1": image}).args
    else:
        expected = TextEncodeQwenImageEditPlus.execute(native_clip, "change the coat", vae, image).args
        assert positive[0][1]["reference_latents_method"] == "index_timestep_zero"
        assert actual_clip.tokenize_calls[0]["llama_template"] == native_clip.tokenize_calls[0]["llama_template"]
    for actual, native in zip((positive, negative), expected):
        assert actual[0][1]["text"] == native[0][1]["text"]
        assert actual[0][1]["n_images"] == native[0][1]["n_images"]
        assert torch.equal(actual[0][1]["reference_latents"][0], native[0][1]["reference_latents"][0])
    assert actual_clip.tokenize_calls[0]["text"] == native_clip.tokenize_calls[0]["text"]
    for actual, native in zip(actual_clip.tokenize_calls[0]["images"], native_clip.tokenize_calls[0]["images"]):
        assert actual.shape == native.shape
        assert torch.allclose(actual, native, atol=1 / 255)


def test_krea_uses_own_template_and_rejects_moss_only_layout(monkeypatch):
    previous = unified._comfy.optional_module
    monkeypatch.setattr(unified._comfy, "optional_module", lambda name: SimpleNamespace(KREA2_TEMPLATE="krea-template") if name == "comfy.text_encoders.krea2" else previous(name))
    clip = FakeClip()
    h = unified.HANDLERS["krea2"]
    ctx = unified.ApplyContext(clip, "edit", "", None, None, 1, True)
    h.build(h, ctx, [torch.ones(1, 16, 1, 8, 8)], [torch.ones(1, 64, 64, 3)])
    assert clip.tokenize_calls[0]["llama_template"] == "krea-template"
    ctx.edit_format = "Moss-Image-Edit"
    with pytest.raises(RefModError, match="Moss"):
        h.build(h, ctx, [], [])


def test_wrong_vae_channels_are_rejected():
    h = unified.HANDLERS["krea2"]
    with pytest.raises(RefModError, match="single-image"):
        h.validate(h, torch.zeros(1, 128, 1, 4, 4), torch.zeros(1, 32, 32, 3))
    with pytest.raises(RefModError, match="single-image"):
        unified.HANDLERS["ltxv"].validate(unified.HANDLERS["ltxv"], torch.zeros(1, 128, 2, 4, 4), None)


def test_kontext_default_bake_uses_native_trained_image_bucket():
    from comfy_extras.nodes_flux import FluxKontextImageScale
    h = unified.HANDLERS["flux_kontext"]
    image = torch.full((1, 80, 120, 3), 128 / 255)
    vae = FamilyVAE(h)
    scaled = FluxKontextImageScale.execute(image).args[0]
    encoded = h.encode(h, vae, image, 1024)
    assert encoded.size == (scaled.shape[2], scaled.shape[1])
    assert torch.equal(encoded.lat, vae.encode(scaled))


def test_ltx_apply_delegates_each_saved_guide_and_preserves_native_output(monkeypatch, refmod_root):
    h = unified.HANDLERS["ltxv"]
    vae = FamilyVAE(h)
    unified.JWTFUnifiedRefModBake.execute("ltxv", torch.ones(2, 64, 64, 3), "guides", 64, "", True, vae=vae)
    calls = []
    def apply(pos, neg, vae, latent, guide, index, strength):
        calls.append((guide["samples"].shape, index, strength))
        return io.NodeOutput(pos, neg, {**latent, "guide_count": len(calls), "noise_mask": "native-mask"})
    previous = unified._comfy.optional_module
    monkeypatch.setattr(unified._comfy, "optional_module", lambda name: SimpleNamespace(LTXVAddLatentGuide=SimpleNamespace(execute=apply)) if name == "comfy_extras.nodes_lt" else previous(name))
    target = {"samples": torch.zeros(1, 128, 8, 2, 2), "custom": "kept"}
    pos, neg = [[torch.zeros(1), {}]], [[torch.zeros(1), {}]]
    result = unified.JWTFUnifiedRefModApply.execute(unified.AUTO, "ltxv/guides", positive=pos, negative=neg,
                                                  latent_in=target, vae=vae, latent_idx=-1, guide_strength=0.7)
    assert len(calls) == 2 and calls[0][1:] == (-1, 0.7)
    assert result.args[2]["guide_count"] == 2 and result.args[2]["noise_mask"] == "native-mask"
    assert result.args[2]["custom"] == "kept" and "guide_count" not in target


def test_ltx_missing_native_node_and_target_are_actionable(monkeypatch):
    with pytest.raises(RefModError, match="latent_in"):
        unified.apply_ltx([], [], None, object(), [], 0, 1)
    monkeypatch.setattr(unified._comfy, "optional_module", lambda _: None)
    with pytest.raises(RefModError, match="Update ComfyUI"):
        unified.apply_ltx([], [], {"samples": torch.zeros(1, 128, 4, 2, 2)}, object(), [], 0, 1)


def test_ltx_native_guide_preserves_position_metadata_without_loading_models():
    module = unified._comfy.optional_module("comfy_extras.nodes_lt")
    if getattr(module, "LTXVAddLatentGuide", None) is None:
        pytest.skip("ComfyUI build does not include LTXVAddLatentGuide")
    positive, negative = [[torch.zeros(1, 4), {}]], [[torch.zeros(1, 4), {}]]
    original = {"samples": torch.zeros(1, 128, 4, 2, 2), "custom": "retained"}
    guide = torch.ones(1, 128, 1, 2, 2)
    vae = SimpleNamespace(downscale_index_formula=(8, 32, 32))
    pos, neg, result = unified.apply_ltx(positive, negative, original, vae, [guide], 0, 0.75)
    assert result["samples"].shape == (1, 128, 5, 2, 2)
    assert result["noise_mask"][0, 0, -1].mean() == pytest.approx(0.25)
    assert result["custom"] == "retained" and original["samples"].shape[2] == 4
    assert "keyframe_idxs" in pos[0][1] and "guide_attention_entries" in neg[0][1]
