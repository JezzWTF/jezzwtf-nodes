from __future__ import annotations

import math

import pytest
import torch

from model_loaders.relay_logic import (
    DEFAULT_SIGMA,
    MAX_COST,
    RelayMask,
    RelayOptions,
    Segment,
    attention_mask_arg,
    install_text_scope_hooks,
    parse_timeline,
    text_attention_scope,
    build_segments,
    combine_mask,
    distribute_lengths,
    install_override,
    make_backend_override,
    make_relay_override,
    parse_lengths,
    parse_prompts,
    penalty_bias,
    pixel_to_latent_lengths,
    sigma_from_eps,
    token_ranges,
)

EOS = 1


def word_ids(text: str) -> list[int]:
    return [10 + len(w) for w in text.split()] + [EOS]


def test_sigma() -> None:
    assert sigma_from_eps(1e-3) == pytest.approx(1 / math.log(1000))
    assert sigma_from_eps(0.0) == DEFAULT_SIGMA
    assert sigma_from_eps(1.0) == DEFAULT_SIGMA


def test_parse_prompts_and_lengths() -> None:
    assert parse_prompts(" a | |b c|  ") == ["a", "b c"]
    assert parse_lengths("") is None
    assert parse_lengths("64, 65") == [64, 65]
    with pytest.raises(ValueError):
        parse_lengths("1, x")


def test_pixel_to_latent_snaps_to_full_coverage() -> None:
    assert pixel_to_latent_lengths([64, 65], latent_frames=17, stride=8) == [8, 9]
    assert sum(pixel_to_latent_lengths([40, 40, 49], 17, 8)) == 17


def test_pixel_to_latent_partial_and_minimum_one() -> None:
    assert pixel_to_latent_lengths([16, 16], latent_frames=20, stride=8) == [2, 2]
    assert pixel_to_latent_lengths([8, 0], latent_frames=10, stride=8) == [1, 1]
    assert pixel_to_latent_lengths([0, 0], 10, 8) == [1, 1]
    assert pixel_to_latent_lengths([100, 1, 1], 10, 8) == [8, 1, 1]


def test_distribute_lengths() -> None:
    assert distribute_lengths(None, 3, 10) == [4, 4, 2]
    warns: list[str] = []
    assert distribute_lengths([6, 6, 3], 3, 10, warns.append) == [6, 4, 0]
    assert len(warns) == 1
    with pytest.raises(ValueError):
        distribute_lengths([1, 2], 3, 10)


def test_token_ranges_incremental() -> None:
    ranges, full = token_ranges(word_ids, "a b", ["cc dd", "eee"], eos_adj=1, max_len=100)
    # "a b" → 2 content tokens; "a b cc dd" → 4; "a b cc dd eee" → 5
    assert ranges == [(2, 4), (4, 5)]
    assert full == "a b cc dd eee"


def test_token_ranges_empty_local_raises() -> None:
    with pytest.raises(ValueError):
        token_ranges(lambda s: [1, 2], "x", ["y"], eos_adj=0, max_len=10)


def test_token_ranges_overflow_truncates() -> None:
    warns: list[str] = []
    ranges, full = token_ranges(word_ids, "g", ["a b", "c d", "e f"], eos_adj=1, max_len=4,
                                decode=lambda ids: f"decoded{len(ids)}", warn=warns.append)
    assert ranges == [(1, 3), (3, 4)]
    assert full == "decoded4" and warns


def test_build_segments_metadata() -> None:
    opts = RelayOptions(video_window_scale=2.0, audio_epsilon=0.1, audio_window_scale=0.5, audio_strength=3.0,
                        per_segment_epsilon=[0.5])
    warns: list[str] = []
    segs = build_segments([(1, 3), (3, 5), (5, 6)], [10, 0, 4], eps=1e-3, options=opts, warn=warns.append)
    assert len(segs) == 2 and len(warns) == 1
    s0, s1 = segs
    assert torch.equal(s0.token_idx, torch.tensor([1, 2]))
    assert s0.midpoint == 4.5 and s0.window == 6.0 and s0.window_audio == 1.5
    assert s0.sigma == pytest.approx(sigma_from_eps(0.5))  # per-segment override
    assert s0.sigma_audio == pytest.approx(sigma_from_eps(0.1)) and s0.strength_audio == 3.0
    assert s1.midpoint == 10 + 1.5 and s1.window == 0.0  # cursor not advanced by the skipped segment
    assert s1.sigma == pytest.approx(sigma_from_eps(1e-3))


def test_options_validation_and_get() -> None:
    o = RelayOptions(unknown=5)
    assert o.get("video_strength") == 1.0 and o.get("nope", 7) == 7
    with pytest.raises(ValueError):
        RelayOptions(video_strength=11)
    with pytest.raises(ValueError):
        RelayOptions(audio_epsilon=1.0)


def _seg(start: int, end: int, mid: float, window: float = 0.0, strength: float = 1.0) -> Segment:
    sigma = sigma_from_eps(1e-3)
    return Segment(torch.arange(start, end), mid, window, sigma, strength, window, sigma, strength)


def test_penalty_formula_video_mode() -> None:
    seg = _seg(1, 3, mid=1.5)
    bias = penalty_bias([seg], lq=8, lk=5, latent_frames=4, video_tpf=2, video_mode=True)
    frames = torch.tensor([0, 0, 1, 1, 2, 2, 3, 3], dtype=torch.float32)
    expect = torch.clamp((frames - 1.5).abs() ** 2 / (2 * seg.sigma ** 2), max=MAX_COST)
    assert torch.allclose(-bias[:, 1], expect) and torch.allclose(-bias[:, 2], expect)
    assert torch.count_nonzero(bias[:, [0, 3, 4]]) == 0  # global / padding tokens untouched


def test_penalty_window_and_overwrite_and_scaled_mode() -> None:
    a = _seg(0, 2, mid=1.0, window=1.0)
    b = _seg(1, 3, mid=5.0, strength=2.0)  # overlaps token 1: overwritten, not summed
    bias = penalty_bias([a, b], lq=6, lk=4, latent_frames=6, video_tpf=1, video_mode=True)
    assert torch.count_nonzero(bias[:3, 0]) == 0  # |f-1| ≤ window
    fr = torch.arange(6, dtype=torch.float32)
    assert torch.allclose(-bias[:, 1], torch.clamp(2 * (fr - 5).abs() ** 2 / (2 * b.sigma ** 2), max=MAX_COST))
    scaled = penalty_bias([a], lq=3, lk=4, latent_frames=6, video_tpf=1, video_mode=False)
    f = torch.tensor([0.0, 2.0, 4.0])
    exp = torch.clamp(torch.relu((f - 1).abs() - 1) ** 2 / (2 * a.sigma_audio ** 2), max=MAX_COST)
    assert torch.allclose(-scaled[:, 0], exp)


def test_relay_mask_gating_and_cache() -> None:
    m = RelayMask([_seg(1, 3, 1.5)], latent_frames=4, fallback_tpf=2)
    assert m(8, 8, torch.float32, "cpu", {}) is None  # self-attention
    assert m(8, 5, torch.float32, "cpu", {"cond_or_uncond": [1]}) is None  # uncond only
    assert m(8, 2, torch.float32, "cpu", {}) is None  # too few keys
    assert m(3, 8, torch.float32, "cpu", {}) is None  # keys are the video tokens (cross-modal)
    b1 = m(8, 5, torch.float32, "cpu", {"cond_or_uncond": [0, 1]})
    assert b1 is not None and b1 is m(8, 5, torch.float32, "cpu", {})
    gs = m(12, 5, torch.float32, "cpu", {"grid_sizes": (4, 1, 3)})  # tpf from grid_sizes → video mode
    assert gs is not None and torch.equal(gs[0], gs[2]) and not torch.equal(gs[0], gs[3])
    assert RelayMask([], 4, 2)(8, 5, torch.float32, "cpu", {}) is None


def test_combine_mask_shapes() -> None:
    bias = torch.full((3, 4), -1.0)
    assert combine_mask(None, bias).shape == (1, 1, 3, 4)
    pad = torch.zeros(2, 1, 1, 4)
    pad[1, ..., 3] = -100
    c = combine_mask(pad, bias)
    assert c.shape == (2, 1, 3, 4) and c[1, 0, 0, 3] == -101
    boolean = torch.tensor([[True, True, True, False]])
    cb = combine_mask(boolean, bias)
    assert cb.shape == (1, 1, 3, 4) and cb[0, 0, 0, 3] < -1e30


def test_relay_override_injects_bias_positionally_and_by_kw() -> None:
    seen: list[torch.Tensor | None] = []

    def attn(q: torch.Tensor, k: torch.Tensor, v: torch.Tensor, heads: int, mask: torch.Tensor | None = None,
             **kw: object) -> torch.Tensor:
        seen.append(mask)
        return q

    bias = torch.full((5, 3), -2.0)
    ov = make_relay_override(lambda lq, lk, dt, dev, to: bias if (lq, lk) == (5, 3) else None, None)
    q, k = torch.zeros(1, 5, 8), torch.zeros(1, 3, 8)
    ov(attn, q, k, k, 2, transformer_options={})
    ov(attn, q, k, k, 2, torch.zeros(1, 1, 1, 3), transformer_options={})
    ov(attn, q.view(1, 2, 5, 4), k.view(1, 2, 3, 4), k, 2, skip_reshape=True)
    ov(attn, q, q, q, 2)  # self-attention: untouched
    assert all(s is not None and s.shape[-2:] == (5, 3) for s in seen[:3])
    assert seen[3] is None


def test_override_chain_order_independent() -> None:
    calls: list[str] = []

    def default(*a: object, **kw: object) -> torch.Tensor:
        calls.append("default")
        return torch.zeros(1)

    def backend(*a: object, **kw: object) -> torch.Tensor:
        calls.append(f"backend mask={kw.get('mask') is not None}")
        return torch.zeros(1)

    bias = torch.zeros(2, 3)
    opts: dict[str, object] = {"transformer_options": {"other": 1}}
    install_override(opts, lambda prev: make_relay_override(lambda *a: bias, prev))
    install_override(opts, lambda prev: make_backend_override(backend, prev))
    topts = opts["transformer_options"]
    assert isinstance(topts, dict) and topts["other"] == 1
    topts["optimized_attention_override"](default, torch.zeros(1, 2, 4), torch.zeros(1, 3, 4), None, 1)
    opts2: dict[str, object] = {}
    install_override(opts2, lambda prev: make_backend_override(backend, prev))
    install_override(opts2, lambda prev: make_relay_override(lambda *a: bias, prev))
    t2 = opts2["transformer_options"]
    assert isinstance(t2, dict)
    t2["optimized_attention_override"](default, torch.zeros(1, 2, 4), torch.zeros(1, 3, 4), None, 1)
    assert calls == ["backend mask=True", "backend mask=True"]


class _FakePatcher:
    def __init__(self, model: torch.nn.Module) -> None:
        self.model = model
        self.patches: dict[str, object] = {}

    def get_model_object(self, name: str) -> object:
        if name in self.patches:
            return self.patches[name]
        obj: object = self.model
        for part in name.removeprefix("diffusion_model.").split("."):
            obj = getattr(obj, part)
        return obj

    def add_object_patch(self, name: str, obj: object) -> None:
        self.patches[name] = obj


class _Blk(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.attn2 = torch.nn.Identity()
        self.audio_attn2 = torch.nn.Identity()
        self.audio_to_video_attn = torch.nn.Identity()


def test_av_cross_attention_is_never_biased_when_hooked() -> None:
    # text keys 0..5; audio keys happen to number 6 as well (> max_token), the shape guards alone would pass
    m = RelayMask([_seg(1, 3, 1.5)], latent_frames=4, fallback_tpf=2, text_only=True)
    assert m(8, 6, torch.float32, "cpu", {}) is None  # a2v: video queries, audio keys, outside any text scope
    with text_attention_scope("video"):
        assert m(8, 6, torch.float32, "cpu", {}) is not None
    with text_attention_scope("audio"):
        b = m(5, 6, torch.float32, "cpu", {})
        assert b is not None and b.shape == (5, 6)
    assert m(8, 6, torch.float32, "cpu", {}) is None  # scope restored


def test_install_text_scope_hooks_wraps_only_text_attention() -> None:
    from model_loaders.relay_logic import current_text_scope

    seen: list[str | None] = []

    class Rec(torch.nn.Module):
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            seen.append(current_text_scope())
            return x

    blk = _Blk()
    blk.attn2, blk.audio_attn2, blk.audio_to_video_attn = Rec(), Rec(), Rec()
    root = torch.nn.Module()
    root.add_module("blocks", torch.nn.ModuleList([blk]))
    patcher = _FakePatcher(root)
    assert install_text_scope_hooks(patcher, root) == 2
    assert set(patcher.patches) == {"diffusion_model.blocks.0.attn2.forward",
                                    "diffusion_model.blocks.0.audio_attn2.forward"}
    x = torch.zeros(1)
    patcher.patches["diffusion_model.blocks.0.attn2.forward"](x)  # type: ignore[operator]
    patcher.patches["diffusion_model.blocks.0.audio_attn2.forward"](x)  # type: ignore[operator]
    blk.audio_to_video_attn(x)
    assert seen == ["video", "audio", None]


def test_guide_tokens_use_video_mode_and_clamp_frames() -> None:
    tpf, frames = 2, 4
    m = RelayMask([_seg(1, 3, 1.5)], latent_frames=frames, fallback_tpf=tpf)
    lq = frames * tpf + 2 * tpf  # two guide frames appended
    b = m(lq, 5, torch.float32, "cpu", {})
    assert b is not None
    assert torch.equal(b, penalty_bias([_seg(1, 3, 1.5)], lq, 5, frames, tpf, True))
    assert torch.equal(b[lq - 1], b[frames * tpf - 1])  # guide tokens map to the last real frame
    audio = m(frames * tpf + 1, 5, torch.float32, "cpu", {})  # not a multiple of tpf: audio mode
    assert audio is not None and audio.shape == (frames * tpf + 1, 5)


def test_parse_timeline() -> None:
    raw = '{"segments": [{"prompt": " a | b ", "length": 60.4}, {"prompt": "c", "length": 0}]}'
    assert parse_timeline(raw) == (["a b", "c"], [60, 1])
    assert parse_timeline("") is None and parse_timeline("{bad") is None and parse_timeline('{"segments": []}') is None
    with pytest.raises(ValueError, match=r"segment\(s\) 2"):
        parse_timeline('{"segments": [{"prompt": "a", "length": 5}, {"prompt": " | ", "length": 5}]}')


def test_backend_override_bypasses_flash_for_masked_calls() -> None:
    calls: list[str] = []
    warned: list[int] = []

    def flash(*a: object, **kw: object) -> torch.Tensor:
        calls.append("flash")
        return torch.zeros(1)

    def default(*a: object, **kw: object) -> torch.Tensor:
        calls.append("default")
        return torch.zeros(1)

    ov = make_backend_override(flash, None, supports_mask=False, on_masked=lambda: warned.append(1))
    q = torch.zeros(1, 2, 4)
    ov(default, q, q, q, 1)
    ov(default, q, q, q, 1, torch.zeros(1, 1, 2, 2))
    ov(default, q, q, q, 1, mask=torch.zeros(1, 1, 2, 2))
    assert calls == ["flash", "default", "default"] and len(warned) == 2  # the caller de-duplicates the warning
    assert attention_mask_arg((q, q, q, 1), {}) is None


def test_backend_override_with_relay_chain_bypasses_flash_on_relay_mask() -> None:
    calls: list[str] = []

    def flash(*a: object, **kw: object) -> torch.Tensor:
        calls.append("flash")
        return torch.zeros(1)

    def default(*a: object, **kw: object) -> torch.Tensor:
        calls.append("default")
        return torch.zeros(1)

    opts: dict[str, object] = {}
    install_override(opts, lambda prev: make_relay_override(lambda *a: torch.zeros(2, 3), prev))
    install_override(opts, lambda prev: make_backend_override(flash, prev, supports_mask=False))
    t = opts["transformer_options"]
    assert isinstance(t, dict)
    t["optimized_attention_override"](default, torch.zeros(1, 2, 4), torch.zeros(1, 3, 4), None, 1)
    assert calls == ["default"]
