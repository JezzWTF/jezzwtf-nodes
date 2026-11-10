"""Samplers: step trimming, combos, dispatch rules and error paths with recorded stand-ins."""
from __future__ import annotations

import sys
import types

import pytest
import torch

from refmod_h3 import _comfy, preview, samplers
from refmod_h3._types import RefModError
from v3_helpers import legacy, legacy_spec, run_node

LATENT = {"samples": torch.zeros(1, 4, 8, 8)}


@pytest.fixture()
def events(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, object]]]:
    sent: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(_comfy, "send_sync", lambda event, data, to_client=False: sent.append((event, data)))
    return sent


class Recorder:
    """Stands in for comfy_extras.nodes_custom_sampler and records every call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        rec = self

        def node(name: str, result: tuple[object, ...]) -> type:
            class N:
                @classmethod
                def execute(cls, **kwargs: object) -> tuple[object, ...]:
                    rec.calls.append((name, kwargs))
                    return result
            N.__name__ = name
            return N

        self.RandomNoise = node("RandomNoise", ("noise",))
        self.BasicGuider = node("BasicGuider", ("basic_guider",))
        self.CFGGuider = node("CFGGuider", ("cfg_guider",))
        self.KSamplerSelect = node("KSamplerSelect", ("sampler",))
        self.SamplerCustomAdvanced = node("SamplerCustomAdvanced", ({"samples": "out"}, {"samples": "denoised"}))

    @property
    def names(self) -> list[str]:
        return [n for n, _ in self.calls]

    def kwargs(self, name: str) -> dict[str, object]:
        return next(k for n, k in self.calls if n == name)


@pytest.fixture()
def rec(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    r = Recorder()
    monkeypatch.setattr(samplers, "_custom_core", lambda: r)
    monkeypatch.setattr(samplers, "widget_sigmas", lambda model, scheduler, steps, denoise: torch.linspace(1.0, 0.0, steps + 1))
    return r


def test_trim_sigmas_semantics() -> None:
    s = torch.linspace(1, 0, 11)  # 10 steps
    assert samplers.trim_sigmas(s, -1) is s and samplers.trim_sigmas(s, 0) is s
    assert samplers.trim_sigmas(s, 10) is s and samplers.trim_sigmas(s, 99) is s
    assert samplers.trim_sigmas(s, 3).shape[-1] == 4 and torch.equal(samplers.trim_sigmas(s, 3), s[:4])
    assert samplers.trim_sigmas(s, 9).shape[-1] == 10


def test_scheduler_helpers_and_combos() -> None:
    assert samplers.scheduler_choices()[0] == "none" and "beta" in samplers.scheduler_choices()
    assert samplers.default_scheduler(["none", "simple", "beta"]) == "beta"
    assert samplers.default_scheduler(["none", "simple"]) == "simple"
    assert samplers.real_scheduler("none") == "beta" and samplers.real_scheduler("beta") == "beta"
    assert samplers.real_scheduler("res4lyf_only") == "beta"
    assert all(not n.startswith("clown: ") for n in samplers.sampler_choices()) or samplers.res4lyf_sampler_names()


def test_res4lyf_discovery_is_soft_and_skips_shells(monkeypatch: pytest.MonkeyPatch) -> None:
    assert samplers.res4lyf_sampler_class() is None or isinstance(samplers.res4lyf_sampler_class(), type)
    shell = types.ModuleType("torch.ops.fake_samplers")
    shell.ClownsharKSampler_Beta = type("ClownsharKSampler_Beta", (), {})  # type: ignore[attr-defined]
    real = types.ModuleType("res4lyf_samplers")
    cls = type("ClownsharKSampler_Beta", (), {})
    real.ClownsharKSampler_Beta = cls  # type: ignore[attr-defined]
    rk = types.ModuleType("rk_coefficients")
    rk.get_sampler_name_list = lambda: ["res_2m", "res_3s"]  # type: ignore[attr-defined]
    helper = types.ModuleType("res4lyf_helper")
    helper.get_res4lyf_scheduler_list = lambda: ["beta57", "beta"]  # type: ignore[attr-defined]
    for name, mod in (("torch.ops.fake_samplers", shell), ("res4lyf_samplers", real), ("rk_coefficients", rk),
                      ("res4lyf_helper", helper)):
        monkeypatch.setitem(sys.modules, name, mod)
    assert samplers.res4lyf_sampler_class() is cls
    assert samplers.sampler_choices()[-2:] == ["clown: res_2m", "clown: res_3s"]
    assert samplers.scheduler_choices()[-1] == "beta57" and samplers.scheduler_choices().count("beta") == 1
    assert "beta57" not in samplers.scheduler_choices(include_res4lyf=False)


def test_node_ids_prefer_display_id() -> None:
    class Dyn:
        def get_display_node_id(self, uid: str) -> str:
            return f"display-{uid}"
    assert samplers.node_ids("5", Dyn()) == ("display-5", "5")
    assert samplers.node_ids("5", None) == ("5", "5")


def test_ultimate_interface() -> None:
    cls = samplers.JWTFUltimateKSampler
    spec = legacy_spec(cls)
    assert list(spec["required"]) == ["model", "positive", "latent_image", "sampler_name", "scheduler", "steps",
                                      "steps_to_run", "cfg", "cfg_enabled", "denoise", "seed", "eta",
                                      "sampler_mode", "bongmath", "decode", "tiled_decode", "preview_fps"]
    req = spec["required"]
    assert req["steps"][1]["default"] == 30 and req["cfg"][1]["default"] == 5.5 and req["cfg"][1]["round"] is False
    eta = dict(req["eta"][1])
    assert eta.pop("tooltip")
    assert eta == {"default": 0.5, "min": -100.0, "max": 100.0, "step": 0.01}
    assert req["sampler_mode"][0] == ["standard", "unsample", "resample"] and req["bongmath"][1]["default"] is True
    assert {"negative", "vae", "audio_vae", "sigmas", "options", "preview", "preview_max_res", "preview_frames",
            "preview_jpeg_quality", "preview_tiny_vae"} <= set(spec["optional"])
    assert spec["hidden"] == {"unique_id": "UNIQUE_ID", "dynprompt": "DYNPROMPT"}
    assert tuple(cls.RETURN_NAMES) == ("latent", "denoised", "image", "audio") and cls.OUTPUT_NODE and cls.CATEGORY == "JezzWTF/sampling"
    h3 = legacy_spec(samplers.JWTFH3KSampler)
    assert h3["required"]["steps"][1]["default"] == 8 and h3["required"]["scheduler"][0][0] == "none"
    assert {"noise", "guider", "sampler", "sigmas", "model", "positive"} <= set(h3["optional"])


def run_ultimate(**over: object) -> dict[str, object]:
    kw: dict[str, object] = dict(
        model=object(), positive=[["p"]], latent_image=LATENT, sampler_name="euler", scheduler="beta", steps=4,
        steps_to_run=-1, cfg=5.0, cfg_enabled=True, denoise=1.0, seed=7, eta=0.5, sampler_mode="standard",
        bongmath=True, decode=False, tiled_decode=False, preview_fps=12, preview=False, unique_id="9")
    kw.update(over)
    return run_node(samplers.JWTFUltimateKSampler, **kw)  # type: ignore[arg-type]


def test_ultimate_plain_path_uses_common_ksampler(monkeypatch: pytest.MonkeyPatch, rec: Recorder,
                                                  events: list[tuple[str, dict[str, object]]]) -> None:
    seen: dict[str, object] = {}
    fake = types.SimpleNamespace(
        NODE_CLASS_MAPPINGS={},
        common_ksampler=lambda model, seed, steps, cfg, sampler, scheduler, pos, neg, latent, denoise=1.0:
        seen.update(seed=seed, steps=steps, cfg=cfg, sampler=sampler, scheduler=scheduler, neg=neg, denoise=denoise)
        or ({"samples": "ksampled"},))
    monkeypatch.setattr(_comfy, "comfy_nodes", lambda: fake)
    out = run_ultimate(negative=[["n"]])
    assert seen["scheduler"] == "beta" and seen["cfg"] == 5.0 and seen["neg"] == [["n"]] and rec.calls == []
    latent, denoised, image, audio = out["result"]
    assert latent == {"samples": "ksampled"} and denoised is latent
    assert tuple(image.shape) == (1, 64, 64, 3) and audio["sample_rate"] == 44100 and audio["waveform"].shape == (1, 1, 1)
    assert out["ui"] == {"jezzwtf_source_id": ["9"]}
    assert [(e, d["phase"]) for e, d in events] == [("jezzwtf.uk_phase", "sampling"), ("jezzwtf.uk_phase", "done")]
    assert events[0][1]["node"] == "9" and events[0][1]["node_raw"] == "9"


def test_ultimate_custom_paths(rec: Recorder, events: list[tuple[str, dict[str, object]]]) -> None:
    # no negative: forced CFG off -> BasicGuider + custom path
    run_ultimate()
    assert rec.names == ["RandomNoise", "BasicGuider", "KSamplerSelect", "SamplerCustomAdvanced"]
    assert rec.kwargs("RandomNoise") == {"noise_seed": 7} and rec.kwargs("KSamplerSelect") == {"sampler_name": "euler"}
    rec.calls.clear()
    run_ultimate(negative=[["n"]], steps_to_run=2)  # chain sampling needs the custom path, with CFG
    assert rec.names == ["RandomNoise", "CFGGuider", "KSamplerSelect", "SamplerCustomAdvanced"]
    assert rec.kwargs("CFGGuider")["cfg"] == 5.0
    assert rec.kwargs("SamplerCustomAdvanced")["sigmas"].shape[-1] == 3  # trimmed to steps_to_run + 1
    rec.calls.clear()
    wired = torch.linspace(1, 0, 6)
    run_ultimate(negative=[["n"]], sigmas=wired, scheduler="none")
    assert torch.equal(rec.kwargs("SamplerCustomAdvanced")["sigmas"], wired)
    rec.calls.clear()
    run_ultimate(negative=[["n"]], cfg_enabled=False)
    assert "BasicGuider" in rec.names and "CFGGuider" not in rec.names


def test_ultimate_clown_dispatch_and_errors(monkeypatch: pytest.MonkeyPatch, rec: Recorder,
                                            events: list[tuple[str, dict[str, object]]]) -> None:
    with pytest.raises(RefModError, match="RES4LYF"):
        monkeypatch.setattr(samplers, "res4lyf_sampler_class", lambda: None)
        run_ultimate(sampler_name="clown: res_2m")
    captured: dict[str, object] = {}

    class Clown:
        @classmethod
        def execute(cls, **kwargs: object) -> tuple[object, ...]:
            captured.update(kwargs)
            return ({"samples": "c"}, {"samples": "cd"}, "opts")

    monkeypatch.setattr(samplers, "res4lyf_sampler_class", lambda: Clown)
    out = run_ultimate(sampler_name="clown: res_2m", negative=[["n"]], options="OPT", cfg_enabled=False)
    assert captured["sampler_name"] == "res_2m" and captured["cfg"] == 1.0 and captured["options_group"] == {"options0": "OPT"}
    assert captured["scheduler"] == "beta" and captured["sigmas"] is None and captured["bongmath"] is True
    assert out["result"][1] == {"samples": "cd"}
    with pytest.raises(RefModError, match="no sigmas"):
        run_ultimate(scheduler="none")


def test_decode_nested_latent_and_missing_vae(monkeypatch: pytest.MonkeyPatch) -> None:
    class Nested:
        is_nested = True

        def unbind(self) -> list[torch.Tensor]:
            return [torch.zeros(1, 4, 2, 2), torch.zeros(1, 2, 2)]

    decoded: list[object] = []

    class VAEDecode:
        def decode(self, vae: object, samples: dict[str, object]) -> tuple[torch.Tensor]:
            decoded.append(samples["samples"])
            return (torch.ones(1, 8, 8, 3),)

    tiled: list[tuple[object, ...]] = []

    class VAEDecodeTiled:
        def decode(self, vae: object, samples: dict[str, object], *args: object) -> tuple[torch.Tensor]:
            tiled.append(args)
            return (torch.ones(1, 8, 8, 3),)

    fake = types.SimpleNamespace(VAEDecode=VAEDecode, VAEDecodeTiled=VAEDecodeTiled, NODE_CLASS_MAPPINGS={},
                                 common_ksampler=None)
    monkeypatch.setattr(_comfy, "comfy_nodes", lambda: fake)
    image, audio = samplers.decode_latent({"samples": Nested()}, object(), None, tiled=False)  # type: ignore[dict-item]
    assert image.shape == (1, 8, 8, 3) and decoded[0].shape == (1, 4, 2, 2) and audio["sample_rate"] == 44100
    samplers.decode_latent({"samples": Nested()}, object(), None, tiled=True)  # type: ignore[dict-item]
    assert tiled == [(512, 64, 64, 8)]
    image, audio = samplers.decode_latent(LATENT, None, None, tiled=False)
    assert tuple(image.shape) == (1, 64, 64, 3)  # no VAE: warning + placeholder


def test_h3_sampler_error_matrix(rec: Recorder, events: list[tuple[str, dict[str, object]]]) -> None:
    node = samplers.JWTFH3KSampler
    base = dict(latent_image=LATENT, sampler_name="euler", scheduler="beta", steps=4, steps_to_run=-1,
                denoise=1.0, seed=1, decode=False, tiled_decode=False, preview_fps=12, preview=False)
    with pytest.raises(RefModError, match="connect a model or a guider"):
        run_node(node, **base)  # type: ignore[arg-type]
    with pytest.raises(RefModError, match="needs sigmas"):
        run_node(node, guider=object(), **base)  # type: ignore[arg-type]
    with pytest.raises(RefModError, match="positive"):
        run_node(node, model=object(), **base)  # type: ignore[arg-type]
    with pytest.raises(RefModError, match="no sigmas"):
        run_node(node, model=object(), positive=[["p"]], **{**base, "scheduler": "none"})  # type: ignore[arg-type]


def test_h3_sampler_defaults_and_wiring(rec: Recorder, events: list[tuple[str, dict[str, object]]]) -> None:
    node = samplers.JWTFH3KSampler
    base = dict(latent_image=LATENT, sampler_name="euler", scheduler="beta", steps=4, steps_to_run=2,
                denoise=1.0, seed=3, decode=False, tiled_decode=False, preview_fps=12, preview=False, unique_id="4")
    out = run_node(node, model=object(), positive=[["p"]], **base)  # type: ignore[arg-type]
    assert rec.names == ["RandomNoise", "BasicGuider", "KSamplerSelect", "SamplerCustomAdvanced"]  # never CFG
    assert rec.kwargs("SamplerCustomAdvanced")["sigmas"].shape[-1] == 3
    assert out["result"][0] == {"samples": "out"} and out["result"][1] == {"samples": "denoised"}
    rec.calls.clear()
    guider = types.SimpleNamespace(model_patcher=types.SimpleNamespace(clone=lambda: None, add_wrapper_with_key=lambda *a: None))
    run_node(node, noise="N", guider=guider, sampler="S", sigmas=torch.linspace(1, 0, 5), model=None,
                **{**base, "steps_to_run": -1})  # type: ignore[arg-type]
    assert rec.names == ["SamplerCustomAdvanced"]
    kw = rec.kwargs("SamplerCustomAdvanced")
    assert kw["noise"] == "N" and kw["guider"] is guider and kw["sampler"] == "S"


def test_guider_model_lookup_and_shallow_copy_for_preview(monkeypatch: pytest.MonkeyPatch, rec: Recorder,
                                                          events: list[tuple[str, dict[str, object]]]) -> None:
    class Patcher:
        def clone(self) -> "Patcher":
            return Patcher()

        def add_wrapper_with_key(self, *args: object) -> None:
            pass

    original = Patcher()
    guider = types.SimpleNamespace(model_patcher=original, other=1)
    assert samplers.guider_model(guider) is original
    assert samplers.guider_model(types.SimpleNamespace(model_patcher=object())) is None
    assert samplers.guider_model(None) is None
    clone = Patcher()
    monkeypatch.setattr(samplers, "attach_preview", lambda *a, **k: clone)
    run_node(samplers.JWTFH3KSampler, 
        latent_image=LATENT, sampler_name="euler", scheduler="beta", steps=4, steps_to_run=-1, denoise=1.0, seed=1,
        decode=False, tiled_decode=False, preview_fps=12, guider=guider, sigmas=torch.linspace(1, 0, 5), preview=True)
    used = rec.kwargs("SamplerCustomAdvanced")["guider"]
    assert used is not guider and used.model_patcher is clone and guider.model_patcher is original


def test_ui_events_and_wire_protocol_names(events: list[tuple[str, dict[str, object]]]) -> None:
    assert preview.WRAPPER_KEY == preview.EVENT == "kj_preview_override"
    assert samplers.PHASE_EVENT == "jezzwtf.uk_phase" and samplers.SOURCE_KEY == "jezzwtf_source_id"
    samplers.emit_phase("12", None, "decoding")
    assert events == [("jezzwtf.uk_phase", {"node": "12", "node_raw": "12", "phase": "decoding"})]


def test_h3_preview_clones_the_guider_model_not_the_model_input(monkeypatch: pytest.MonkeyPatch, rec: Recorder,
                                                                events: list[tuple[str, dict[str, object]]]) -> None:
    class Patcher:
        def __init__(self, tag: str) -> None:
            self.tag = tag

        def clone(self) -> "Patcher":
            return Patcher(self.tag + "-clone")

        def add_wrapper_with_key(self, *args: object) -> None:
            pass

    guided, plain = Patcher("guided-with-lora"), Patcher("plain-model")
    guider = types.SimpleNamespace(model_patcher=guided)
    attached: list[object] = []

    def fake_attach(model: Patcher, *args: object) -> Patcher:
        attached.append(model)
        return model.clone()

    monkeypatch.setattr(samplers, "attach_preview", fake_attach)
    sigma_models: list[object] = []
    monkeypatch.setattr(samplers, "widget_sigmas",
                        lambda model, scheduler, steps, denoise: sigma_models.append(model) or torch.linspace(1, 0, steps + 1))
    run_node(samplers.JWTFH3KSampler, 
        latent_image=LATENT, sampler_name="euler", scheduler="beta", steps=4, steps_to_run=-1, denoise=1.0, seed=1,
        decode=False, tiled_decode=False, preview_fps=12, guider=guider, model=plain, preview=True)
    assert attached == [guided]  # the guider's patched model, not `model`
    assert rec.kwargs("SamplerCustomAdvanced")["guider"].model_patcher.tag == "guided-with-lora-clone"  # type: ignore[attr-defined]
    assert sigma_models == [plain]  # `model` still supplies the schedule


def test_widget_sigmas_zero_denoise_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    fake = types.SimpleNamespace(calculate_sigmas=lambda ms, sched, n: calls.append(n) or torch.linspace(1, 0, n + 1))
    monkeypatch.setattr(_comfy, "optional_module", lambda name: fake)
    model = types.SimpleNamespace(get_model_object=lambda n: None)
    out = samplers.widget_sigmas(model, "beta", 20, 0.0)
    assert out.numel() == 0 and calls == []  # was ~3e7 sigmas
    assert samplers.widget_sigmas(model, "beta", 4, 0.5).shape[-1] == 5 and calls == [8]
