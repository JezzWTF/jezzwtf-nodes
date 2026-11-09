"""Bundle v5 / standalone file format: round trip, exact header layout and validation errors."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import torch
from safetensors import safe_open
from safetensors.torch import save_file

from refmod_h3 import bundle
from refmod_h3._types import RefModError
from refmod_h3.bundle import RefMod


def visual(name: str = "v", t: int = 1, h: int = 4, w: int = 6, seed: int = 0) -> RefMod:
    g = torch.Generator().manual_seed(seed)
    lat = torch.randn(1, 24, t, h, w, generator=g).to(torch.float16)
    return RefMod(name=name, kind="image" if t == 1 else "video", latent=lat, description="a face",
                  tags=["1 img, 0 vid"], source="image", source_shape="1x128x192")


def audio(name: str = "a", t: int = 40) -> RefMod:
    lat = torch.randn(1, 32, 2, t, generator=torch.Generator().manual_seed(3))
    return RefMod(name=name, kind="audio", latent=lat, concept_type="voice", sample_rate=32000)


def test_bundle_round_trip_and_header(tmp_path: Path) -> None:
    dest = os.path.join(str(tmp_path), "char.safetensors")
    a, b = visual("char_visual", t=5), audio("char_audio")
    bundle.write_bundle(dest, "char", [a, b])
    with safe_open(dest, framework="pt") as fh:
        meta = fh.metadata()
        assert set(fh.keys()) == {"ref_0", "ref_1"}
    payload = json.loads(meta["refmod_meta"])
    assert payload["_format_version"] == 5
    assert payload["kind"] == "bundle"
    assert payload["name"] == "char"
    assert [m["name"] for m in payload["members"]] == ["char_visual", "char_audio"]
    assert payload["members"][0]["kind"] == "video" and payload["members"][0]["latent_t"] == 5
    assert payload["members"][0]["_format_version"] == 4
    assert payload["members"][1]["sample_rate"] == 32000
    mods = bundle.load_refmod_file(dest)
    assert [m.kind for m in mods] == ["video", "audio"]
    assert torch.equal(mods[0].latent, a.latent) and mods[0].latent.dtype == torch.float16
    assert torch.equal(mods[1].latent, b.latent) and mods[1].latent.dtype == torch.float32
    assert mods[0].bundle_index == 0 and mods[1].bundle_index == 1 and mods[0].path == dest
    assert mods[0].token_count == 5 * 2 * 3 and mods[1].token_count == 80


def test_write_bundle_dedupes_by_identity_and_leaves_no_temp(tmp_path: Path) -> None:
    folder = str(tmp_path)
    a = visual("x")
    bundle.write_bundle(os.path.join(folder, "d.safetensors"), "d", [a, a, a])
    assert len(bundle.inspect_file(os.path.join(folder, "d.safetensors")).members) == 1
    assert [f for f in os.listdir(folder) if f.endswith(".tmp")] == []


def test_standalone_mod_round_trip_and_sidecar(tmp_path: Path) -> None:
    dest = os.path.join(str(tmp_path), "old.safetensors")
    bundle.write_standalone(dest, visual("old"))
    info = bundle.inspect_file(dest)
    assert not info.is_bundle and info.kind == "image"
    assert bundle.load_refmod_file(dest)[0].name == "old"
    # metadata moved to a sidecar json
    side_dest = os.path.join(str(tmp_path), "side.safetensors")
    save_file({"latent": visual().latent}, side_dest)
    with open(os.path.join(str(tmp_path), "side.json"), "w", encoding="utf-8") as fh:
        json.dump(visual("side").member_meta(), fh)
    assert bundle.inspect_file(side_dest).name == "side"


def test_audio_standalone_uses_audio_meta_key(tmp_path: Path) -> None:
    dest = os.path.join(str(tmp_path), "voice.safetensors")
    bundle.write_standalone(dest, audio("voice"))
    assert "audio_refmod_meta" in bundle.read_metadata(dest)
    assert bundle.inspect_file(dest).kind == "audio"


@pytest.mark.parametrize("kind,shape,msg", [
    ("image", (1, 23, 1, 4, 4), "24"),
    ("image", (1, 24, 2, 4, 4), "T == 1"),
    ("image", (1, 24, 1, 3, 4), "even"),
    ("image", (1, 24, 1, 4, 5), "even"),
    ("video", (2, 24, 3, 4, 4), "24"),
    ("video", (1, 24, 0, 4, 4), "empty"),
    ("video", (1, 24, 3, 4), "must be"),
    ("audio", (1, 32, 1, 10), "audio latent"),
    ("audio", (1, 31, 2, 10), "audio latent"),
    ("audio", (1, 32, 2, 0), "T == 0"),
    ("other", (1, 24, 1, 4, 4), "unknown kind"),
])
def test_validate_latent_rejects_bad_layouts(kind: str, shape: tuple[int, ...], msg: str) -> None:
    with pytest.raises(RefModError, match=msg):
        bundle.validate_latent(kind, torch.zeros(*shape))


def test_validate_latent_rejects_non_finite_and_accepts_good() -> None:
    bad = torch.zeros(1, 24, 1, 4, 4)
    bad[0, 0, 0, 0, 0] = float("nan")
    with pytest.raises(RefModError, match="NaN"):
        bundle.validate_latent("image", bad)
    bundle.validate_latent("image", torch.zeros(1, 24, 1, 2, 2))
    bundle.validate_latent("video", torch.zeros(1, 24, 5, 4, 4))
    bundle.validate_latent("audio", torch.zeros(1, 32, 2, 7))


def test_write_bundle_refuses_empty_oversized_and_invalid(tmp_path: Path) -> None:
    dest = os.path.join(str(tmp_path), "x.safetensors")
    with pytest.raises(RefModError, match="at least one"):
        bundle.write_bundle(dest, "x", [])
    with pytest.raises(RefModError, match="at most 256"):
        bundle.write_bundle(dest, "x", [visual(f"m{i}") for i in range(257)])
    broken = visual("b")
    broken.latent = torch.zeros(1, 24, 1, 3, 4, dtype=torch.float16)
    with pytest.raises(RefModError, match="even"):
        bundle.write_bundle(dest, "x", [broken])
    assert not os.path.exists(dest)


def _bundle_file(path: str, members: list[dict[str, object]], tensors: dict[str, torch.Tensor],
                 version: int = 5) -> None:
    meta = {"refmod_meta": json.dumps({"_format_version": version, "kind": "bundle", "name": "n",
                                       "members": members})}
    save_file(tensors, path, metadata=meta)


def test_inspect_rejects_malformed_bundles(tmp_path: Path) -> None:
    folder = str(tmp_path)
    member = {"name": "m", "kind": "image"}
    good = {"ref_0": torch.zeros(1, 24, 1, 2, 2)}
    p = os.path.join(folder, "missing.safetensors")
    _bundle_file(p, [member, member], good)
    with pytest.raises(RefModError, match="missing tensor ref_1"):
        bundle.inspect_file(p)
    p = os.path.join(folder, "oldver.safetensors")
    _bundle_file(p, [member], good, version=4)
    with pytest.raises(RefModError, match="unsupported bundle format"):
        bundle.inspect_file(p)
    p = os.path.join(folder, "kind.safetensors")
    _bundle_file(p, [{"name": "m", "kind": "text"}], good)
    with pytest.raises(RefModError, match="invalid kind"):
        bundle.inspect_file(p)
    p = os.path.join(folder, "nomembers.safetensors")
    _bundle_file(p, [], good)
    with pytest.raises(RefModError, match="1-256"):
        bundle.inspect_file(p)
    p = os.path.join(folder, "nometa.safetensors")
    save_file(good, p)
    with pytest.raises(RefModError, match="no refmod metadata"):
        bundle.inspect_file(p)
    p = os.path.join(folder, "garbage.safetensors")
    with open(p, "wb") as fh:
        fh.write(b"\x01\x00")
    with pytest.raises(RefModError, match="too short"):
        bundle.inspect_file(p)


def test_load_rejects_bad_tensor_in_valid_header(tmp_path: Path) -> None:
    p = os.path.join(str(tmp_path), "bad.safetensors")
    _bundle_file(p, [{"name": "m", "kind": "image"}], {"ref_0": torch.zeros(1, 24, 2, 2, 2)})
    with pytest.raises(RefModError, match="T == 1"):
        bundle.load_refmod_file(p)


def test_load_select_and_out_of_range(tmp_path: Path) -> None:
    dest = os.path.join(str(tmp_path), "two.safetensors")
    bundle.write_bundle(dest, "two", [visual("a"), audio("b")])
    only_audio = bundle.load_refmod_file(dest, select=[1])
    assert [m.kind for m in only_audio] == ["audio"]
    with pytest.raises(RefModError, match="out of range"):
        bundle.load_refmod_file(dest, select=[5])


def test_update_bundle_member_checks_name_and_keeps_others(tmp_path: Path) -> None:
    dest = os.path.join(str(tmp_path), "u.safetensors")
    a, b = visual("first", seed=1), audio("second")
    bundle.write_bundle(dest, "u", [a, b])
    bundle.update_bundle_member(dest, 0, "first", {"description": "fixed"})
    mods = bundle.load_refmod_file(dest)
    assert mods[0].description == "fixed" and torch.equal(mods[1].latent, b.latent)
    with pytest.raises(RefModError, match="no longer"):
        bundle.update_bundle_member(dest, 0, "wrong", {})
    new = visual("first", seed=9)
    bundle.update_bundle_member(dest, 0, "first", {}, new.latent)
    assert torch.equal(bundle.load_refmod_file(dest)[0].latent, new.latent)


def test_finite_unit() -> None:
    assert bundle.finite_unit(0.5, "x") == 0.5
    for bad in (-0.1, 1.1, float("nan"), float("inf")):
        with pytest.raises(RefModError):
            bundle.finite_unit(bad, "x")


def test_non_float_latent_dtypes_are_rejected() -> None:
    for dtype in (torch.int8, torch.float64):
        lat = torch.zeros(1, 24, 1, 4, 6).to(dtype)
        with pytest.raises(RefModError, match="dtype"):
            bundle.validate_latent("image", lat, "x")
    for dtype in (torch.float16, torch.bfloat16, torch.float32):
        bundle.validate_latent("image", torch.zeros(1, 24, 1, 4, 6, dtype=dtype), "x")


def test_non_finite_numeric_metadata_is_a_refmod_error(tmp_path: Path) -> None:
    lat = torch.zeros(1, 24, 1, 4, 6, dtype=torch.float16)
    for bad in (float("inf"), float("nan")):
        meta = {"kind": "image", "name": "v", "optimize_steps": bad}
        with pytest.raises(RefModError, match="numeric metadata"):
            bundle.mod_from_member(meta, lat, "v.safetensors")  # OverflowError/ValueError before the fix
    meta = {"kind": "audio", "name": "a", "sample_rate": float("inf")}
    with pytest.raises(RefModError, match="numeric metadata"):
        bundle.mod_from_member(meta, torch.zeros(1, 32, 2, 8), "a.safetensors")

    path = os.path.join(str(tmp_path), "bad.safetensors")
    bundle.write_bundle(path, "ok", [visual("v")])
    with safe_open(path, framework="pt") as fh:
        raw = dict(fh.metadata())
        tensors = {k: fh.get_tensor(k).clone() for k in fh.keys()}
    payload = json.loads(raw["refmod_meta"])
    payload["optimize_steps"] = float("inf")
    for m in payload.get("members", []):
        m["optimize_steps"] = float("inf")
    raw["refmod_meta"] = json.dumps(payload)
    save_file(tensors, path, metadata=raw)
    try:
        bundle.load_refmod_file(path)
    except RefModError:
        pass  # skipped cleanly
