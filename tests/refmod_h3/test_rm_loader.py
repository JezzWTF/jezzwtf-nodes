"""Ultimate Model Loader: backend priority, quantisation report, CLIP types, sparse guards, interface."""
from __future__ import annotations

import pytest

from refmod_h3 import ultimate_loader as ul
from refmod_h3._types import RefModError


def registry(*names: str):
    table = {n: (lambda *a, **k: n) for n in names}
    return lambda name: table.get(name)


def test_backend_priority_order() -> None:
    everything = registry("sage3", "sage", "flash", "comfy_kitchen_int8", "pytorch")
    on = {"kitchen": True, "sage2": True, "sage3": True, "flash2": True, "pytorch": True}
    assert ul.resolve_backend(on, everything)[0] == "sage3"
    assert ul.resolve_backend({**on, "sage3": False}, everything)[0] == "sage"
    assert ul.resolve_backend({**on, "sage3": False, "sage2": False}, everything)[0] == "flash"
    assert ul.resolve_backend({"kitchen": True, "pytorch": True}, everything)[0] == "comfy_kitchen_int8"
    assert ul.resolve_backend({"pytorch": True}, everything)[0] == "pytorch"
    assert ul.resolve_backend({}, everything) == (None, None, [])


def test_backend_probes_alternate_names_and_warns_when_nothing_registered() -> None:
    name, fn, warnings = ul.resolve_backend({"sage2": True}, registry("sageattn"))
    assert name == "sageattn" and callable(fn) and warnings == []
    name, fn, warnings = ul.resolve_backend({"sage3": True, "flash2": True}, registry("flash_attn"))
    assert name == "flash_attn" and len(warnings) == 1 and "sage3 is enabled" in warnings[0]  # falls through to flash
    name, fn, warnings = ul.resolve_backend({"kitchen": True}, registry())
    assert name is None and fn is None and "kitchen is enabled" in warnings[0]

    def exploding(_name: str):
        raise RuntimeError("registry broke")
    assert ul.resolve_backend({"pytorch": True}, exploding)[0] is None


def test_kitchen_defaults_on_and_loses_to_any_higher_switch() -> None:
    spec = ul.JWTFUltimateModelLoader.INPUT_TYPES()["required"]
    assert spec["kitchen"][1]["default"] is True
    assert all(spec[k][1]["default"] is False for k in ("sage2", "sage3", "triton", "flash2", "pytorch", "sparse", "vsa"))
    reg = registry("comfy_kitchen_int8", "sage")
    assert ul.resolve_backend({"kitchen": True}, reg)[0] == "comfy_kitchen_int8"
    assert ul.resolve_backend({"kitchen": True, "sage2": True}, reg)[0] == "sage"


def test_interface_matches_spec() -> None:
    cls = ul.JWTFUltimateModelLoader
    spec = cls.INPUT_TYPES()
    req = spec["required"]
    assert list(req)[:3] == ["model_name", "quant_format", "model_type"]
    assert list(req)[-5:] == ["heading_model", "heading_engine", "heading_clips", "heading_vaes", "section_order"]
    assert req["model_type"][0] == ["default", "minimax_h3", "flux3", "moss"]
    assert req["section_order"][1]["default"] == "model,engine,clips,vaes"
    assert [req[k][1]["default"] for k in ("heading_model", "heading_engine", "heading_clips", "heading_vaes")] == \
           ["Model", "Efficiencies", "Text Encoders", "VAEs"]
    assert req["kitchen"][1]["label_on"] == req["kitchen"][1]["label_off"] == "kitchen"
    assert req["clip1_device"][0] == ["default", "cpu"] and req["clip2_enabled"][1]["default"] is False
    assert spec["hidden"] == {"unique_id": "UNIQUE_ID"}
    assert cls.RETURN_TYPES == ("MODEL", "CLIP", "CLIP", "VAE", "VAE")
    assert cls.RETURN_NAMES == ("MODEL", "CLIP (main)", "CLIP (enhancer)", "VAE (video/default)", "VAE (audio)")
    assert cls.CATEGORY == "JezzWTF/loaders" and cls.VALIDATE_INPUTS() is True
    assert req["quant_format"][0][:2] == ["auto", "bf16"]


def test_sparse_and_vsa_together_is_an_error() -> None:
    kw = dict(model_name="m", quant_format="auto", model_type="default", kitchen=True, sage2=False, sage3=False,
              triton=False, flash2=False, pytorch=False, sparse=True, vsa=True, clip1_name="c", clip1_type="auto",
              clip1_device="default", clip2_enabled=False, clip2_name="c", clip2_type="auto", clip2_device="default",
              vae_name="v", audio_vae_enabled=False, audio_vae_name="v")
    with pytest.raises(RefModError, match="sparse and vsa"):
        ul.JWTFUltimateModelLoader().load(**kw)


def test_sparse_attention_degrades_with_a_clear_error_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ul._comfy, "optional_module", lambda name: None)
    with pytest.raises(RefModError, match="nodes_sparse_attention"):
        ul.apply_sparse(object(), vsa=False, model_type="default")


def test_sparse_attention_call_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class Mod:
        @staticmethod
        def apply_block_sparse_attention(model: object, **kwargs: object) -> object:
            seen.update(kwargs)
            return ("patched", )

    monkeypatch.setattr(ul._comfy, "optional_module", lambda name: Mod if name == "comfy_extras.nodes_sparse_attention" else None)
    assert ul.apply_sparse("model", vsa=True, model_type="minimax_h3") == "patched"
    assert seen == {"tau": 1.3, "topk_ratio": 0.0, "vsa": True, "start_percent": 0.2, "end_percent": 1.0,
                    "min_tokens": 12288, "dense_blocks": set(), "sink_conditioning": "exact_kv_and_rows",
                    "extra_tokens": 0, "verbose": False}
    ul.apply_sparse("model", vsa=False, model_type="default")
    assert seen["extra_tokens"] == 256 and seen["vsa"] is False


def test_quant_report_cases() -> None:
    meta = {"layers": {"a": {"format": "float8_e4m3fn"}}}
    known = ["float8_e4m3fn", "nvfp4"]
    r = ul.quant_report("bf16", meta, known)
    assert r.level == "warning" and r.detected == ["float8_e4m3fn"]
    assert ul.quant_report("bf16", None, known).level == "info"
    assert ul.quant_report("nvfp4", None, known).level == "warning"
    r = ul.quant_report("nvfp4", meta, known)
    assert r.level == "warning" and "not found" in r.message and "float8_e4m3fn" in r.message
    r = ul.quant_report("float8_e4m3fn", meta, known)
    assert r.level == "info" and "confirmed" in r.message
    assert ul.quant_report("auto", meta, known).detected == ["float8_e4m3fn"]
    assert ul.quant_report("auto", {}, known).detected == []
    assert ul.quant_report("auto", {"odd": 1}, known).message.startswith("quantised model")


def test_clip_type_list_and_auto_fallbacks() -> None:
    names = ul.clip_type_names()
    assert names[0] == "auto" and len(names) == len(set(names))
    rest = names[1:]
    preferred = [n for n in ul.PREFERRED_CLIP_TYPES if n in rest]
    assert rest[: len(preferred)] == preferred
    assert rest[len(preferred):] == sorted(rest[len(preferred):])
    assert all(n == n.lower() for n in names)
    assert ul.auto_clip_type("default") == "stable_diffusion"
    assert ul.auto_clip_type("flux3") in ("flux3", "flux2", "flux")
    assert ul.auto_clip_type("minimax_h3") in ("minimax", "minimax_h3", "hunyuan_video")
    assert ul.auto_clip_type("moss") in ("moss_image", "stable_diffusion")
    assert ul.auto_clip_type("unheard_of") == "stable_diffusion"
    with pytest.raises(RefModError, match="unknown CLIP type"):
        ul.clip_type_value("not_a_type", "default")


def test_section_order_normalisation() -> None:
    assert ul.normalise_section_order("model,engine,clips,vaes") == ["model", "engine", "clips", "vaes"]
    assert ul.normalise_section_order("vaes, junk, model, vaes") == ["vaes", "model", "engine", "clips"]
    assert ul.normalise_section_order("") == ["model", "engine", "clips", "vaes"]


def test_set_attention_clones_and_prefers_the_native_setter() -> None:
    class Patcher:
        def __init__(self) -> None:
            self.model_options: dict[str, object] = {}
            self.attn: object = None

        def clone(self) -> "Patcher":
            c = Patcher()
            c.model_options = {k: v for k, v in self.model_options.items()}
            return c

    base = Patcher()
    fn = lambda *a, **k: "attn"  # noqa: E731
    clone = ul.set_attention(base, fn)
    override = clone.model_options["transformer_options"]["optimized_attention_override"]  # type: ignore[index]
    assert clone is not base and "transformer_options" not in base.model_options
    assert override(lambda *a, **k: "orig", 1, _inside_attn_wrapper=True) == "attn"

    class WithSetter(Patcher):
        def clone(self) -> "WithSetter":
            return WithSetter()

        def set_model_optimized_attention(self, f: object) -> None:
            self.attn = f

    assert ul.set_attention(WithSetter(), fn).attn is fn  # type: ignore[attr-defined]
    plain = object()
    assert ul.set_attention(plain, fn) is plain


# --------------------------------------------------------------------------- review regressions

def test_attention_override_fallback_runs_real_comfy_attention_without_recursing() -> None:
    import torch

    attn = pytest.importorskip("comfy.ldm.modules.attention")

    class Patcher:
        def __init__(self) -> None:
            self.model_options: dict[str, object] = {}

        def clone(self) -> "Patcher":
            return Patcher()

    for name in ("attention_basic", "attention_pytorch"):
        fn = getattr(attn, name)
        clone = ul.set_attention(Patcher(), fn)
        topts = clone.model_options["transformer_options"]  # type: ignore[attr-defined]
        q = torch.randn(1, 4, 8)
        out = fn(q, q, q, 2, transformer_options=topts)  # RecursionError before the fix
        assert out.shape == (1, 4, 8)
        assert torch.allclose(out, fn(q, q, q, 2), atol=1e-5)


def test_load_vae_mirrors_core_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class Utils:
        @staticmethod
        def load_torch_file(path: str, return_metadata: bool = False) -> object:
            seen["return_metadata"] = return_metadata
            return ({"w": 1}, {"meta": "x"}) if return_metadata else {"w": 1}

    class Vae:
        def __init__(self, sd: object = None, metadata: object = None) -> None:
            seen["metadata"] = metadata
            self.checked = False

        def throw_exception_if_invalid(self) -> None:
            seen["checked"] = True

    class Sd:
        VAE = Vae

    mods = {"comfy.sd": Sd, "comfy.utils": Utils}
    monkeypatch.setattr(ul._comfy, "optional_module", lambda name: mods.get(name))
    monkeypatch.setattr(ul, "_model_path", lambda *a: "p")
    ul.load_vae("v")
    assert seen == {"return_metadata": True, "metadata": {"meta": "x"}, "checked": True}


def test_quant_config_comes_from_the_model_config() -> None:
    class Cfg:
        quant_config = {"mixed_ops": True}

    class Inner:
        model_config = Cfg()

    class Patcher:
        model = Inner()
        model_options: dict[str, object] = {}

    cfg = ul.model_quant_config(Patcher())
    assert cfg == {"mixed_ops": True}
    assert ul.model_quant_config(object()) is None
    r = ul.quant_report("nvfp4", cfg, ["nvfp4"])
    assert r.level == "info" and "no quantisation metadata" not in r.message
    assert ul.quant_report("auto", cfg).message.startswith("quantised model")


def test_triton_flag_warns_when_it_cannot_take_effect(monkeypatch: pytest.MonkeyPatch,
                                                      caplog: pytest.LogCaptureFixture) -> None:
    import types

    cli = types.SimpleNamespace(args=types.SimpleNamespace(enable_triton_backend=False))
    mods = {"comfy.cli_args": cli, "comfy.quant_ops": types.SimpleNamespace()}
    monkeypatch.setattr(ul._comfy, "optional_module", lambda name: mods.get(name))
    with caplog.at_level("WARNING", logger="jezzwtf.refmod_h3"):
        assert ul.apply_triton_flag() is False
    assert "triton has no effect" in caplog.text
    caplog.clear()
    cli.args.enable_triton_backend = True
    with caplog.at_level("WARNING", logger="jezzwtf.refmod_h3"):
        assert ul.apply_triton_flag() is True
    assert caplog.text == ""
