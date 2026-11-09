from __future__ import annotations

import pytest
import torch

from utility_core.match_size import compute_size, match_size, parse_hex_color, resolve_target, round_to


def test_parse_hex_color() -> None:
    assert parse_hex_color("#ffffff") == (1.0, 1.0, 1.0)
    assert parse_hex_color("f00") == (1.0, 0.0, 0.0)
    assert parse_hex_color("#00ff00")[1] == 1.0
    assert parse_hex_color("nope") == (0.0, 0.0, 0.0)
    assert parse_hex_color("#12345") == (0.0, 0.0, 0.0)


def test_round_to() -> None:
    assert round_to(100, 1) == 100
    assert round_to(100, 64) == 128
    assert round_to(10, 64) == 64


@pytest.mark.parametrize("mode, src, target, r, expected", [
    ("scale dimensions", (400, 200), (100, 100), 8, (100, 100, False)),
    ("fill (crop)", (400, 200), (100, 100), 8, (100, 100, True)),
    ("fit width", (400, 200), (100, 0), 1, (100, 50, False)),
    ("fit height", (400, 200), (0, 100), 1, (200, 100, False)),
    ("fit width", (400, 300), (100, 0), 8, (100, 72, False)),  # exact side not rounded
    ("shortest side", (400, 200), (100, 0), 1, (200, 100, False)),
    ("shortest side", (200, 400), (100, 0), 1, (100, 200, False)),
    ("longest side", (400, 200), (100, 0), 1, (100, 50, False)),
    ("longest side", (200, 400), (100, 0), 1, (50, 100, False)),
    ("fit within", (400, 200), (100, 100), 1, (100, 50, False)),
    ("pad to", (200, 400), (100, 100), 1, (50, 100, False)),
    ("fit within", (1000, 10), (100, 100), 8, (96, 8, False)),  # clamped to >= r
])
def test_compute_size(mode: str, src: tuple[int, int], target: tuple[int, int], r: int,
                      expected: tuple[int, int, bool]) -> None:
    assert compute_size(mode, src[0], src[1], target[0], target[1], r) == expected


def test_resolve_target_needs_both_dimensions() -> None:
    assert resolve_target(0, 0, (64, 32)) == (64, 32)
    assert resolve_target(10, 0, (64, 32)) == (10, 32)
    assert resolve_target(10, 20, None) == (10, 20)
    with pytest.raises(ValueError, match="reference"):
        resolve_target(100, 0, None)  # even shortest/longest side need the height to resolve
    with pytest.raises(ValueError):
        resolve_target(0, 100, None)


def test_shortest_side_without_height_raises() -> None:
    with pytest.raises(ValueError):
        match_size(torch.rand(1, 8, 8, 3), "shortest side", "bilinear", width=16)


def test_image_resize_and_mask_is_red_channel() -> None:
    img = torch.rand(2, 40, 80, 3)
    out, mask, w, h = match_size(img, "scale dimensions", "bilinear", width=32, height=16)
    assert out.shape == (2, 16, 32, 3) and mask.shape == (2, 16, 32) and (w, h) == (32, 16)
    assert torch.equal(mask, out[..., 0])


def test_four_channel_input_mask_is_still_channel_zero() -> None:
    img = torch.ones(1, 8, 8, 4)
    img[..., 0] = 0.25
    img[..., 3] = 0.5
    out, mask, _, _ = match_size(img, "scale dimensions", "nearest-exact", width=4, height=4)
    assert out.shape == (1, 4, 4, 4)
    assert torch.allclose(mask, torch.full((1, 4, 4), 0.25))


def test_mask_input_gives_single_channel_image() -> None:
    m = torch.zeros(1, 10, 20)
    m[:, :, 10:] = 1.0
    image, mask, w, h = match_size(m, "fit width", "nearest-exact", width=10, height=1)
    assert image.shape == (1, 5, 10, 1) and mask.shape == (1, 5, 10) and (w, h) == (10, 5)
    assert torch.equal(image[..., 0], mask)


def test_pad_to_fills_with_pad_color_and_centres() -> None:
    img = torch.zeros(1, 10, 20, 3)
    out, mask, w, h = match_size(img, "pad to", "nearest-exact", width=20, height=20, pad_color="#ff0000")
    assert (w, h) == (20, 20)
    assert torch.allclose(out[0, 0, 0], torch.tensor([1.0, 0.0, 0.0]))  # padded row
    assert torch.allclose(out[0, 10, 10], torch.zeros(3))  # content
    assert torch.equal(mask, out[..., 0])


def test_pad_to_mask_uses_red_channel_of_colour() -> None:
    m = torch.zeros(1, 4, 8)
    _, mask, w, h = match_size(m, "pad to", "nearest-exact", width=8, height=8, pad_color="#ff00ff")
    assert (w, h) == (8, 8) and mask[0, 0, 0] == 1.0 and mask[0, 4, 4] == 0.0


def test_pad_larger_target_is_clipped_not_crashing() -> None:
    img = torch.ones(1, 10, 10, 3)
    out, _, w, h = match_size(img, "pad to", "nearest-exact", width=5, height=5)
    assert out.shape == (1, 5, 5, 3) and (w, h) == (5, 5)


def test_reference_image() -> None:
    ref = torch.zeros(1, 30, 50, 3)
    out, _, w, h = match_size(torch.rand(1, 10, 10, 3), "fill (crop)", "bilinear", reference=ref)
    assert (w, h) == (50, 30) and out.shape == (1, 30, 50, 3)


def test_reference_mask_and_round_to() -> None:
    ref = torch.zeros(1, 30, 50)
    out, _, w, h = match_size(torch.rand(1, 40, 40, 3), "fit within", "bilinear", reference=ref, rnd=8)
    assert (w, h) == (32, 32) and out.shape == (1, 32, 32, 3)
