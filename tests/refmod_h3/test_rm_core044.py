"""Contract tests against the real ComfyUI 0.44 core (MiniMax H3 packed DiT, sparse attention, audio VAE).

They need the core's ``comfy`` package on ``sys.path`` and a torch that can import it. Run with the Desktop
interpreter, pointing at the core folder:

    set PYTHONPATH=<core dir>;<dir with pytest>
    "<Comfy Desktop>/ComfyUI/.venv/Scripts/python.exe" -m pytest tests/refmod_h3 -q

or set ``COMFY_CORE_DIR`` (the core folder is then appended to ``sys.path``). Without a usable core the whole
module is skipped, so the pure-logic suite still runs anywhere.
"""
from __future__ import annotations

import inspect
import os
import sys
from types import SimpleNamespace

import pytest
import torch
from v3_helpers import legacy

_core_dir = os.environ.get("COMFY_CORE_DIR")
if _core_dir and os.path.isdir(_core_dir) and _core_dir not in sys.path:
    sys.path.append(_core_dir)  # appended: the pack's own `nodes` package must keep precedence

try:
    from comfy.ldm.minimax import model as h3_model
    from comfy import model_base, model_sampling, sd as comfy_sd
    from comfy_extras import nodes_audio, nodes_minimax_h3, nodes_sparse_attention
except Exception as exc:  # pragma: no cover - depends on the environment
    pytest.skip(f"ComfyUI 0.44 core is not importable here: {exc}", allow_module_level=True)

from refmod_h3 import _comfy, curves, extract, image_edit, preview, samplers, ultimate_loader
from refmod_h3.bundle import RefMod


def _mod(kind: str, shape: tuple[int, ...]) -> RefMod:
    return RefMod(name=kind, kind=kind, latent=torch.zeros(*shape))


# --------------------------------------------------------------------------- reference blocks vs PackedLayout

def test_refmod_blocks_pack_into_the_core_layout_with_matching_token_counts() -> None:
    mods = [_mod("image", (1, 24, 1, 4, 6)), _mod("video", (1, 24, 2, 4, 4)), _mod("audio", (1, 32, 2, 10))]
    blocks = [curves.make_block(m, m.latent) for m in mods]
    layout = h3_model.PackedLayout(7, 2, 4, 4, 10, refs=blocks)
    refs = [(b - a, kind) for a, b, kind in layout.segments if kind.startswith("ref_")]
    # image 2x3 cells, video 2 frames of 2x2 cells, audio 2 stereo rows per latent frame
    assert refs == [(6, "ref_img"), (8, "ref_img"), (20, "ref_audio")]
    assert [m.token_count for m in mods] == [6, 8, 20]


def test_refmod_blocks_carry_every_key_core_blocks_have() -> None:
    class Clip:
        def tokenize(self, prompt: str, **_: object) -> dict[str, str]:
            return {"p": prompt}

        def encode_from_tokens_scheduled(self, tokens: dict[str, str]) -> list[list[object]]:
            return [[torch.zeros(1, 4), {}]]

    class Vae:
        def encode(self, pixels: torch.Tensor) -> torch.Tensor:
            t, h, w, _ = pixels.shape
            return torch.zeros(1, 24, max(1, t), h // 16, w // 16)

    class AudioVae:
        audio_sample_rate = 32000

        def encode(self, wave: torch.Tensor) -> torch.Tensor:
            return torch.zeros(1, 32, 2, max(1, wave.shape[1] // 800))

    wave = {"waveform": torch.zeros(1, 2, 32000), "sample_rate": 32000}
    out = nodes_minimax_h3.MiniMaxH3ReferenceToVideo.execute(
        Clip(), "p", 64, 64, 5, vae=Vae(), audio_vae=AudioVae(),
        ref_images={"ref_image_1": torch.zeros(1, 64, 64, 3)},
        ref_videos={"ref_video_1": torch.zeros(5, 64, 64, 3)}, ref_audios={"ref_audio_1": wave})
    core_blocks = {b["kind"]: b for b in out.args[0][0][1]["minimax_refs"]}
    ours = {"image": curves.make_block(_mod("image", (1, 24, 1, 4, 4)), torch.zeros(1, 24, 1, 4, 4)),
            "video": curves.make_block(_mod("video", (1, 24, 2, 4, 4)), torch.zeros(1, 24, 2, 4, 4)),
            "audio": curves.make_block(_mod("audio", (1, 32, 2, 8)), torch.zeros(1, 32, 2, 8))}
    for kind, core in core_blocks.items():
        assert set(core) <= set(ours[kind]), (kind, set(core) - set(ours[kind]))


def test_injected_blocks_flow_through_the_model_condition_collection() -> None:
    mods = [_mod("image", (1, 24, 1, 4, 4)), _mod("video", (1, 24, 2, 4, 4)), _mod("audio", (1, 32, 2, 8))]
    cond = [[torch.zeros(1, 4), {"text": "x"}]]
    out, count = curves.apply_rows(cond, [(m, 1.0) for m in mods], 1.0)
    assert count == 3
    refs = out[0][1]["minimax_refs"]
    packed = model_base.MiniMaxH3._cond_latents(None, refs)
    assert len(packed["cond_video_latents"]) == 2   # image + video; the audio block has no picture latent
    assert len(packed["cond_audio_latents"]) == 1   # video blocks carry audio_latent=None


# --------------------------------------------------------------------------- audio VAE

class _CoreStyleAudioVae:
    """Looks like ``comfy.sd.VAE`` around ``MiniMaxH3AudioVAE``: ``encode`` takes ``[B, L, C]``."""

    latent_dim = 2
    patcher = object()

    def __init__(self) -> None:
        self.first_stage_model = type("MiniMaxH3AudioVAE", (), {})()
        self.shapes: list[tuple[int, ...]] = []

    def encode(self, wave: torch.Tensor) -> torch.Tensor:
        self.shapes.append(tuple(wave.shape))
        return torch.zeros(1, 32, 2, -(-wave.shape[1] // 800), dtype=torch.float16)


def test_audio_extraction_uses_the_public_vae_encode_with_channels_last_chunks() -> None:
    vae = _CoreStyleAudioVae()
    wave = torch.zeros(1, 2, 32000 * 25)  # 25 s: three 10 s chunks (the last one partial)
    z = extract.encode_audio(vae, wave)
    assert vae.shapes == [(1, 320000, 2), (1, 320000, 2), (1, 160000, 2)]
    assert z.dtype == torch.float32 and z.shape == (1, 32, 2, 1000)


def test_audio_extraction_falls_back_to_the_first_stage_model() -> None:
    vae = _CoreStyleAudioVae()
    vae.encode = lambda wave: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]
    seen: list[tuple[int, ...]] = []
    vae.first_stage_model.encode = lambda w: (seen.append(tuple(w.shape)), torch.zeros(1, 32, 2, w.shape[-1] // 800))[1]  # type: ignore[attr-defined]
    z = extract.encode_audio(vae, torch.zeros(1, 2, 16000))
    assert seen == [(1, 2, 16000)] and z.shape == (1, 32, 2, 20)


def test_core_resampler_has_the_signature_our_wrapper_calls() -> None:
    wave = torch.randn(1, 2, 4410)
    out = extract.resample_audio(wave, 44100, 32000)
    assert out.shape == (1, 2, 3200)


def test_nested_audio_latent_decodes_through_core_vae_decode_audio() -> None:
    from comfy.nested_tensor import NestedTensor

    class AudioVae:
        audio_sample_rate = 32000

        def decode(self, latent: torch.Tensor) -> torch.Tensor:  # comfy.sd.VAE.decode returns [B, L, C]
            assert latent.shape == (1, 32, 2, 4)
            return torch.randn(1, 3200, 2)

    latent = {"samples": NestedTensor((torch.zeros(1, 24, 2, 4, 4), torch.zeros(1, 32, 2, 4)))}
    audio = samplers.decode_audio_latent(latent, AudioVae())
    assert audio["waveform"].shape == (1, 2, 3200) and audio["sample_rate"] == 32000
    assert hasattr(nodes_audio, "vae_decode_audio")


# --------------------------------------------------------------------------- preview

def test_audio_preview_reads_the_rate_of_a_real_style_audio_vae() -> None:
    avae = SimpleNamespace(audio_sample_rate=32000, first_stage_model=SimpleNamespace(output_sample_rate=32000),
                           patcher=object(), device="cpu")
    assert preview.audio_vae_rate(avae) == 32000
    assert preview.audio_vae_rate(SimpleNamespace(first_stage_model=SimpleNamespace(output_sample_rate=16000))) == 16000
    assert preview.audio_vae_rate(None) == 0


def test_audio_preview_is_enabled_for_flow_av_with_the_real_model_sampling(monkeypatch: pytest.MonkeyPatch) -> None:
    ms = model_sampling.ModelSamplingAV(None)
    ms.set_parameters(shift=12.0, audio_shift=3.0)
    assert ms.audio_scale == 4.0
    mp = SimpleNamespace(model=SimpleNamespace(model_type=model_base.ModelType.FLOW_AV))
    avae = SimpleNamespace(audio_sample_rate=32000, first_stage_model=SimpleNamespace(), patcher=object())
    dec = preview.PreviewWrapper(256, "n", frames=4, audio_vae=avae)._audio_setup(mp, ms)
    assert dec is not None
    # still images carry no clip to score against
    assert preview.PreviewWrapper(256, "n", frames=1, audio_vae=avae)._audio_setup(mp, ms) is None


def test_core_nested_callback_views_unpack_into_video_and_audio() -> None:
    from comfy.nested_tensor import NestedTensor

    video, audio = torch.randn(1, 24, 2, 3, 3), torch.randn(1, 32, 2, 5)
    parts = preview.unpack_parts(NestedTensor((video, audio)), [video.shape, audio.shape])
    assert len(parts) == 2 and torch.equal(parts[0], video) and torch.equal(parts[1], audio)


def test_taeh3_is_a_video_tiny_vae() -> None:
    assert preview.is_video_tae("taeh3.safetensors") and preview.is_video_tae("taeltx_2.safetensors")
    assert not preview.is_video_tae("taef1_decoder.pth")


# --------------------------------------------------------------------------- Ultimate Model Loader

def test_clip_types_resolve_to_the_0044_enum_members() -> None:
    cl = comfy_sd.CLIPType
    assert ultimate_loader.clip_type_value("auto", "minimax_h3") is cl.MINIMAX
    assert ultimate_loader.clip_type_value("auto", "flux3") is cl.FLUX3
    assert ultimate_loader.clip_type_value("auto", "moss") is cl.MOSS_IMAGE
    assert ultimate_loader.clip_type_value("minimax", "default") is cl.MINIMAX
    assert ultimate_loader.clip_type_value("minimax_h3", "default") is cl.MINIMAX   # saved workflows
    names = ultimate_loader.clip_type_names()
    assert names[0] == "auto" and "minimax" in names and names.index("minimax") < names.index("yue2")


def test_quant_choices_list_the_core_algorithms() -> None:
    from comfy import quant_ops

    choices = ultimate_loader.quant_choices()
    assert choices[:2] == ["auto", "bf16"] and set(quant_ops.QUANT_ALGOS) <= set(choices)


def test_attention_registry_and_optimized_attention_override() -> None:
    from comfy.ldm.modules import attention
    from comfy.model_patcher import ModelPatcher

    getter = ultimate_loader.registry_getter()
    assert getter("pytorch") is attention.attention_pytorch
    name, fn, warnings = ultimate_loader.resolve_backend({"pytorch": True}, getter)
    assert (name, fn, warnings) == ("pytorch", attention.attention_pytorch, [])
    patcher = ModelPatcher(torch.nn.Linear(1, 1), torch.device("cpu"), torch.device("cpu"))
    clone = ultimate_loader.set_attention(patcher, fn)
    assert clone is not patcher
    assert "optimized_attention_override" in clone.model_options["transformer_options"]
    assert "optimized_attention_override" not in patcher.model_options["transformer_options"]


def test_sparse_attention_call_matches_the_core_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    real = nodes_sparse_attention.apply_block_sparse_attention
    sig = inspect.signature(real)
    seen: dict[str, object] = {}

    def spy(model: object, **kwargs: object) -> object:
        sig.bind(model, **kwargs)  # raises TypeError on an unknown or missing keyword
        seen.update(kwargs)
        return model

    monkeypatch.setattr(nodes_sparse_attention, "apply_block_sparse_attention", spy)
    marker = SimpleNamespace(get_model_object=lambda name: type("MiniMaxH3Model", (), {})())
    assert ultimate_loader.apply_sparse(marker, True, "minimax_h3") is marker
    assert seen["vsa"] is True and seen["extra_tokens"] == 0 and seen["dense_blocks"] == set()
    ultimate_loader.apply_sparse(marker, False, "minimax_h3")
    assert seen["vsa"] is False and seen["extra_tokens"] == 256


def test_vsa_on_a_non_h3_model_fails_readably() -> None:
    other = SimpleNamespace(get_model_object=lambda name: torch.nn.Linear(1, 1))
    with pytest.raises(ultimate_loader.RefModError, match="MiniMax H3"):
        ultimate_loader.apply_sparse(other, True, "default")


# --------------------------------------------------------------------------- H3 Image Edit

class _Clip:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def tokenize(self, prompt: str, **_: object) -> dict[str, str]:
        self.prompts.append(prompt)
        return {"p": prompt}

    def encode_from_tokens_scheduled(self, tokens: dict[str, str]) -> list[list[object]]:
        return [[torch.zeros(1, 4), {}]]


class _Ph3Vae:
    def __init__(self) -> None:
        self.first_stage_model = type("PH3ImageVAE", (), {})()
        self.decoded: list[tuple[int, ...]] = []

    def encode(self, pixels: torch.Tensor) -> torch.Tensor:
        return torch.zeros(1, 24, 1, pixels.shape[1] // 16, pixels.shape[2] // 16)

    def decode(self, latent: torch.Tensor) -> torch.Tensor:
        self.decoded.append(tuple(latent.shape))
        return torch.full((1, 1, latent.shape[3] * 16, latent.shape[4] * 16, 3), 0.5)  # 5-D like the video VAEs


def _patch_edit(monkeypatch: pytest.MonkeyPatch, seen: dict[str, object]) -> None:
    def sample(model: object, noise: object, steps: int, cfg: float, sampler: str, sched: str, pos: object,
               neg: object, latent: object, **kw: object) -> object:
        seen["sample_latent"] = latent
        seen["neg_is_pos"] = neg is pos
        return latent

    fake = SimpleNamespace(prepare_noise=lambda lat, seed: lat, sample=sample)
    monkeypatch.setattr(_comfy, "comfy_nodes", lambda: None)
    monkeypatch.setattr(_comfy, "optional_module", lambda n: fake if n == "comfy.sample" else None)
    monkeypatch.setattr(_comfy, "send_sync", lambda *a, **k: None)


def test_image_edit_uses_ph3_conditioning_for_the_p_h3_image_vae(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    _patch_edit(monkeypatch, seen)
    monkeypatch.setattr(image_edit, "_core_node_class",
                        lambda name=image_edit.CORE_NODE: getattr(nodes_minimax_h3, "PH3ImageConditioning")
                        if name == image_edit.PH3_NODE else None)
    monkeypatch.setattr(image_edit, "ensure_unit_shift", lambda m: m)
    clip, vae = _Clip(), _Ph3Vae()
    img = torch.rand(1, 512, 768, 3)
    final, native, positive, latent, w, h = legacy(image_edit.JWTFH3ImageEdit.execute(
        object(), clip, vae, "make it red", 0, 0, 1, 0, 7, 4, 1.0, "euler", "simple", 1.0, image=img))
    assert clip.prompts == ["Edit <Picture 1>. make it red"]               # core adds the edit prefix
    assert positive[0][1]["minimax_refs"][0]["kind"] == "image"
    assert latent["samples"].is_nested and latent["samples"].unbind()[0].shape[2] == 1   # one picture frame
    assert vae.decoded == [tuple(latent["samples"].unbind()[0].shape)]      # only the picture stream is decoded
    assert (w, h) == (768, 512) and final.shape == (1, 512, 768, 3)         # resized back to the source
    assert seen["neg_is_pos"] is True                                       # cfg 1.0: no empty-prompt encode


def test_image_edit_uses_the_video_conditioning_node_for_other_vaes(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    _patch_edit(monkeypatch, seen)
    requested: list[str] = []

    def core(name: str = image_edit.CORE_NODE) -> type | None:
        requested.append(name)
        return getattr(nodes_minimax_h3, "MiniMaxH3ImageToVideo")

    monkeypatch.setattr(image_edit, "_core_node_class", core)

    class VideoVae:
        def encode(self, pixels: torch.Tensor) -> torch.Tensor:
            return torch.zeros(1, 24, 1, pixels.shape[1] // 16, pixels.shape[2] // 16)

        def decode(self, latent: torch.Tensor) -> torch.Tensor:
            assert latent.dim() == 5 and latent.shape[1] == 24
            return torch.zeros(5, latent.shape[3] * 16, latent.shape[4] * 16, 3)

    final, native, positive, latent, w, h = legacy(image_edit.JWTFH3ImageEdit.execute(
        object(), _Clip(), VideoVae(), "p", 0, 0, 1, 0, 1, 4, 1.0, "euler", "simple", 1.0, image=torch.rand(1, 256, 256, 3)))
    assert requested == [image_edit.CORE_NODE]
    assert positive[0][1]["minimax_keyframes"][0]["resolved_frame_index"] == 0
    assert latent["samples"].is_nested and (w, h) == (256, 256)


def test_unit_shift_is_only_patched_when_the_model_is_not_already_at_one(monkeypatch: pytest.MonkeyPatch) -> None:
    unit = model_sampling.ModelSamplingAV(None)
    unit.set_parameters(shift=1.0, audio_shift=1.0)
    ok = SimpleNamespace(get_model_object=lambda n: unit)
    assert image_edit.ensure_unit_shift(ok) is ok

    shifted = model_sampling.ModelSamplingAV(None)
    shifted.set_parameters(shift=12.0, audio_shift=3.0)
    called: dict[str, object] = {}

    class Shift:
        FUNCTION = "go"

        def go(self, model: object, shift_video: float, shift_audio: float) -> tuple[object]:
            called.update(v=shift_video, a=shift_audio)
            return ("patched",)

    monkeypatch.setattr(image_edit, "_core_node_class", lambda name=image_edit.CORE_NODE: Shift)
    assert image_edit.ensure_unit_shift(SimpleNamespace(get_model_object=lambda n: shifted)) == "patched"
    assert called == {"v": 1.0, "a": 1.0}


def test_core_h3_nodes_the_family_relies_on_exist() -> None:
    names = {c.__name__ for c in (nodes_minimax_h3.MiniMaxH3ImageToVideo, nodes_minimax_h3.MiniMaxH3ReferenceToVideo,
                                  nodes_minimax_h3.PH3ImageConditioning, nodes_minimax_h3.MiniMaxH3SigmaShift,
                                  nodes_minimax_h3.MiniMaxH3LatentUpscaleWithModel)}
    assert len(names) == 5
