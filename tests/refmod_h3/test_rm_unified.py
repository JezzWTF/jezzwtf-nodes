"""Unified image-model RefMods: handler registry, file format, bake, apply and library payload."""
from __future__ import annotations

import json
import os

import pytest
import torch
from safetensors import safe_open

from fakes import FakeClip, FakeImageVAE
from refmod_h3 import unified
from refmod_h3._types import RefModError
from v3_helpers import legacy, legacy_spec

CHANNELS = {"qwen21": 64, "fibo2": 128, "flux3": 128}


def bake(refmod_root: str, model: str, name: str = "alice", n: int = 2, resolution: int = 128,
         **kw: object) -> str:
    frames = torch.rand(n, 96, 160, 3)
    out = legacy(unified.JWTFUnifiedRefModBake.execute(model, frames, name, resolution, "", True,
                                               vae=FakeImageVAE(CHANNELS[model]), **kw))
    return out["result"][0]


def test_registry_matches_the_spec_table() -> None:
    rows = {k: (h.label, h.format, h.meta_key, h.subfolder, h.max_refs, h.latent_channels, h.stores_images,
                h.accent, h.apply_needs, sorted(h.apply_uses))
            for k, h in unified.HANDLERS.items()}
    assert rows == {
        "qwen21": ("Qwen 2.1", "jezzwtf_qwen21_refmod", "jezzwtf_qwen21", "qwen21", 16, 64, True, "#22d3ee",
                   ("clip",), ["clip", "ref_on_negative", "ref_strength"]),
        "fibo2": ("Fibo 2", "jezzwtf_fibo2_refmod", "jezzwtf_fibo2", "fibo2", 8, 128, True, "#f472b6",
                  ("clip",), ["clip", "ref_on_negative", "ref_strength"]),
        "flux3": ("Flux 3", "jezzwtf_flux3_refmod", "jezzwtf_flux3", "flux3", 16, 128, False, "#fbbf24",
                  ("positive",), ["positive", "ref_on_negative", "ref_strength"]),
    }
    ui = unified.HANDLERS["qwen21"].ui()
    assert ui["token_downscale"] == 16 and ui["bake_needs"] == ["vae"] and ui["bake_uses"] == ["vae"]


@pytest.mark.parametrize("model", ["qwen21", "fibo2", "flux3"])
def test_bake_file_format_detect_and_load(refmod_root: str, model: str) -> None:
    path = bake(refmod_root, model, n=2, resolution=128)
    assert path == os.path.join(refmod_root, model, "alice.safetensors")
    h = unified.HANDLERS[model]
    found = unified.detect(path)
    assert found is not None and found[0].key == model
    meta = found[1]
    assert meta["format"] == h.format and meta["version"] == 1 and meta["count"] == 2 and meta["name"] == "alice"
    assert isinstance(meta["thumb"], str) and meta["thumb"]
    with safe_open(path, framework="pt") as fh:
        assert set(fh.metadata()) == {h.meta_key}
        keys = set(fh.keys())
        lat = fh.get_tensor("lat_0")
    assert lat.dtype == torch.float32
    assert keys == ({"lat_0", "lat_1", "img_0", "img_1"} if h.stores_images else {"lat_0", "lat_1"})
    if h.stores_images:
        assert meta["latent_channels"] == h.latent_channels and meta["downscale"] == 16 and meta["resolution"] == 128
        assert len(meta["sizes"]) == 2 and all(w % 32 == 0 and hh % 32 == 0 for w, hh in meta["sizes"])
    else:
        assert meta["shapes"][0][:2] == [1, 128] and meta["megapixels"] == pytest.approx(128 * 128 / 1024 ** 2)
    got_h, lats, imgs = unified.load_refs(path)
    assert got_h.key == model and len(lats) == 2 and len(imgs) == (2 if h.stores_images else 0)
    if imgs:
        assert imgs[0].dtype == torch.float32 and 0 <= float(imgs[0].min()) and float(imgs[0].max()) <= 1


def test_encoding_rules() -> None:
    assert tuple(unified.resize32(torch.rand(1, 100, 200, 3), 0).shape[1:3]) == (96, 192)
    s = unified.resize32(torch.rand(1, 300, 600, 3), 256)
    assert s.shape[1] % 32 == 0 and s.shape[2] % 32 == 0 and s.shape[1] * s.shape[2] == pytest.approx(256 * 256, rel=0.2)
    same = torch.rand(1, 64, 64, 3)
    assert unified.resize32(same, 0) is same
    rgba = torch.zeros(1, 2, 2, 4)
    rgba[..., :3] = 0.0
    rgba[..., 3] = 0.25
    assert torch.allclose(unified.rgb_over_white(rgba), torch.full((1, 2, 2, 3), 0.75))
    enc = unified.HANDLERS["qwen21"].encode(unified.HANDLERS["qwen21"], FakeImageVAE(64), torch.rand(1, 64, 96, 4), 0)
    assert enc.img is not None and enc.img.shape[-1] == 3 and enc.size == (96, 64)
    flux = unified.HANDLERS["flux3"].encode(unified.HANDLERS["flux3"], FakeImageVAE(128), torch.rand(1, 100, 200, 3), 128)
    assert flux.img is None and flux.size[0] * flux.size[1] == pytest.approx(128 * 128, rel=0.1)
    with pytest.raises(RefModError, match="expected \\[1, 64, h, w\\]"):
        unified.HANDLERS["qwen21"].encode(unified.HANDLERS["qwen21"], FakeImageVAE(32), torch.rand(1, 64, 64, 3), 0)


def test_bake_rules(refmod_root: str) -> None:
    node = unified.JWTFUnifiedRefModBake
    vae = FakeImageVAE(64)
    first = bake(refmod_root, "qwen21")
    again = legacy(node.execute("qwen21", torch.rand(1, 64, 64, 3), "alice", 128, "", False, vae=vae))
    assert again["result"] == (first,) and "already exists, skipped" in again["ui"]["text"][0]
    with pytest.raises(RefModError, match="at most 8"):
        legacy(node.execute("fibo2", torch.rand(9, 64, 64, 3), "x", 128, "", True, vae=FakeImageVAE(128)))
    with pytest.raises(RefModError, match="no reference images"):
        legacy(node.execute("qwen21", torch.zeros(0, 64, 64, 3), "x", 128, "", True, vae=vae))
    with pytest.raises(RefModError, match="VAE"):
        legacy(node.execute("qwen21", torch.rand(1, 64, 64, 3), "x", 128, "", True))
    with pytest.raises(RefModError, match="unknown model"):
        legacy(node.execute("nope", torch.rand(1, 64, 64, 3), "x", 128, "", True, vae=vae))
    for bad_sub in ("..", "C:\\x", "/abs"):
        with pytest.raises(RefModError):
            legacy(node.execute("qwen21", torch.rand(1, 64, 64, 3), "x", 128, bad_sub, True, vae=vae))
    four = legacy(node.execute("qwen21", torch.rand(1, 64, 64, 3), "four", 128, "", True, vae=vae,
                     image_2=torch.rand(1, 64, 64, 3), image_3=torch.rand(2, 64, 64, 3), image_4=None, scale_mode="x"))
    assert unified.detect(four["result"][0])[1]["count"] == 4
    assert os.path.basename(unified.unified_output_path("a/b:c*", "", unified.HANDLERS["qwen21"])) == "a_b_c_.safetensors"
    with pytest.raises(RefModError, match="empty"):
        unified.sanitise_file_name("  . ")


def test_detect_ignores_non_refmods_and_validation_catches_bad_tensors(refmod_root: str, tmp_path: object) -> None:
    from safetensors.torch import save_file
    plain = os.path.join(refmod_root, "plain.safetensors")
    save_file({"x": torch.zeros(1)}, plain)
    assert unified.detect(plain) is None
    path = bake(refmod_root, "qwen21", n=1)
    with safe_open(path, framework="pt") as fh:
        tensors = {k: fh.get_tensor(k).clone() for k in fh.keys()}
        meta = fh.metadata()
    tensors["lat_0"] = torch.zeros(1, 64, 3, 3)  # H//16 no longer matches
    broken = os.path.join(refmod_root, "broken.safetensors")
    save_file(tensors, broken, metadata=meta)
    with pytest.raises(RefModError, match="does not match latent"):
        unified.load_refs(broken)
    with pytest.raises(RefModError, match="not a Qwen/Fibo/Flux"):
        unified.load_refs(plain)


def test_index_and_library_payload(refmod_root: str) -> None:
    bake(refmod_root, "qwen21", "q", n=2)
    bake(refmod_root, "flux3", "f", n=1)
    unified.invalidate(os.path.join(refmod_root, "qwen21", "q.safetensors"))
    assert unified.choices()[0] == "None"
    payload = unified.library_payload()
    assert [m["key"] for m in payload["models"]] == ["qwen21", "fibo2", "flux3"]
    by = {r["name"]: r for r in payload["refmods"]}
    assert set(by) == {"flux3/f", "qwen21/q"}
    q, f = by["qwen21/q"], by["flux3/f"]
    assert q["model"] == "qwen21" and q["count"] == 2 and q["thumb"] is True and isinstance(q["stamp"], int)
    assert q["tokens"] == sum((w // 16) * (h // 16) for w, h in q["sizes"])
    assert f["sizes"][0][0] % 16 == 0 and f["tokens"] == (f["sizes"][0][0] // 16) * (f["sizes"][0][1] // 16)
    data = unified.thumb_bytes("qwen21/q")
    assert data is not None and data[:2] == b"\xff\xd8"
    assert unified.thumb_bytes("../qwen21/q") is None and unified.thumb_bytes("missing") is None


def test_apply_qwen_schedules_references_by_fraction_of_steps(refmod_root: str) -> None:
    bake(refmod_root, "qwen21", "alice", n=2)
    clip = FakeClip()
    node = unified.JWTFUnifiedRefModApply
    pos, neg, latent = legacy(node.execute(unified.AUTO, "qwen21/alice", clip=clip, prompt="a cat", negative_prompt="blur"))
    assert len(pos) == 1 and len(pos[0][1]["reference_latents"]) == 2 and len(neg[0][1]["reference_latents"]) == 2
    assert pos[0][1]["n_images"] == 2  # the text encoder sees the stored images
    assert latent["samples"].shape[1] == 64 and float(latent["samples"].abs().sum()) == 0.0
    assert clip.tokenize_calls[0]["keep_vision"] is False and clip.tokenize_calls[0]["prevent_empty_text"] is True
    pos, neg, _ = legacy(node.execute("qwen21", "qwen21/alice", clip=clip, prompt="a cat", ref_strength=0.4, ref_on_negative=False))
    assert [(p[1].get("start_percent"), p[1].get("end_percent")) for p in pos] == [(0.0, 0.4), (0.4, 1.0)]
    assert "reference_latents" in pos[0][1] and "reference_latents" not in pos[1][1]
    assert "reference_latents" not in neg[0][1]
    pos, _, _ = legacy(node.execute("qwen21", "qwen21/alice", clip=clip, ref_strength=0.0))
    assert "reference_latents" not in pos[0][1]


def test_apply_flux3_needs_positive_and_keeps_negative_rules(refmod_root: str) -> None:
    bake(refmod_root, "flux3", "f", n=1)
    node = unified.JWTFUnifiedRefModApply
    with pytest.raises(RefModError, match="positive"):
        legacy(node.execute("auto (from refmod)", "flux3/f"))
    positive = [[torch.zeros(1, 4), {"text": "p"}]]
    pos, neg, _ = legacy(node.execute(unified.AUTO, "flux3/f", positive=positive))
    assert len(pos[0][1]["reference_latents"]) == 1 and neg is pos  # no negative: negative output = positive
    negative = [[torch.zeros(1, 4), {"text": "n"}]]
    _, neg, _ = legacy(node.execute(unified.AUTO, "flux3/f", positive=positive, negative=negative, ref_on_negative=False))
    assert neg is negative


def test_apply_error_paths(refmod_root: str) -> None:
    bake(refmod_root, "qwen21", "q", n=1)
    bake(refmod_root, "flux3", "f", n=1)
    node = unified.JWTFUnifiedRefModApply
    positive = [[torch.zeros(1, 4), {}]]
    with pytest.raises(RefModError, match="mixed models"):
        legacy(node.execute(unified.AUTO, "qwen21/q", clip=FakeClip(), refmod_2="flux3/f", positive=positive))
    with pytest.raises(RefModError, match="different|model is set to"):
        legacy(node.execute("flux3", "qwen21/q", clip=FakeClip(), positive=positive))
    with pytest.raises(RefModError, match="choose a model"):
        legacy(node.execute(unified.AUTO, unified.NONE))
    with pytest.raises(RefModError, match="not found"):
        legacy(node.execute(unified.AUTO, "ghost"))
    with pytest.raises(RefModError, match="needs a CLIP"):
        legacy(node.execute(unified.AUTO, "qwen21/q"))
    with pytest.raises(RefModError, match="extra_image needs the vae"):
        legacy(node.execute("qwen21", unified.NONE, clip=FakeClip(), extra_image=torch.rand(1, 64, 64, 3)))
    pos, _, latent = legacy(node.execute("qwen21", unified.NONE, clip=FakeClip(), extra_image=torch.rand(2, 64, 64, 3),
                                vae=FakeImageVAE(64), extra_image_resolution=64))
    assert len(pos[0][1]["reference_latents"]) == 2 and latent["samples"].shape[1] == 64
    empty = legacy(node.execute("flux3", unified.NONE, positive=positive))[2]
    assert tuple(empty["samples"].shape) == (1, 128, 64, 64)


def test_is_changed_uses_file_mtimes(refmod_root: str) -> None:
    path = bake(refmod_root, "qwen21", "q", n=1)
    key = unified.JWTFUnifiedRefModApply.fingerprint_inputs("qwen21/q")
    assert key == str(os.path.getmtime(path))
    assert unified.JWTFUnifiedRefModApply.fingerprint_inputs("qwen21/q", "ghost") == f"{key}|missing"
    assert unified.JWTFUnifiedRefModApply.fingerprint_inputs() == ""
    spec = legacy_spec(unified.JWTFUnifiedRefModApply)
    assert list(spec["optional"])[-4:] == ["extra_image_resolution", "extra_image_scale", "ref_strength", "ref_on_negative"]
    assert spec["required"]["model"][0][0] == unified.AUTO and json.dumps(spec)


def test_one_bad_file_does_not_blank_the_library(refmod_root: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from safetensors.torch import save_file

    good = bake(refmod_root, "qwen21", "good", n=1)
    bad = bake(refmod_root, "qwen21", "bad", n=1)
    vanishing = bake(refmod_root, "qwen21", "vanishing", n=1)
    with safe_open(bad, framework="pt") as fh:
        meta = dict(fh.metadata())
        tensors = {k: fh.get_tensor(k).clone() for k in fh.keys()}
    parsed = json.loads(meta["jezzwtf_qwen21"])
    parsed["sizes"] = [["wide", "tall"]]  # int() raises while building the entry
    meta["jezzwtf_qwen21"] = json.dumps(parsed)
    save_file(tensors, bad, metadata=meta)
    unified.invalidate(bad)

    real = os.path.getmtime

    def getmtime(path: str) -> float:
        if str(path) == vanishing:
            raise FileNotFoundError(path)  # deleted between listing and stat
        return real(path)

    monkeypatch.setattr(os.path, "getmtime", getmtime)
    payload = unified.library_payload()
    assert [r["name"] for r in payload["refmods"]] == ["qwen21/good"]
    assert "error" not in payload and len(payload["errors"]) == 2
    assert any("qwen21/bad" in e for e in payload["errors"]) and any("qwen21/vanishing" in e for e in payload["errors"])
    assert good  # the surviving entry is the intact one
