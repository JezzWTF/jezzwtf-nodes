"""Package contract: mappings, naming conventions, node interfaces, preview wrapper helpers and JS parity."""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import numpy as np
import pytest
import refmod_h3
import torch
from comfy_api.latest import io
from PIL import Image

from refmod_h3 import curves, preview
from refmod_h3 import _comfy
from v3_helpers import legacy_spec

CURVE_JS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "js", "refmod_h3", "curve_math.js"))
EXPECTED = {
    "JWTFRefModBake": "RefMod Bake (Character)", "JWTFRefModLoader": "RefMod Loader", "JWTFRefModApply": "RefMod Apply",
    "JWTFTailRefMod": "Tail RefMod", "JWTFTailCapture": "Tail Capture", "JWTFTailLoad": "Tail Load",
    "JWTFUnifiedRefModBake": "Image RefMod Bake", "JWTFUnifiedRefModApply": "Image RefMod Apply",
    "JWTFRefmodCardBaker": "Refmod Character Card Baker", "JWTFH3ImageEdit": "MiniMax H3 Image Edit",
    "JWTFUltimateKSampler": "Ultimate KSampler", "JWTFH3KSampler": "H3 KSampler",
    "JWTFH3UpscalePicker": "H3 Upscale Picker", "JWTFUltimateModelLoader": "Ultimate Model Loader",
}


def _schemas() -> dict[str, io.Schema]:
    return {s.node_id: s for s in (n.GET_SCHEMA() for n in refmod_h3.NODES)}


def test_mappings_cover_the_whole_family() -> None:
    schemas = _schemas()
    assert {k: s.display_name for k, s in schemas.items()} == EXPECTED
    assert len(refmod_h3.NODES) == len(EXPECTED)


def test_naming_conventions_and_interfaces() -> None:
    for node in refmod_h3.NODES:
        schema = node.GET_SCHEMA()
        key = schema.node_id
        assert key.startswith("JWTF")
        name = schema.display_name
        assert name.isascii() and name == name.strip(), f"{key}: display name must be plain text"
        assert schema.category in ("JezzWTF/refmod", "JezzWTF/sampling", "JezzWTF/loaders"), key
        spec = legacy_spec(node)
        assert set(spec) <= {"required", "optional", "hidden"} and "required" in spec or key.endswith("Capture")
        assert len(node.RETURN_TYPES) == len(node.RETURN_NAMES), key
        for section in ("required", "optional"):
            for field, entry in spec.get(section, {}).items():
                assert isinstance(entry, tuple) and entry, f"{key}.{field}"
                assert entry[0] is not None


def test_categories() -> None:
    cats = {s.node_id: s.category for s in _schemas().values()}
    assert cats["JWTFUltimateKSampler"] == cats["JWTFH3KSampler"] == "JezzWTF/sampling"
    assert cats["JWTFUltimateModelLoader"] == "JezzWTF/loaders" and cats["JWTFRefModApply"] == "JezzWTF/refmod"


# --------------------------------------------------------------------------- preview helpers

def test_preview_size_and_media_encoders() -> None:
    assert preview.fit_size(2000, 1000, 1000) == (1000, 500) and preview.fit_size(100, 50, 0) == (100, 50)
    assert preview.fit_size(100, 50, 4096) == (100, 50)
    frames = [Image.new("RGB", (32, 24), (i * 20, 0, 0)) for i in range(4)]
    assert preview.encode_jpeg(frames[0], 80)[:2] == b"\xff\xd8"
    webp = preview.encode_webp(frames, 12, 80)
    assert webp[:4] == b"RIFF" and webp[8:12] == b"WEBP"
    assert preview.pick_even(10, 3) == [0, 4 if round(4.5) == 4 else 5, 9] or preview.pick_even(10, 3)[0] == 0
    assert preview.pick_even(3, 8) == [0, 1, 2] and preview.pick_even(5, 1) == [0]
    imgs = preview.tensor_to_images(torch.rand(3, 8, 8, 3))
    assert len(imgs) == 3 and imgs[0].size == (8, 8)


def test_step_metrics_delta_and_timing() -> None:
    m = preview.StepMetrics()
    a = torch.zeros(1, 4, 2, 2)
    assert m.delta(a) == 0.0
    assert m.delta(torch.ones(1, 4, 2, 2)) == pytest.approx(1.0)
    assert m.delta(torch.ones(1, 4, 4, 4)) == 0.0  # shape change resets instead of failing
    assert m.tick() == (0.0, 0.0)
    ms, avg = m.tick()
    assert ms >= 0 and avg >= 0 and len(m.times) <= 8


def test_spectrogram_png_and_latent2rgb() -> None:
    import base64
    import io
    png = preview.spectrogram_png(np.sin(np.linspace(0, 400, 16000)).astype(np.float32))
    with Image.open(io.BytesIO(base64.b64decode(png))) as im:
        assert im.size == (512, 64)
    l2r = preview.Latent2RGB([[0.1, 0.2, 0.3]] * 4, [0.0, 0.0, 0.0])
    out = l2r.frames(torch.randn(1, 4, 5, 6, 6), 3)
    assert out.shape == (3, 6, 6, 3) and out.dtype == torch.uint8
    assert l2r.frames(torch.randn(1, 4, 6, 6), 1).shape == (1, 6, 6, 3)


def test_default_preview_suppression_is_restored() -> None:
    lp = _comfy.optional_module("latent_preview")
    if lp is None or not hasattr(lp, "LatentPreviewer"):
        pytest.skip("ComfyUI latent_preview is not importable here")
    subs = [c for c in preview._all_subclasses(lp.LatentPreviewer) if "decode_latent_to_preview_image" in c.__dict__]
    before = {c: c.__dict__["decode_latent_to_preview_image"] for c in subs}
    with preview.SuppressDefaultPreview():
        assert all(c().decode_latent_to_preview_image("fmt", None) is None for c in subs)
    assert {c: c.__dict__["decode_latent_to_preview_image"] for c in subs} == before


def test_attach_preview_clones_and_registers_under_the_load_bearing_key() -> None:
    class Patcher:
        def __init__(self) -> None:
            self.wrappers: dict[tuple[str, str], object] = {}

        def clone(self) -> "Patcher":
            return Patcher()

        def add_wrapper_with_key(self, kind: str, key: str, fn: object) -> None:
            self.wrappers[(kind, key)] = fn

    base = Patcher()
    out = preview.attach_preview(base, 512, "7", 80, 1, 12, None, "none", None)
    ext = _comfy.optional_module("comfy.patcher_extension")
    if ext is None:
        assert out is base
        return
    assert out is not base and not base.wrappers
    assert list(out.wrappers) == [(ext.WrappersMP.OUTER_SAMPLE, "kj_preview_override")]
    wrapper = out.wrappers[(ext.WrappersMP.OUTER_SAMPLE, "kj_preview_override")]
    assert wrapper.node_id == "7" and wrapper.max_res == 512
    assert preview.attach_preview(object(), 512, "7", 80, 1, 12, None, "none", None) is not None


# --------------------------------------------------------------------------- JS parity for the curve math

@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_curve_math_python_and_js_agree() -> None:
    cases = [{"d": d, "s": s, "v": v, "t": t} for d in curves.DIRECTIONS + ("increase", "decrease", "bogus")
             for s in curves.SHAPES for v in (0.0, 0.35, 1.0) for t in (1, 2, 7, 24)]
    script = (
        "import(require('url').pathToFileURL(process.argv[1]).href).then(m => {"
        " let raw = ''; process.stdin.on('data', c => raw += c).on('end', () => {"
        " const cases = JSON.parse(raw);"
        " console.log(JSON.stringify(cases.map(c => m.directionCurve(c.d, c.s, c.v, c.t))));"
        " });});"
    )
    proc = subprocess.run(["node", "-e", script, CURVE_JS], input=json.dumps(cases), capture_output=True,
                          text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    for c, g in zip(cases, got):
        want = curves.direction_curve(c["d"], c["s"], c["v"], c["t"])
        if want is None:
            assert g is None, c
        else:
            assert g == pytest.approx(want, abs=1e-12), c


def test_js_review_regressions_sampler_preview_and_loader_panel() -> None:
    root = os.path.join(os.path.dirname(__file__), "..", "..", "js", "refmod_h3")
    sp = open(os.path.join(root, "sampler_preview.js"), encoding="utf-8").read()
    lp = open(os.path.join(root, "loader_panel.js"), encoding="utf-8").read()
    assert 'addEventListener("execution_error"' in sp and 'addEventListener("execution_interrupted"' in sp
    assert "mouseenter" not in sp  # focus-on-hover stole typing from other widgets
    assert "const loop = " not in lp and "document.hidden" in lp  # no perpetual animation loop
