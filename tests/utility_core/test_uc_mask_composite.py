from __future__ import annotations

import pytest
import torch
from utility_core.mask_composite import JWTFMaskComposite, OPERATIONS, composite, soften
from v3_helpers import legacy


def mask(value: float, h: int = 4, w: int = 4, b: int = 1) -> torch.Tensor:
    return torch.full((b, h, w), value)


def test_operations_on_overlapping_values() -> None:
    dst, src = mask(0.6), mask(0.3)
    expected = {"replace": 0.3, "add": 0.9, "subtract": 0.3, "multiply": 0.18, "min": 0.3, "max": 0.6, "difference": 0.3,
                "xor": 0.6 * 0.7 + 0.3 * 0.4}
    assert set(expected) == set(OPERATIONS)
    for op, value in expected.items():
        assert composite(dst, src, 0, 0, op).mean().item() == pytest.approx(value, abs=1e-6), op


def test_results_stay_inside_zero_and_one() -> None:
    assert composite(mask(0.8), mask(0.8), 0, 0, "add").max().item() == 1.0
    assert composite(mask(0.2), mask(0.8), 0, 0, "subtract").min().item() == 0.0


def test_source_is_placed_at_the_offset_and_cut_off_at_the_edges() -> None:
    out = composite(mask(0.0, 6, 6), mask(1.0, 3, 3), 4, 4, "replace")
    assert out[0, 4:, 4:].min().item() == 1.0 and out.sum().item() == 4.0  # only a 2x2 corner fits
    out = composite(mask(0.0, 6, 6), mask(1.0, 3, 3), -2, -2, "replace")
    assert out[0, 0, 0].item() == 1.0 and out.sum().item() == 1.0
    untouched = composite(mask(0.5, 4, 4), mask(1.0, 2, 2), 10, 10, "replace")
    assert torch.equal(untouched, mask(0.5, 4, 4))


def test_opacity_blends_between_the_destination_and_the_result() -> None:
    assert composite(mask(0.0), mask(1.0), 0, 0, "replace", opacity=0.25).mean().item() == pytest.approx(0.25)
    assert composite(mask(0.4), mask(1.0), 0, 0, "replace", opacity=0.0).mean().item() == pytest.approx(0.4)
    assert composite(mask(0.4), mask(1.0), 0, 0, "replace", opacity=7).mean().item() == pytest.approx(1.0)


def test_invert_source() -> None:
    assert composite(mask(0.0), mask(0.25), 0, 0, "replace", invert_source=True).mean().item() == pytest.approx(0.75)


def test_batches_repeat_the_shorter_side_and_inputs_are_not_modified() -> None:
    dst = torch.stack([mask(0.0)[0], mask(0.5)[0]])
    src = mask(0.5)
    before = dst.clone()
    out = composite(dst, src, 0, 0, "add")
    assert out.shape[0] == 2 and out[0].mean().item() == pytest.approx(0.5) and out[1].mean().item() == pytest.approx(1.0)
    assert torch.equal(dst, before)
    wide = composite(mask(0.0), torch.stack([mask(0.2)[0], mask(0.4)[0], mask(0.6)[0]]), 0, 0, "replace")
    assert wide.shape[0] == 3 and wide[2].mean().item() == pytest.approx(0.6)


def test_two_dimensional_masks_are_accepted() -> None:
    assert composite(torch.zeros(4, 4), torch.ones(2, 2), 0, 0, "replace").shape == (1, 4, 4)


def test_feather_softens_a_hard_edge_without_darkening_the_inside() -> None:
    hard = torch.zeros(1, 9, 9)
    hard[:, 3:6, 3:6] = 1.0
    soft = soften(hard, 2)
    assert soft.shape == hard.shape and 0.0 < soft[0, 3, 2].item() < 1.0 and soft[0, 4, 4].item() < 1.0
    assert soften(hard, 0) is hard
    assert soften(torch.ones(1, 5, 5), 3).min().item() == pytest.approx(1.0)  # uniform stays uniform at the borders


def test_unknown_operation_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown operation"):
        composite(mask(0.1), mask(0.1), 0, 0, "blend")


def test_node_schema_and_execute() -> None:
    schema = JWTFMaskComposite.GET_SCHEMA()
    assert schema.node_id == "JWTFMaskComposite" and schema.category == "JezzWTF/image"
    (out,) = legacy(JWTFMaskComposite.execute(mask(0.0), mask(1.0, 2, 2), "replace", 1, 1, opacity=1.0, invert_source=False, feather=0))
    assert out[0, 1:3, 1:3].min().item() == 1.0 and out.sum().item() == 4.0
