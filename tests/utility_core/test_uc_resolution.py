from __future__ import annotations

import pytest

from utility_core.resolution import (
    ASPECT_LABELS, PRESET_LABELS, JWTFResolutionPicker, compute_resolution, parse_ratio, parse_size, snap,
)


def test_label_parsing() -> None:
    assert parse_ratio("16:9 (Widescreen)") == (16.0, 9.0)
    assert parse_ratio("2.35:1 (Cinemascope)") == (2.35, 1.0)
    assert parse_ratio("Custom") == (1.0, 1.0)
    assert parse_size("1920x1080 (Full HD 1080p)") == (1920, 1080)
    assert parse_size("640X360") == (640, 360)
    assert parse_size("nonsense") == (1024, 1024)
    for label in ASPECT_LABELS[:-1]:
        assert parse_ratio(label) != (1.0, 1.0) or label.startswith("1:1")
    for label in PRESET_LABELS:
        assert parse_size(label) != (1024, 1024) or label.startswith("1024x1024")


def test_snap() -> None:
    assert snap(1365.33, 32) == 1376
    assert snap(768, 32) == 768
    assert snap(720, 32) == 736  # 22.5 rounds half up
    assert snap(3, 32) == 32
    assert snap(101, 0) == 101


def _ratio(label: str, mp: float = 1.0, mult: int = 32, swap: bool = False, cw: float = 16, ch: float = 9) -> tuple[int, int]:
    return compute_resolution("Ratio + Megapixels", label, cw, ch, mp, "", True, mult, swap)


def test_ratio_mode() -> None:
    assert _ratio("16:9 (Widescreen)") == (1376, 768)
    assert _ratio("1:1 (Square)") == (1024, 1024)
    assert _ratio("1:1 (Square)", mp=4.0) == (2048, 2048)
    assert _ratio("16:9 (Widescreen)", swap=True) == (768, 1376)
    assert _ratio("Custom", cw=1, ch=1) == (1024, 1024)
    # custom clamps to 0.1..100 and megapixels to 0.05..16
    assert _ratio("Custom", cw=1000, ch=0.0) == _ratio("Custom", cw=100, ch=0.1)
    assert _ratio("1:1 (Square)", mp=99) == _ratio("1:1 (Square)", mp=16)


def test_preset_mode() -> None:
    p = "1280x720 (HD 720p)"
    assert compute_resolution("Preset Resolution", "", 1, 1, 1, p, True, 32, False) == (1280, 736)
    assert compute_resolution("Preset Resolution", "", 1, 1, 1, p, False, 32, False) == (1280, 720)
    assert compute_resolution("Preset Resolution", "", 1, 1, 1, p, False, 32, True) == (720, 1280)


def test_node_latent() -> None:
    w, h, latent = JWTFResolutionPicker().run("Preset Resolution", "1:1 (Square)", 16, 9, 1, "640x360 (16:9 nHD)",
                                              False, 32, False, 3)
    assert (w, h) == (640, 360)
    assert tuple(latent["samples"].shape) == (3, 4, 45, 80)
    assert latent["downscale_ratio_spacial"] == 8


@pytest.mark.parametrize("label", ["16:9 (Widescreen)", "2.39:1 (Anamorphic)", "9:16 (Vertical Video)"])
def test_snapped_sizes_are_multiples(label: str) -> None:
    for mult in (8, 16, 64):
        w, h = _ratio(label, mult=mult)
        assert w % mult == 0 and h % mult == 0
