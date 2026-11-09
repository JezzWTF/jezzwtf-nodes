from __future__ import annotations

import pytest

from utility_core.duration_frames import (
    FPS_EXPR, MINIMAX_EXPR, PRESETS, JWTFDurationFrames, eval_rows, resolve,
)
from utility_core.expr_eval import ExprError, evaluate, to_frames


# ------------------------------------------------------------ presets

def test_minimax_default_string_is_verbatim() -> None:
    assert MINIMAX_EXPR == "max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17"
    assert JWTFDurationFrames.INPUT_TYPES()["required"]["expression"][1]["default"] == MINIMAX_EXPR


@pytest.mark.parametrize("a, expected", [(0.0, 5), (6.0, 158), (0.2, 5), (1.0, 39), (10.0, 243)])
def test_minimax_values(a: float, expected: int) -> None:
    assert to_frames(MINIMAX_EXPR, a, 24) == expected


def test_minimax_is_always_17k_plus_5() -> None:
    for tenth in range(0, 600):
        n = to_frames(MINIMAX_EXPR, tenth / 10, 24)
        assert n % 17 == 5
        assert n >= round(tenth / 10 * 24)


def test_fps_presets() -> None:
    assert to_frames(FPS_EXPR, 6.0, 30) == 180
    assert to_frames(FPS_EXPR, 2.0, 24) == 48
    assert to_frames(FPS_EXPR, 0.0, 24) == 1


def test_resolve_preset_wins_over_widgets() -> None:
    assert resolve("30 FPS", "a * 1000", 7) == (30, FPS_EXPR)
    assert resolve("MiniMax H3 (24 FPS)", "1", 60) == (24, MINIMAX_EXPR)
    assert resolve("Custom", "a * 2", 0) == (1, "a * 2")
    assert set(PRESETS) == {"MiniMax H3 (24 FPS)", "24 FPS", "30 FPS"}


def test_node_output_and_ui() -> None:
    out = JWTFDurationFrames().run(6.0, "24 FPS", "ignored", 99)
    assert out["result"] == (144, 6.0, 24.0, 24)
    assert JWTFDurationFrames.RETURN_TYPES == ("INT", "FLOAT", "FLOAT", "INT")
    assert JWTFDurationFrames.RETURN_NAMES == ("frames", "seconds", "fps", "fps_int")
    assert isinstance(out["result"][2], float) and isinstance(out["result"][3], int)
    info = out["ui"]["jezzwtf_duration_frames"][0]
    assert info["frames"] == 144 and info["fps"] == 24 and info["expression"] == FPS_EXPR


def test_node_error_includes_expression() -> None:
    with pytest.raises(ValueError, match=r"expression: a / 0"):
        JWTFDurationFrames().run(1.0, "Custom", "a / 0", 24)


def test_eval_rows() -> None:
    fps, expr, rows = eval_rows("Custom", "a * fps", 10, [1, 2.5, "x", None, True] + [1] * 50)
    assert fps == 10 and expr == "a * fps"
    assert rows[0] == {"a": 1.0, "frames": 10, "seconds": 1.0}
    assert rows[1]["frames"] == 25
    assert "error" in rows[2] and rows[2]["a"] == "x"
    assert "error" in rows[3] and "error" in rows[4]
    assert len(rows) == 40


# ------------------------------------------------------------ evaluator semantics

def test_python_semantics() -> None:
    assert evaluate("round(2.5)", 0, 0) == 2  # banker's rounding
    assert evaluate("round(3.5)", 0, 0) == 4
    assert evaluate("7 / 2", 0, 0) == 3.5
    assert evaluate("7 // 2", 0, 0) == 3
    assert evaluate("-7 % 3", 0, 0) == 2
    assert evaluate("2 ** 10", 0, 0) == 1024
    assert evaluate("round(a, 1)", 1.26, 0) == 1.3


def test_operators_and_functions() -> None:
    assert evaluate("1 < a <= 3", 2, 0) is True
    assert evaluate("1 < a <= 3", 4, 0) is False
    assert evaluate("a > 1 and fps > 1", 2, 0) is False
    assert evaluate("a > 1 or fps > 1", 2, 0) is True
    assert evaluate("not a", 0, 0) is True
    assert evaluate("10 if a > 1 else 20", 2, 0) == 10
    assert evaluate("ceil(1.2) + floor(1.8) + int(2.9) + abs(-1)", 0, 0) == 6
    assert evaluate("sqrt(16) + float(1)", 0, 0) == 5.0
    assert evaluate("min(3, a, fps)", 2, 1) == 1
    assert abs(evaluate("pi + e", 0, 0) - 5.859874482) < 1e-6
    assert evaluate("True + 1", 0, 0) == 2
    assert evaluate("-a + +fps", 1, 3) == 2


@pytest.mark.parametrize("expr, msg", [
    ("", "empty"),
    ("   ", "empty"),
    ("1" * 301, "too long"),
    ("1 +", "syntax"),
    ("b + 1", "unknown name"),
    ("__import__('os')", "unknown function"),
    ("open('x')", "unknown function"),
    ("a.real", "unsupported syntax"),
    ("(1).__class__", "unsupported syntax"),
    ("[1, 2]", "unsupported syntax"),
    ("lambda: 1", "unsupported syntax"),
    ("'abc'", "numeric"),
    ("1j", "numeric"),
    ("round(a, ndigits=1)", "keyword"),
    ("max(*[1, 2])", "starred"),
    ("max(1, 2, 3, 4)", "too many"),
    ("a / 0", "division by zero"),
    ("a % 0", "division by zero"),
    ("2 ** 65", "exponent"),
    ("9 ** 9 ** 9", "exponent"),
    ("255 ** 64", "power result too large"),
    ("2 ** 60 * 2 ** 60 * 2 ** 60 * 2 ** 60 * 2 ** 60", "integer too large"),
    ("int(1e300)", "integer too large"),
    ("(-8) ** 0.5", "complex"),
    ("sqrt(-1)", "math error"),
    ("max(5)", "math error"),
    ("1e300 ** 2", "overflow"),
    ("+".join(["1"] * 150), "too complex"),
])
def test_rejections(expr: str, msg: str) -> None:
    with pytest.raises(ExprError, match=msg):
        evaluate(expr, 1.0, 24)


def test_big_but_allowed_power() -> None:
    assert evaluate("2 ** 64", 0, 0) == 2 ** 64
    assert evaluate("7 ** 64", 0, 0) == 7 ** 64


def test_to_frames_limits() -> None:
    with pytest.raises(ExprError, match="finite"):
        to_frames("1e308 * 10", 0, 0)
    with pytest.raises(ExprError, match="finite"):
        to_frames("1e308 * 10 - 1e308 * 10", 0, 0)
    with pytest.raises(ExprError, match="too large"):
        to_frames("1000001", 0, 0)
    assert to_frames("1000000", 0, 0) == 1_000_000
    assert to_frames("-5", 0, 0) == 1
    assert to_frames("2.5", 0, 0) == 2
    assert to_frames("a > 1", 2, 0) == 1


def test_fps_output_connects_to_a_float_frame_rate_input() -> None:
    """ComfyUI refuses INT -> FLOAT links, so the `fps` output must be the FLOAT Video Compare expects."""
    import os
    import re

    source = os.path.join(os.path.dirname(__file__), "..", "..", "nodes", "video_compare.py")
    text = open(source, encoding="utf-8").read()
    match = re.search(r'"frame_rate":\s*\("(\w+)"', text)
    assert match is not None
    fps_type = JWTFDurationFrames.RETURN_TYPES[JWTFDurationFrames.RETURN_NAMES.index("fps")]
    assert fps_type == match.group(1)
