"""H3 upscale picker: same-scale target search, caps, megapixel mode, and Python/JS parity."""
from __future__ import annotations

import json
import math
import os
import random
import shutil
import subprocess

import pytest

from refmod_h3 import upscale_picker as up

JS_MATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "js", "refmod_h3", "upscale_math.js"))


def reference_cost(w: int, h: int, tw: int, th: int, s: float) -> float | None:
    """Independent restatement of the spec's rejection rule and cost."""
    sw, sh = tw / w, th / h
    if sw < 1 - 1e-9 or sh < 1 - 1e-9:
        return None
    eff = (sw + sh) / 2
    if eff > 4:
        return None
    return 20 * abs(sw - sh) / eff + abs(eff / s - 1)


def test_simple_exact_cases() -> None:
    p = up.pick_target(640, 352, "Scale factor", "2x")
    assert (p.width, p.height) == (1280, 704)
    assert p.scale == pytest.approx(2.0) and p.note == ""
    assert "exact" in p.info and p.info.startswith("640x352 -> 1280x704 |")
    p = up.pick_target(512, 512, "Scale factor", "1.5x")
    assert (p.width, p.height) == (768, 768)


def test_winner_is_the_cheapest_candidate_and_ties_prefer_smaller_width() -> None:
    rnd = random.Random(11)
    for _ in range(60):
        w, h = rnd.randint(64, 2000), rnd.randint(64, 2000)
        label = rnd.choice(["1.5x", "2x", "2.5x", "3x", "4x"])
        m = rnd.choice([16, 32, 48, 64])
        p = up.pick_target(w, h, "Scale factor", label, multiple=m)
        s = up.label_scale(label)
        costs = [(c, cw, ch) for cw, ch in up.candidates(w, h, s, up.grid(m))
                 if (c := reference_cost(w, h, cw, ch, s)) is not None]
        assert costs, "a candidate must survive for ordinary sizes"
        best = min(costs, key=lambda t: (t[0], t[1]))
        assert (p.width, p.height) == (best[1], best[2])
        assert p.width % up.grid(m) == 0 and p.height % up.grid(m) == 0
        assert p.scale_w >= 1 - 1e-9 and p.scale_h >= 1 - 1e-9 and p.scale <= 4


def test_never_shrinks_and_stays_close_to_exact_for_reasonable_sizes() -> None:
    for w, h in [(1000, 563), (720, 1280), (333, 777), (1920, 1080), (96, 64)]:
        p = up.pick_target(w, h, "Scale factor", "2x")
        assert p.width >= w and p.height >= h
        assert abs(p.scale_w - p.scale_h) / p.scale < 0.2
        assert abs(p.scale - 2.0) < 0.5


def test_label_parsing_and_custom() -> None:
    assert up.label_scale("2.5x") == 2.5 and up.label_scale(" 3 x") == 3.0 and up.label_scale("4×") == 4.0
    assert up.label_scale("fast") == 2.0
    p = up.pick_target(640, 352, "Scale factor", "Custom", custom_scale=1.5)
    assert (p.width, p.height) == (960, 528)
    assert up.pick_target(640, 352, "Scale factor", "Custom", custom_scale=3.0).requested == 3.0


def test_scale_caps_and_notes() -> None:
    p = up.pick_target(640, 352, "Scale factor", "Custom", custom_scale=9.0)
    assert p.requested == 4.0 and p.note == "capped at 4x" and p.scale <= 4 and p.info.endswith("capped at 4x")
    p = up.pick_target(640, 352, "Target megapixels", target_megapixels=0.05)
    assert p.requested == 1.0 and p.note == "no upscale (target <= source)"
    assert (p.width, p.height) == (640, 352)


def test_megapixel_mode_targets_the_area() -> None:
    p = up.pick_target(640, 352, "Target megapixels", target_megapixels=2.0)
    got = p.width * p.height / 1048576
    assert abs(got - 2.0) / 2.0 < 0.08
    s = math.sqrt(2.0 * 1048576 / (640 * 352))
    assert p.requested == pytest.approx(s)
    big = up.pick_target(64, 64, "Target megapixels", target_megapixels=16.0)
    assert big.requested == 4.0 and big.note == "capped at 4x"


def test_no_survivor_falls_back_to_ceiling_grid() -> None:
    p = up.pick_target(1, 1, "Scale factor", "2x")
    assert (p.width, p.height) == (16, 16)


def test_grid_rounds_multiple_up_to_16() -> None:
    assert up.grid(16) == 16 and up.grid(17) == 32 and up.grid(5) == 16 and up.grid(256) == 256


def test_node_output_and_ui_payload() -> None:
    out = up.JWTFH3UpscalePicker().pick(640, 352, "Scale factor", "2x", 2.0, 0.5, 16)
    assert out["result"][:3] == (1280, 704, pytest.approx(2.0))
    ui = out["ui"]["jezzwtf_upscale"][0]
    assert ui == {"sw": 640, "sh": 352, "tw": 1280, "th": 704, "scale": pytest.approx(2.0)}
    spec = up.JWTFH3UpscalePicker.INPUT_TYPES()["required"]
    assert list(spec) == ["width", "height", "mode", "scale", "custom_scale", "target_megapixels", "multiple"]
    assert spec["scale"][1]["default"] == "2x" and spec["multiple"][1]["step"] == 16


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_python_and_js_implement_the_same_function() -> None:
    rnd = random.Random(5)
    cases = []
    for _ in range(80):
        cases.append({
            "w": rnd.randint(1, 3000), "h": rnd.randint(1, 3000),
            "mode": rnd.choice(list(up.MODES)), "scale": rnd.choice(list(up.SCALE_LABELS)),
            "custom": round(rnd.uniform(1, 4), 2), "mp": round(rnd.uniform(0.05, 16), 2),
            "multiple": rnd.choice([16, 32, 48, 64, 100]),
        })
    script = (
        "import(require('url').pathToFileURL(process.argv[1]).href).then(m => {"
        " const cases = JSON.parse(process.argv[2]);"
        " console.log(JSON.stringify(cases.map(c => m.pickTarget(c.w, c.h, c.mode, c.scale, c.custom, c.mp, c.multiple))));"
        "});"
    )
    proc = subprocess.run(["node", "-e", script, JS_MATH, json.dumps(cases)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    for c, g in zip(cases, got):
        p = up.pick_target(c["w"], c["h"], c["mode"], c["scale"], c["custom"], c["mp"], c["multiple"])
        assert (g["width"], g["height"]) == (p.width, p.height), c
        assert g["scale"] == pytest.approx(p.scale) and g["note"] == p.note, c
        assert g["info"] == p.info, c
