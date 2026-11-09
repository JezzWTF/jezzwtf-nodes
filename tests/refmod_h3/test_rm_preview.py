"""Preview wrapper regressions: packed audio latents, setup failures, encoder shutdown."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
import torch

from refmod_h3 import _comfy, preview


def test_audio_preview_unpacks_latents_packed_by_the_guider(monkeypatch: pytest.MonkeyPatch) -> None:
    utils = pytest.importorskip("comfy.utils")
    real = _comfy.optional_module
    # builds before 0.44 have no ModelType.FLOW_AV; stand in for the enum only there
    mb = real("comfy.model_base")
    if not hasattr(getattr(mb, "ModelType", None), "FLOW_AV"):
        mb = SimpleNamespace(ModelType=SimpleNamespace(FLOW_AV="flow_av"))
        monkeypatch.setattr(preview._comfy, "optional_module", lambda n: mb if n == "comfy.model_base" else real(n))
    video, audio = torch.randn(1, 4, 2, 3, 3), torch.randn(1, 8, 5)
    packed, shapes = utils.pack_latents([video, audio])
    assert not packed.is_nested and packed.shape[:2] == (1, 1)

    seen: dict[str, torch.Tensor] = {}

    class Fsm:
        def decode(self, lat: torch.Tensor) -> torch.Tensor:
            seen["lat"] = lat
            return torch.randn(1, 2, 64)

    avae = SimpleNamespace(first_stage_model=Fsm(), audio_sample_rate=16000, patcher=object(), device="cpu")
    mp = SimpleNamespace(model=SimpleNamespace(model_type=mb.ModelType.FLOW_AV))
    ms = SimpleNamespace(audio_scale=1.0)
    wrapper = preview.PreviewWrapper(256, "n", frames=4, audio_vae=avae)
    dec = wrapper._audio_setup(mp, ms, shapes)
    assert dec is not None
    wav, rate = dec(packed, 4)
    assert wav is not None and rate == 16000
    assert torch.equal(seen["lat"], audio)


def test_setup_failure_still_samples_and_leaves_no_encoder_thread() -> None:
    class Boom:
        load_device = "cpu"
        model = None

        def get_model_object(self, name: str) -> object:
            raise RuntimeError("setup broke")

    calls: list[object] = []

    class Executor:
        class_obj = SimpleNamespace(model_patcher=Boom())

        def __call__(self, noise: torch.Tensor, latent: torch.Tensor, sampler: object, sigmas: torch.Tensor,
                     mask: object, callback: object, disable_pbar: bool, seed: int | None, **kw: object) -> torch.Tensor:
            calls.append(callback)
            return latent

    def previewers() -> list[threading.Thread]:
        return [t for t in threading.enumerate() if t.name == "jwtf-preview" and t.is_alive()]

    sentinel = object()
    before = len(previewers())
    out = preview.PreviewWrapper(256, "n")(Executor(), torch.zeros(1, 4, 2, 2), torch.ones(1, 4, 2, 2), object(),
                                           torch.tensor([1.0, 0.0]), None, sentinel, False, 0)  # type: ignore[arg-type]
    assert out.shape == (1, 4, 2, 2) and calls == [sentinel]
    deadline = time.time() + 3
    while len(previewers()) > before and time.time() < deadline:
        time.sleep(0.05)
    assert len(previewers()) == before


def test_encoder_stops_even_when_the_queue_stays_full(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()
    monkeypatch.setattr(preview.PreviewEncoder, "_send", lambda self, job: release.wait(5))
    enc = preview.PreviewEncoder("n", 64, 80)
    job = preview._Job([], {}, 12.0, None, 0)
    for _ in range(4):
        enc.submit(job)
    t0 = time.time()
    enc.stop(timeout=0.3)
    assert time.time() - t0 < 2
    release.set()
    enc.thread.join(3)
    assert not enc.thread.is_alive()


def test_unpack_parts_passthrough_for_unpacked_latents() -> None:
    assert preview.unpack_parts(torch.zeros(1, 1, 4), [torch.Size([1, 4])]) == []
    assert _comfy is not None
