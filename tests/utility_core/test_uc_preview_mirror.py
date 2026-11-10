from __future__ import annotations

import json
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest
from utility_core import preview_mirror as pm
from utility_core.preview_mirror import JWTFModelPreviewMirror, source_id
from v3_helpers import legacy

LOGIC = Path(__file__).resolve().parents[2] / "js" / "utility_core" / "mirror_logic.js"
NODE = shutil.which("node")


class FakeWrapper:
    def __init__(self, node_id: object) -> None:
        self.node_id = node_id


class FakeModel:
    def __init__(self, wrappers: list[FakeWrapper]) -> None:
        self._wrappers = wrappers
        self.asked: list[tuple[object, str]] = []

    def get_wrappers(self, kind: object, key: str) -> list[FakeWrapper]:
        self.asked.append((kind, key))
        return self._wrappers


@pytest.fixture()
def fake_comfy(monkeypatch: pytest.MonkeyPatch) -> None:
    extension = types.SimpleNamespace(WrappersMP=types.SimpleNamespace(OUTER_SAMPLE="outer_sample"))
    monkeypatch.setitem(sys.modules, "comfy", types.ModuleType("comfy"))
    monkeypatch.setitem(sys.modules, "comfy.patcher_extension", extension)


def test_source_is_the_last_preview_wrappers_node_id(fake_comfy: None) -> None:
    model = FakeModel([FakeWrapper("3"), FakeWrapper(17)])
    assert source_id(model) == "17"
    assert model.asked == [("outer_sample", pm.WRAPPER_KEY)]


def test_no_source_when_there_is_nothing_to_follow(fake_comfy: None) -> None:
    assert source_id(FakeModel([])) is None
    assert source_id(FakeModel([FakeWrapper(None)])) is None
    assert source_id(FakeModel([FakeWrapper("")])) is None
    assert source_id(object()) is None
    assert source_id("a string") is None


def test_a_model_that_cannot_report_wrappers_does_not_fail(fake_comfy: None) -> None:
    class Broken:
        def get_wrappers(self, *_: object) -> list[object]:
            raise RuntimeError("odd patcher")

    assert source_id(Broken()) is None


def test_node_passes_the_value_through_and_names_the_source(fake_comfy: None) -> None:
    model = FakeModel([FakeWrapper("9")])
    out = legacy(JWTFModelPreviewMirror.execute(any=model))
    assert out["result"][0] is model and out["ui"] == {pm.UI_KEY: ["9"]}
    plain = legacy(JWTFModelPreviewMirror.execute(any="text"))
    assert plain["result"][0] == "text" and plain["ui"] == {pm.UI_KEY: []}
    nothing = legacy(JWTFModelPreviewMirror.execute())
    assert nothing["result"][0] is None and nothing["ui"] == {pm.UI_KEY: []}


def test_schema() -> None:
    schema = JWTFModelPreviewMirror.GET_SCHEMA()
    assert schema.node_id == "JWTFModelPreviewMirror" and schema.is_output_node
    assert [i.id for i in schema.inputs] == ["any"]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_panel_rules_under_node() -> None:
    script = (f"import * as L from {json.dumps(LOGIC.as_uri())};\n"
              "console.log(JSON.stringify({\n"
              "  follows: [L.follows('', 5), L.follows(null, 5), L.follows('5', 5), L.follows('5', '6'), L.follows('5', ''), L.follows('5', null),\n"
              "            L.follows('12:34', '34'), L.follows('34', '12:34'), L.follows('12:34', '99:34'), L.follows('7', '17')],\n"
              "  line: [L.statusLine({ step: 4, total: 20, sigma: 0.8123, delta: 0.0314 }), L.statusLine({ step: 2 }), L.statusLine({}), L.statusLine(null)],\n"
              "  media: [L.mediaSource({ image: 'AAA', mime: 'video/mp4' }), L.mediaSource({ image: 'AAA' }), L.mediaSource({ image: 'AAA', mime: 'text/html' }), L.mediaSource({}), L.mediaSource(null)],\n"
              "}));")
    done = subprocess.run([NODE or "node", "--input-type=module", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert out["follows"] == [True, True, True, False, False, False, True, True, False, False]
    assert out["line"] == ["step 4/20 · sigma 0.812 · change 0.031", "step 2", "", ""]
    assert out["media"][0] == {"url": "data:video/mp4;base64,AAA", "video": True}
    assert out["media"][1] == {"url": "data:image/jpeg;base64,AAA", "video": False}
    assert out["media"][2]["url"].startswith("data:image/jpeg;") and out["media"][3] is None and out["media"][4] is None
