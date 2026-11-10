"""H3 Image Edit: the sampler call mirrors core's common_ksampler."""
from __future__ import annotations

import types

import pytest
import torch

from refmod_h3 import _comfy, image_edit
from v3_helpers import legacy


def test_seed_is_passed_to_comfy_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class Core:
        FUNCTION = "go"

        def go(self, **kw: object) -> tuple[object, dict[str, torch.Tensor]]:
            return "pos", {"samples": torch.zeros(1, 4, 1, 2, 2)}

    def sample(model: object, noise: object, steps: int, cfg: float, sampler: str, sched: str, pos: object,
               neg: object, latent: object, **kw: object) -> torch.Tensor:
        seen.update(kw)
        return torch.zeros(1, 4, 1, 2, 2)

    fake_sample = types.SimpleNamespace(prepare_noise=lambda lat, seed: lat, sample=sample)
    monkeypatch.setattr(image_edit, "_core_node_class", lambda name=image_edit.CORE_NODE: Core)
    monkeypatch.setattr(_comfy, "comfy_nodes", lambda: None)
    monkeypatch.setattr(_comfy, "optional_module", lambda n: fake_sample if n == "comfy.sample" else None)
    monkeypatch.setattr(_comfy, "send_sync", lambda *a, **k: None)
    vae = types.SimpleNamespace(decode=lambda s: torch.rand(1, 8, 8, 3))
    legacy(image_edit.JWTFH3ImageEdit.execute(object(), object(), vae, "p", 64, 64, 1, 0, 1234, 4, 1.0, "euler", "simple", 1.0))
    assert seen["seed"] == 1234 and seen["denoise"] == 1.0
