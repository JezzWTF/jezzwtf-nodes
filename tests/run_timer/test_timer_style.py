"""Runs the dependency-free Run Timer style module under Node and checks the results."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STYLE = Path(__file__).resolve().parents[2] / "js" / "run_timer" / "timer_style.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_js(body: str) -> object:
    script = f"import * as S from {json.dumps(STYLE.as_uri())};\nconst out = (() => {{ {body} }})();\nconsole.log(JSON.stringify(out));"
    done = subprocess.run([NODE or "node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_sanitize_fills_gaps_and_rejects_junk() -> None:
    out = run_js("""
      return [S.sanitize(undefined), S.sanitize(null), S.sanitize("x"),
              S.sanitize({ face: "ring", skin: "neon", theme: "ice", color: "#ABCDEF", font: "serif", background: "clear", statusTint: false }),
              S.sanitize({ face: "cube", theme: "__proto__", color: "red", font: 5, background: "toString", statusTint: "yes" })];
    """)
    default = {"skin": "glass", "face": "digital", "theme": "ember", "color": "", "font": "mono", "background": "dark", "statusTint": True, "anim": "arc", "lap": "60"}
    assert out[0] == out[1] == out[2] == default
    assert out[3] == {"skin": "neon", "face": "ring", "theme": "ice", "color": "#abcdef", "font": "serif", "background": "clear", "statusTint": False, "anim": "arc", "lap": "60"}
    assert out[4] == default


def test_accent_prefers_a_custom_colour_and_vars_follow_the_style() -> None:
    out = run_js("""
      const plain = S.sanitize({ theme: "mint" });
      const custom = S.sanitize({ theme: "mint", color: "#112233", font: "thin", background: "light" });
      return [S.accent(plain), S.accent(custom), S.cssVars(custom)];
    """)
    assert out[0] == "#3ddc97" and out[1] == "#112233"
    assert out[2]["--rt-color"] == "#112233" and out[2]["--rt-weight"] == "200" and out[2]["--rt-scale"] == "0.8" and out[2]["--rt-bg"] == "#e9e9ee"
    assert "Light" in out[2]["--rt-font"]


def test_aspect_per_face() -> None:
    assert run_js("return [S.aspectOf('digital', 2.03), S.aspectOf('ring', 2.03), S.aspectOf('analog', 2.03)];") == [2.03, 1, 1]


def test_ring_laps_and_rest() -> None:
    out = run_js("""
      const s = (o) => S.ringState({ running: true, elapsedMs: 0, lapMs: 60000, ...o });
      return [s({ elapsedMs: 30000 }), s({ elapsedMs: 60000 }), s({ elapsedMs: 150000 }), s({ elapsedMs: 15000, lapMs: 10000 }),
              S.ringState({ running: false, elapsedMs: 99999, lapMs: 60000 }), s({ elapsedMs: -5 })];
    """)
    assert out == [{"lap": 0, "frac": 0.5, "rest": False}, {"lap": 1, "frac": 0, "rest": False},
                   {"lap": 2, "frac": 0.5, "rest": False}, {"lap": 1, "frac": 0.5, "rest": False},
                   {"lap": 0, "frac": 1, "rest": True}, {"lap": 0, "frac": 0, "rest": False}]


def test_lap_length_choices() -> None:
    assert run_js("return [S.lapMsFor('10', 0), S.lapMsFor('60', 5000), S.lapMsFor('avg', 80000), S.lapMsFor('avg', 0), S.lapMsFor('junk', 0)];") == [10000, 60000, 80000, 60000, 60000]


def test_second_colour_turns_the_hue_and_keeps_valid_hex() -> None:
    out = run_js("return ['#e8703a', '#3ddc97', '#cccccc', '#000000', '#ffffff'].map(S.secondColor);")
    assert all(len(c) == 7 and c.startswith("#") for c in out)
    assert out[0] != "#e8703a" and out[2] == "#cccccc" and out[3] == "#000000" and out[4] == "#ffffff"


def test_motion_choices_are_validated() -> None:
    out = run_js("return [S.sanitize({ anim: 'ticks', lap: '30' }), S.sanitize({ anim: 'x', lap: 7 })];")
    assert out[0]["anim"] == "ticks" and out[0]["lap"] == "30" and out[1]["anim"] == "arc" and out[1]["lap"] == "60"


def test_hand_angles() -> None:
    out = run_js("return [0, 15000, 60000, 90000, 1800000, -5, 'x'].map(S.handAngles);")
    assert out[0] == {"second": 0, "minute": 0} and out[1]["second"] == 90 and out[2]["second"] == 0
    assert out[3]["second"] == 180 and out[3]["minute"] == 18 and out[4]["minute"] == 0
    assert out[5] == out[6] == {"second": 0, "minute": 0}
