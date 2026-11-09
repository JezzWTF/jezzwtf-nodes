"""libx264 (yuv420p) cannot encode an odd width or height, so IMAGE inputs are padded to even sizes."""
from __future__ import annotations

import pytest
import torch

from video_compare import even_dimensions


@pytest.mark.parametrize("h,w,expected", [(337, 508, (338, 508)), (338, 509, (338, 510)), (337, 509, (338, 510)), (4, 6, (4, 6))])
def test_dimensions_become_even(h: int, w: int, expected: tuple[int, int]) -> None:
    out = even_dimensions(torch.rand(3, h, w, 3))
    assert (out.shape[1], out.shape[2]) == expected and out.shape[0] == 3 and out.shape[3] == 3


def test_original_pixels_are_kept_and_the_edge_is_replicated() -> None:
    src = torch.rand(2, 5, 7, 3)
    out = even_dimensions(src)
    assert torch.equal(out[:, :5, :7, :], src)
    assert torch.equal(out[:, 5, :7, :], src[:, 4, :, :])
    assert torch.equal(out[:, :5, 7, :], src[:, :, 6, :])


def test_even_input_is_returned_unchanged() -> None:
    src = torch.rand(1, 8, 8, 3)
    assert even_dimensions(src) is src
