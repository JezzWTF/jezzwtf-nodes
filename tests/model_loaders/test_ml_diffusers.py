from __future__ import annotations

from pathlib import Path

import json

import pytest

from model_loaders.diffusers_logic import (
    DiffusersComponents,
    describe_backend,
    resolve_backend,
    backend_choice,
    collect_roots,
    diffusers_components,
    is_diffusers_dir,
    resolve_model,
    scan_models,
)


def _touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")


def test_scan_records_folders_once_and_files(tmp_path: Path) -> None:
    r1, r2 = tmp_path / "r1", tmp_path / "r2"
    _touch(r1 / "flux.safetensors")
    _touch(r1 / "sub" / "q.gguf")
    _touch(r1 / "notes.txt")
    _touch(r1 / "sd15" / "model_index.json")
    _touch(r1 / "sd15" / "unet" / "diffusion_pytorch_model.safetensors")  # not descended into
    _touch(r1 / "pipe" / "UNet" / "x.bin")
    _touch(r2 / "flux.safetensors")
    _touch(r2 / "single" / "diffusion_pytorch_model.fp16.safetensors")
    _touch(r1 / "diffusion_pytorch_model.bin")  # file directly in a root is just a file
    names = scan_models([str(r1), str(r2)])
    assert names == sorted(["diffusion_pytorch_model.bin", "flux.safetensors", "pipe", "sd15", "single", "sub/q.gguf"])
    assert resolve_model([str(r1), str(r2)], "single") == str(r2 / "single")
    assert resolve_model([str(r1), str(r2)], "flux.safetensors") == str(r1 / "flux.safetensors")
    assert resolve_model([str(r1)], "../r2/flux.safetensors") is None
    assert not is_diffusers_dir(str(r1 / "sub"))


def test_collect_roots_dedupes_and_filters(tmp_path: Path) -> None:
    (tmp_path / "models" / "unet").mkdir(parents=True)
    (tmp_path / "models" / "diffusers").mkdir()
    roots = collect_roots([str(tmp_path / "models" / "unet"), str(tmp_path / "missing")], [str(tmp_path / "models")])
    assert roots == [str(tmp_path / "models" / "unet"), str(tmp_path / "models" / "diffusers")]


def test_components_lookup_order(tmp_path: Path) -> None:
    d = tmp_path / "pipe"
    _touch(d / "diffusion_pytorch_model.bin")
    _touch(d / "unet" / "diffusion_pytorch_model.safetensors")
    _touch(d / "text_encoder" / "pytorch_model.bin")
    _touch(d / "text_encoder" / "model.safetensors")
    _touch(d / "text_encoder_2" / "model.fp16.safetensors")
    _touch(d / "vae" / "diffusion_pytorch_model.fp16.safetensors")
    parts = diffusers_components(str(d))
    assert parts.unet == [str(d / "unet" / "diffusion_pytorch_model.safetensors")]
    assert parts.encoders == [[str(d / "text_encoder" / "model.safetensors")],
                              [str(d / "text_encoder_2" / "model.fp16.safetensors")]]
    assert parts.vae == [str(d / "vae" / "diffusion_pytorch_model.fp16.safetensors")]
    assert diffusers_components(str(tmp_path)) == DiffusersComponents()


def test_backend_choice_sage_wins() -> None:
    assert backend_choice("None", "None") is None
    assert backend_choice("None", "FlashAttention 2") == "FlashAttention 2"
    assert backend_choice("SageAttention 3", "FlashAttention 2") == "SageAttention 3"


def test_transformer_folder_is_found_and_scanned(tmp_path: Path) -> None:
    d = tmp_path / "flux"
    _touch(d / "transformer" / "diffusion_pytorch_model.safetensors")
    assert diffusers_components(str(d)).unet == [str(d / "transformer" / "diffusion_pytorch_model.safetensors")]
    only_transformer = tmp_path / "root" / "wan"
    _touch(only_transformer / "transformer" / "x.bin")
    assert scan_models([str(tmp_path / "root")]) == ["wan"]


def test_plain_weights_beat_fp16_but_fp16_is_used_alone(tmp_path: Path) -> None:
    a = tmp_path / "a" / "unet"
    _touch(a / "diffusion_pytorch_model.fp16.safetensors")
    _touch(a / "diffusion_pytorch_model.safetensors")
    assert diffusers_components(str(tmp_path / "a")).unet == [str(a / "diffusion_pytorch_model.safetensors")]
    b = tmp_path / "b" / "unet"
    _touch(b / "diffusion_pytorch_model.fp16.safetensors")
    assert diffusers_components(str(tmp_path / "b")).unet == [str(b / "diffusion_pytorch_model.fp16.safetensors")]


def test_sharded_text_encoder_via_index_and_numbering(tmp_path: Path) -> None:
    d = tmp_path / "sd3"
    te = d / "text_encoder_3"
    _touch(te / "model-00001-of-00002.safetensors")
    _touch(te / "model-00002-of-00002.safetensors")
    (te / "model.safetensors.index.json").write_text(json.dumps(
        {"weight_map": {"a": "model-00002-of-00002.safetensors", "b": "model-00001-of-00002.safetensors"}}))
    expect = [str(te / "model-00001-of-00002.safetensors"), str(te / "model-00002-of-00002.safetensors")]
    assert diffusers_components(str(d)).encoders == [expect]
    (te / "model.safetensors.index.json").unlink()  # numbering alone also works
    assert diffusers_components(str(d)).encoders == [expect]


def test_missing_shard_raises_instead_of_dropping_the_encoder(tmp_path: Path) -> None:
    d = tmp_path / "pipe"
    te = d / "text_encoder"
    _touch(te / "model-00001-of-00003.safetensors")
    _touch(te / "model-00003-of-00003.safetensors")
    with pytest.raises(FileNotFoundError, match="incomplete"):
        diffusers_components(str(d))
    (te / "model-00003-of-00003.safetensors").unlink()
    (te / "model-00001-of-00003.safetensors").unlink()
    _touch(te / "model-00001-of-00002.safetensors")
    (te / "model.safetensors.index.json").write_text(json.dumps(
        {"weight_map": {"a": "model-00001-of-00002.safetensors", "b": "model-00002-of-00002.safetensors"}}))
    with pytest.raises(FileNotFoundError, match="missing"):
        diffusers_components(str(d))


def test_sharded_unet_in_transformer(tmp_path: Path) -> None:
    t = tmp_path / "q" / "transformer"
    for i in (1, 2):
        _touch(t / f"diffusion_pytorch_model-0000{i}-of-00002.safetensors")
    assert diffusers_components(str(tmp_path / "q")).unet == [
        str(t / f"diffusion_pytorch_model-0000{i}-of-00002.safetensors") for i in (1, 2)]


def test_backend_resolution_labels_generic_flash() -> None:
    registry = {"flash": "FN", "sage": "SG"}
    assert resolve_backend("FlashAttention 3", registry.get) == ("FN", "flash")
    assert resolve_backend("SageAttention 3", registry.get) is None
    assert "generic 'flash'" in describe_backend("FlashAttention 3", "flash")
    assert describe_backend("FlashAttention 2", "flash") == "FlashAttention 2 (registry 'flash')"
