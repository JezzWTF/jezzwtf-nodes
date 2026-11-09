"""Apply math: easings, direction curves, weakening, scramble determinism, budget, injection."""
from __future__ import annotations

import dataclasses
import math

import pytest
import torch

from refmod_h3 import curves
from refmod_h3._types import RefModError
from refmod_h3.bundle import RefMod


def mod(kind: str = "video", t: int = 5, h: int = 16, w: int = 16, name: str = "m", seed: int = 0) -> RefMod:
    g = torch.Generator().manual_seed(seed)
    if kind == "audio":
        lat = torch.randn(1, 32, 2, t, generator=g)
    else:
        lat = torch.randn(1, 24, t, h, w, generator=g)
    return RefMod(name=name, kind=kind, latent=lat)


# --------------------------------------------------------------------------- easings

def test_easing_table_matches_spec() -> None:
    e = curves.EASINGS
    assert set(e) == {"linear", "ease", "sigmoid", "tanh", "quadratic", "cubic", "exponential", "stair",
                      "elastic", "bump", "dip"}
    assert e["ease"](0.5) == pytest.approx(0.5)
    assert e["sigmoid"](0.5) == pytest.approx(0.5)
    assert e["sigmoid"](1.0) == pytest.approx(1 / (1 + math.exp(-6)))
    assert e["tanh"](0.5) == pytest.approx(0.5)
    assert e["quadratic"](0.5) == 0.25 and e["cubic"](0.5) == 0.125
    assert e["exponential"](1.0) == pytest.approx(1.0) and e["exponential"](0.0) == pytest.approx(0.0)
    assert [e["stair"](x) for x in (0.0, 0.24, 0.25, 0.5, 0.75, 1.0)] == pytest.approx([0, 0, 1 / 3, 2 / 3, 1, 1])
    assert e["elastic"](0.0) == 0.0 and e["elastic"](1.0) == 1.0
    x = 0.3
    assert e["elastic"](x) == pytest.approx(2 ** (-10 * x) * math.sin((10 * x - 0.75) * 2 * math.pi / 3) + 1)
    assert e["bump"](0.0) == 0 and e["bump"](0.5) == 1 and e["bump"](1.0) == 0
    assert e["dip"](0.0) == 1 and e["dip"](0.5) == 0 and e["dip"](1.0) == 1


# --------------------------------------------------------------------------- direction curves

def test_constant_linear_is_flat_or_value() -> None:
    assert curves.direction_curve("constant", "linear", 1.0, 5) is None
    assert curves.direction_curve("constant", "linear", 0.4, 5) == [0.4] * 5
    assert curves.direction_curve("constant", "cubic", 1.0, 3) == pytest.approx([0.0, 0.125, 1.0])


def test_direction_curves_and_aliases() -> None:
    end = curves.direction_curve("concept_at_end", "linear", 1.0, 5)
    start = curves.direction_curve("concept_at_start", "linear", 1.0, 5)
    mid = curves.direction_curve("concept_at_middle", "linear", 1.0, 5)
    ends = curves.direction_curve("concept_at_ends", "linear", 1.0, 5)
    assert end == pytest.approx([0, 0.25, 0.5, 0.75, 1])
    assert start == pytest.approx([1, 0.75, 0.5, 0.25, 0])
    assert mid == pytest.approx([0, 0.5, 1, 0.5, 0])
    assert ends == pytest.approx([1, 0.5, 0, 0.5, 1])
    assert curves.direction_curve("increase", "linear", 1.0, 5) == end
    assert curves.direction_curve("decrease", "linear", 1.0, 5) == start
    assert curves.direction_curve("concept_at_end", "linear", 0.5, 3) == pytest.approx([0, 0.25, 0.5])
    assert curves.direction_curve("bogus", "linear", 1.0, 5) is None
    assert curves.direction_curve("concept_at_end", "linear", 1.0, 1) is None


def test_unknown_shape_is_an_error() -> None:
    with pytest.raises(RefModError, match="unknown curve shape"):
        curves.direction_curve("constant", "wobble", 1.0, 4)


def test_frame_curve_accepts_every_documented_spec() -> None:
    assert curves.frame_curve("fade_in", 3) == pytest.approx([0, 0.5, 1])
    assert curves.frame_curve("fade_out", 3) == pytest.approx([1, 0.5, 0])
    assert curves.frame_curve("flat", 3) is None
    assert curves.frame_curve("bump", 3) == pytest.approx([0, 1, 0])
    assert curves.frame_curve("dip", 3) == pytest.approx([1, 0, 1])
    assert curves.frame_curve([0.1, 0.2, 0.3], 3) == [0.1, 0.2, 0.3]
    assert curves.frame_curve([(0, 0.0), (1, 1.0)], 3) == pytest.approx([0, 0.5, 1])
    assert curves.frame_curve([(0.25, 0.2), (0.75, 0.8)], 5) == pytest.approx([0.2, 0.2, 0.5, 0.8, 0.8])

    class Ramp:
        def interp(self, x: float) -> float:
            return x * 0.5

    assert curves.frame_curve(Ramp(), 3) == pytest.approx([0, 0.25, 0.5])
    assert curves.frame_curve(("constant", "linear", 0.3), 3) == [0.3] * 3
    assert curves.frame_curve(None, 5) is None and curves.frame_curve("fade_in", 1) is None
    with pytest.raises(RefModError, match="exactly 4"):
        curves.frame_curve([0.1, 0.2], 4)
    with pytest.raises(RefModError, match="unknown curve preset"):
        curves.frame_curve("nope", 4)


def test_retention_presets_and_strength() -> None:
    assert curves.resolve_retention("fully_preserved") == 1.0
    assert curves.resolve_retention("partially_preserved") == 0.7
    assert curves.resolve_retention("attribute_transfer") == 0.4
    assert curves.resolve_retention("weak_reference") == 0.15
    assert curves.resolve_retention("0.5") == 0.5
    with pytest.raises(RefModError):
        curves.resolve_retention("mystery")
    assert curves.effective_strength(0.5, 0.85) == pytest.approx(0.425)
    assert curves.effective_strength(2.0, 1.0) == 1.0 and curves.effective_strength(-1.0, 1.0) == 0.0


# --------------------------------------------------------------------------- weakening

def test_blur_shapes_and_audio_edge() -> None:
    v = mod("video", t=3, h=16, w=24)
    assert curves.blur_latent("video", v.latent).shape == v.latent.shape
    a = mod("audio", t=40)
    assert curves.blur_latent("audio", a.latent).shape == a.latent.shape
    one = mod("audio", t=1)
    assert torch.equal(curves.blur_latent("audio", one.latent), one.latent)


def test_weaken_never_scales_toward_zero() -> None:
    m = mod("image", t=1)
    out = curves.weaken(m, 0.5, None)
    blur = curves.blur_latent("image", m.latent)
    assert torch.allclose(out, 0.5 * m.latent + 0.5 * blur, atol=1e-6)
    assert torch.equal(curves.weaken(m, 1.0, None), m.latent)
    near_zero = curves.weaken(m, 0.01, None)
    assert torch.allclose(near_zero, blur, atol=0.05 * float(m.latent.abs().max()))


def test_weaken_with_curve_is_per_frame() -> None:
    m = mod("video", t=3)
    blur = curves.blur_latent("video", m.latent)
    out = curves.weaken(m, 1.0, [1.0, 0.5, 0.0])
    assert torch.equal(out[:, :, 0], m.latent[:, :, 0])
    assert torch.allclose(out[:, :, 1], 0.5 * m.latent[:, :, 1] + 0.5 * blur[:, :, 1], atol=1e-6)
    assert torch.allclose(out[:, :, 2], blur[:, :, 2], atol=1e-6)
    assert curves.weaken(m, 1.0, [1.0, 1.0, 1.0]) is m.latent
    a = mod("audio", t=8)
    assert curves.weaken(a, 1.0, [1.0] * 4 + [0.0] * 4).shape == a.latent.shape


def test_ref_block_values_and_single_frame_cap() -> None:
    assert curves.ref_block(mod("image", t=1), 0.0, None) is None
    img = curves.ref_block(mod("image", t=1), 1.0, ("constant", "linear", 1.0))
    assert img is not None and img["kind"] == "image" and img["refmod"] is True
    assert "latent_t" not in img and img["latent_h"] == 16 and img["latent_w"] == 16
    vid = curves.ref_block(mod("video", t=5), 1.0, None)
    assert vid is not None and vid["latent_t"] == 5 and vid["ref_audio_t"] == 0 and vid["audio_latent"] is None
    aud = curves.ref_block(mod("audio", t=12), 1.0, None)
    assert aud is not None and aud["kind"] == "audio" and aud["ref_audio_t"] == 12
    m = mod("image", t=1)
    capped = curves.ref_block(m, 1.0, ("concept_at_end", "linear", 0.5))
    assert capped is not None
    assert torch.allclose(capped["latent"], 0.5 * m.latent + 0.5 * curves.blur_latent("image", m.latent), atol=1e-6)
    assert curves.ref_block(m, 1.0, ("concept_at_end", "linear", 0.0)) is None


# --------------------------------------------------------------------------- scramble / budget

def rows(n: int = 8) -> list[curves.Row]:
    return [(mod("image", t=1, name=f"m{i}", seed=i), 1.0) for i in range(n)]


def names(rs: list[curves.Row]) -> list[str]:
    return [m.name for m, _ in rs]


def test_scramble_is_deterministic_per_seed() -> None:
    base = rows()
    a = names(curves.scramble_rows(base, 7, "shuffle", 1))
    b = names(curves.scramble_rows(base, 7, "shuffle", 1))
    assert a == b and sorted(a) == sorted(names(base))
    assert a != names(base) or a != names(curves.scramble_rows(base, 8, "shuffle", 1))
    assert names(curves.scramble_rows(base, 7, "subset", 3)) == a[:3]
    legacy = curves.scramble_rows(base, 7, "legacy_subset", 1)
    import random
    rng = random.Random(7)
    shuffled = list(base)
    rng.shuffle(shuffled)
    assert names(legacy) == names(shuffled)[: rng.randint(4, 8)]
    assert len(names(curves.scramble_rows(base, 7, "subset", 0))) == 1


def test_scramble_off_cases_and_bad_mode() -> None:
    base = rows(4)
    assert names(curves.scramble_rows(base, -1, "shuffle", 1)) == names(base)
    assert names(curves.scramble_rows(base[:1], 5, "shuffle", 1)) == names(base[:1])
    with pytest.raises(RefModError, match="unknown scramble mode"):
        curves.scramble_rows(base, 3, "random", 1)


def test_token_budget() -> None:
    rs = [(mod("video", t=5, h=16, w=16), 1.0), (mod("audio", t=10), 1.0), (mod("image", t=1), 0.0)]
    per_video = 5 * 8 * 8
    assert curves.total_tokens(rs) == per_video + 20  # strength-0 rows do not count
    assert curves.check_budget(rs, 0) == per_video + 20
    assert curves.check_budget(rs, per_video + 20) == per_video + 20
    with pytest.raises(RefModError, match="over the budget"):
        curves.check_budget(rs, per_video)
    for bad in (-1, 1.5, float("nan"), float("inf"), True, "10"):
        with pytest.raises(RefModError, match="budget"):
            curves.check_budget(rs, bad)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- injection

def test_inject_into_conditioning_list_keeps_existing_refs() -> None:
    old = {"kind": "image"}
    cond = [[torch.zeros(1, 2), {"minimax_refs": [old], "x": 1}], [torch.zeros(1, 2), {"x": 2}]]
    block = curves.make_block(mod("image", t=1), mod("image", t=1).latent)
    out = curves.inject_blocks(cond, [block])
    assert isinstance(out, list) and len(out) == 2
    assert out[0][1]["minimax_refs"] == [old, block] and out[1][1]["minimax_refs"] == [block]
    assert "minimax_refs" in cond[0][1] and cond[0][1]["minimax_refs"] == [old]  # input untouched
    assert out[0][1]["x"] == 1 and out[1][1]["x"] == 2


def test_inject_into_dataclass_and_unsupported() -> None:
    @dataclasses.dataclass
    class FakeCond:
        text: str
        refs: list[object]

    c = FakeCond("hi", [1])
    out = curves.inject_blocks(c, [{"kind": "audio"}])
    assert isinstance(out, FakeCond) and out.refs == [1, {"kind": "audio"}] and c.refs == [1]
    with pytest.raises(RefModError, match="unsupported conditioning"):
        curves.inject_blocks(42, [])
    with pytest.raises(RefModError, match="not \\[tensor, dict\\]"):
        curves.inject_blocks([["x"]], [])


def test_apply_rows_end_to_end() -> None:
    cond = [[torch.zeros(1, 2), {}]]
    out, n = curves.apply_rows(cond, [(mod("video", t=5), 1.0), (mod("audio", t=10), 0.0)], retention=0.85,
                               curve=("concept_at_end", "linear", 1.0))
    assert n == 1 and out[0][1]["minimax_refs"][0]["kind"] == "video"
    same, zero = curves.apply_rows(cond, [(mod("video", t=5), 0.0)], retention=1.0)
    assert zero == 0 and same is cond
    with pytest.raises(RefModError, match="over the budget"):
        curves.apply_rows(cond, [(mod("video", t=5), 1.0)], budget=10)
