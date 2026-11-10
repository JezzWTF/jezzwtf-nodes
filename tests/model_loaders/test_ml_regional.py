from __future__ import annotations

import torch

from model_loaders.regional_logic import (
    LoraPair,
    Region,
    RegionalSession,
    Target,
    char_masks,
    cond_box_mask,
    extract_lora_pairs,
    latent_grid,
    parse_regions,
    rect_mask,
    resolve_targets,
    sig,
    token_mask,
)


def test_parse_regions() -> None:
    regs, glob = parse_regions('{"regions": [{"char": "B", "x": 0.5, "text": "bob"}, {"char": "zz"}, 3],'
                               ' "global": "two people"}')
    assert glob == "two people"
    assert regs == [Region("b", 0.5, 0.0, 0.5, 1.0, "bob"), Region("a", 0.0, 0.0, 0.5, 1.0, "")]
    assert parse_regions('[{"char": "a"}]')[0] == [Region()]
    assert parse_regions("{bad") == ([], "")


def test_latent_grid_rounds_up_like_flux_padding() -> None:
    assert latent_grid(64, 96) == (32, 48)
    assert latent_grid(65, 1) == (33, 1)
    assert latent_grid(0, 0) == (1, 1)


def test_rect_mask_hard_edges_at_cell_centres() -> None:
    m = rect_mask(2, 4, 0.0, 0.0, 0.5, 1.0, feather=0.0).view(2, 4)
    assert torch.allclose(m, torch.tensor([[1.0, 1, 0, 0], [1, 1, 0, 0]]), atol=1e-4)


def test_rect_mask_feather_is_soft_and_symmetric() -> None:
    m = rect_mask(1, 10, 0.25, 0.0, 0.5, 1.0, feather=0.1)
    assert m.shape == (10,)
    assert 0.0 < float(m[2]) < 1.0
    assert torch.allclose(m, m.flip(0), atol=1e-6)
    assert float(m[4]) > float(m[2]) > float(m[0])


def test_char_masks_take_elementwise_max() -> None:
    regs = [Region("a", 0.0, 0.0, 0.25, 1.0), Region("a", 0.75, 0.0, 0.25, 1.0)]
    m = char_masks(regs, 1, 4, 0.0)
    assert set(m) == {"a"}
    assert torch.allclose(m["a"], torch.tensor([1.0, 0, 0, 1]), atol=1e-4)


def test_token_mask_layouts() -> None:
    g = torch.tensor([0.0, 1.0, 1.0])
    assert torch.equal(token_mask(g, 3), g)  # type: ignore[arg-type]
    assert torch.equal(token_mask(g, 5), torch.tensor([0.0, 0, 0, 1, 1]))  # type: ignore[arg-type]
    assert token_mask(g, 2) is None


def test_sig_normalisation() -> None:
    assert sig("lora_unet_double_blocks_0_img_attn_qkv") == sig("double_blocks.0.img_attn.qkv")
    assert sig("model.diffusion_model.single_blocks.3.linear1") == "singleblocks3linear1"
    assert sig("transformer.blocks.1.ff") == "blocks1ff"


def test_extract_pairs_alpha_and_naming() -> None:
    sd = {
        "lora_unet_x.lora_down.weight": torch.ones(4, 8),
        "lora_unet_x.lora_up.weight": torch.ones(6, 4),
        "lora_unet_x.alpha": torch.tensor(2.0),
        "transformer.y.lora_A.weight": torch.ones(2, 8, dtype=torch.float16),
        "transformer.y.lora_B.weight": torch.ones(6, 2, dtype=torch.float16),
        "orphan.lora_down.weight": torch.ones(2, 8),
        "z.hada_w1_a": torch.ones(2, 2),
    }
    pairs = extract_lora_pairs(sd)
    assert set(pairs) == {"lora_unet_x", "transformer.y"}
    assert pairs["lora_unet_x"].scale == 0.5
    assert pairs["transformer.y"].scale == 1.0 and pairs["transformer.y"].down.dtype == torch.float32


def test_resolve_targets_key_map_slice_and_fallback() -> None:
    modules = ["double_blocks.0.img_attn.qkv", "single_blocks.0.linear1", "final"]
    key_map = {
        "transformer.transformer_blocks.0.attn.to_k": ("diffusion_model.double_blocks.0.img_attn.qkv.weight", (0, 8, 8)),
        "diffusion_model.final": "diffusion_model.final.weight",
    }
    out = resolve_targets({"a": ["transformer.transformer_blocks.0.attn.to_k", "lora_unet_single_blocks_0_linear1"],
                           "b": ["diffusion_model.final", "unmatched"]}, modules, key_map)
    assert out["double_blocks.0.img_attn.qkv"] == [Target("a", "transformer.transformer_blocks.0.attn.to_k", 8, 8)]
    assert out["single_blocks.0.linear1"] == [Target("a", "lora_unet_single_blocks_0_linear1")]
    assert out["final"] == [Target("b", "diffusion_model.final")]
    assert len(out) == 3


def _session(rows: int, cols: int) -> tuple[RegionalSession, LoraPair, LoraPair]:
    torch.manual_seed(0)
    pa = LoraPair(down=torch.randn(2, 8), up=torch.randn(6, 2), scale=0.5)
    pb = LoraPair(down=torch.randn(2, 8), up=torch.randn(3, 2), scale=1.0)
    s = RegionalSession(regions=[Region("a", 0, 0, 0.5, 1), Region("b", 0.5, 0, 0.5, 1)], feather=0.0,
                        pairs={"a": {"la": pa}, "b": {"lb": pb}})
    s.set_grid((rows, cols))
    return s, pa, pb


def test_session_apply_matches_manual_delta_with_text_prefix() -> None:
    s, pa, _ = _session(1, 4)
    x = torch.randn(2, 6, 8)  # 2 text tokens + 4 image tokens
    out = torch.randn(2, 6, 6)
    res = s.apply([Target("a", "la")], x, out)
    mask = torch.tensor([0.0, 0, 1, 1, 0, 0]).view(1, 6, 1)
    expect = out + ((x @ pa.down.T) @ (pa.up * pa.scale).T) * mask
    assert torch.allclose(res, expect, atol=1e-4)
    assert torch.equal(s.apply([Target("a", "la")], x[:, :3], out[:, :3]), out[:, :3])  # seq < n_img → untouched


def test_session_apply_slice_into_fused_layer_and_shape_guard() -> None:
    s, _, pb = _session(1, 4)
    x = torch.randn(1, 4, 8)
    out = torch.zeros(1, 4, 9)
    res = s.apply([Target("b", "lb", offset=3, size=3)], x, out)
    delta = ((x @ pb.down.T) @ pb.up.T) * torch.tensor([0.0, 0, 1, 1]).view(1, 4, 1)
    assert torch.allclose(res[..., 3:6], delta, atol=1e-4)
    assert torch.count_nonzero(res[..., :3]) == 0 and torch.count_nonzero(res[..., 6:]) == 0
    # wrong width → skipped, not crashed
    assert torch.equal(s.apply([Target("b", "lb")], x, out), out)


def test_session_reprepares_per_dtype() -> None:
    s, _, _ = _session(1, 4)
    x = torch.randn(1, 4, 8)
    s.apply([Target("a", "la")], x.half(), torch.zeros(1, 4, 6, dtype=torch.float16))
    s.apply([Target("a", "la")], x, torch.zeros(1, 4, 6))
    assert {k[1] for k in s._prepared} == {torch.float16, torch.float32}


def test_cond_box_mask() -> None:
    m = cond_box_mask(0.5, 0.0, 0.5, 1.0, size=8)
    assert m.shape == (1, 8, 8)
    assert m[0, :, 4:].min() == 1 and m[0, :, :4].max() == 0
    tiny = cond_box_mask(0.999, 0.999, 0.0, 0.0, size=8)
    assert tiny.sum() == 1


def test_rect_mask_has_no_ramp_on_image_borders() -> None:
    assert torch.equal(rect_mask(4, 4, 0.0, 0.0, 1.0, 1.0, feather=0.2), torch.ones(16))
    left = rect_mask(1, 10, 0.0, 0.0, 0.5, 1.0, feather=0.1)
    assert float(left[0]) > 0.98 and float(left[3]) > float(left[4]) > float(left[5])  # soft only at the inner edge
    top = rect_mask(10, 1, 0.0, 0.0, 1.0, 0.5, feather=0.1)
    assert float(top[0]) > 0.98 and float(top[9]) < 0.02


def test_session_reports_idle_once_and_release_frees_matrices() -> None:
    s, _, _ = _session(2, 4)  # 8 image tokens
    s.apply([Target("a", "la")], torch.randn(1, 4, 8), torch.zeros(1, 4, 6))  # 4 tokens: not a patch-2 model
    reason = s.idle_reason()
    assert reason is not None and "2x4" in reason and "[4]" in reason
    assert s.idle_reason() is None
    s.apply([Target("a", "la")], torch.randn(1, 8, 8), torch.zeros(1, 8, 6))
    assert s.applied and s._prepared
    s.release()
    assert not s._prepared and not s._mask_cache
    assert "5-D" in str(RegionalSession(regions=[], feather=0.0, pairs={}).idle_reason())
