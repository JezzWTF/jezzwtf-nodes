"""Runs the dependency-free workspace modules (markdown, search, thumbnails) under Node and checks the results."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WS = Path(__file__).resolve().parents[2] / "js" / "workspace"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_js(body: str) -> object:
    script = (f"import * as MD from {json.dumps((WS / 'md.js').as_uri())};\n"
              f"import * as S from {json.dumps((WS / 'search.js').as_uri())};\n"
              f"import * as P from {json.dumps((WS / 'preview.js').as_uri())};\n"
              f"const out = (() => {{ {body} }})();\nconsole.log(JSON.stringify(out));")
    done = subprocess.run([NODE or "node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_markdown_blocks() -> None:
    blocks = run_js("""
      return MD.parseMarkdown('# Title\\n\\nSome **bold** and `code`.\\n\\n- one\\n- two\\n\\n1. a\\n2. b\\n\\n> note\\n\\n```js\\nlet x = 1;\\n```\\n\\n| A | B |\\n|---|---|\\n| 1 | 2 |\\n');
    """)
    assert [b["type"] for b in blocks] == ["heading", "para", "list", "list", "quote", "code", "table"]
    assert blocks[2]["ordered"] is False and blocks[2]["items"] == ["one", "two"]
    assert blocks[3]["ordered"] is True
    assert blocks[5]["text"] == "let x = 1;" and blocks[5]["lang"] == "js"
    assert blocks[6]["head"] == ["A", "B"] and blocks[6]["rows"] == [["1", "2"]]


def test_inline_and_links_are_safe() -> None:
    out = run_js("""
      return { tokens: MD.parseInline('a **b** `c` *d* [e](https://x.y) [t](topic:run-timer) [bad](javascript:alert(1))'),
               kinds: ['https://a.b', 'http://a.b', 'topic:run-timer', 'javascript:alert(1)', 'data:text/html,x', '/relative'].map(MD.classifyLink) };
    """)
    kinds = [t["t"] for t in out["tokens"] if t["t"] != "text"]
    assert kinds == ["bold", "code", "italic", "link", "link", "link"]
    assert out["kinds"] == ["external", "external", "topic", "blocked", "blocked", "blocked"]


def test_html_is_never_interpreted_as_markup() -> None:
    out = run_js("""
      const blocks = MD.parseMarkdown('<script>alert(1)</script> and <b>x</b>');
      return MD.blocksToText(blocks);
    """)
    assert out == "<script>alert(1)</script> and <b>x</b>"  # plain text; the renderer only uses textContent


def test_every_doc_page_parses_and_links_resolve() -> None:
    index = json.loads((WS / "docs" / "index.json").read_text(encoding="utf-8"))
    ids = {t["id"] for s in index["sections"] for t in s["topics"]}
    assert len(ids) == sum(len(s["topics"]) for s in index["sections"])  # unique ids
    for section in index["sections"]:
        for topic in section["topics"]:
            text = (WS / "docs" / topic["file"]).read_text(encoding="utf-8")
            assert text.startswith("# "), topic["file"]
            for target in re.findall(r"\(topic:([\w-]+)\)", text):
                assert target in ids, f"{topic['file']} links to unknown topic {target}"
    assert "welcome" in ids


def test_search_matching_and_ranking() -> None:
    out = run_js("""
      return {
        all: S.matchesAll('Qwen3.5 caption workflow', 'qwen caption'),
        miss: S.matchesAll('Qwen3.5 caption workflow', 'qwen flux'),
        empty: S.matchesAll('anything', '   '),
        title: S.score({ title: 'Run Timer', text: 'clock history' }, 'timer'),
        body: S.score({ title: 'Other', text: 'a timer inside' }, 'timer'),
        none: S.score({ title: 'x', text: 'y' }, 'timer'),
        natural: S.score({ title: 'Where files are saved', text: 'the file goes to the output folder', keywords: 'save path' }, 'where did my file go'),
        unrelated: S.score({ title: 'Run Timer', text: 'a clock and history' }, 'where did my file go'),
        stopOnly: S.score({ title: 'How it works', text: 'x' }, 'how'),
        snip: S.snippet('a long sentence about the saved file path somewhere', 'saved', 12),
      };
    """)
    assert out["all"] is True and out["miss"] is False and out["empty"] is True
    assert out["title"] > out["body"] > 0 and out["none"] == 0
    assert out["natural"] > 0 and out["unrelated"] == 0 and out["stopOnly"] > 0  # filler words are ignored
    assert "saved" in out["snip"]


def test_workflow_index_and_categories() -> None:
    out = run_js("""
      const wf = { nodes: [
        { id: 1, type: 'UNETLoader', widgets_values: ['minimax_h3_ref2va_pruned_int8_convrot.safetensors', 'default'] },
        { id: 2, type: 'LoraLoaderModelOnly', widgets_values: ['detail.safetensors', 1] },
        { id: 3, type: 'SaveVideo', widgets_values: ['video/x'] },
        { id: 4, type: 'MarkdownNote', widgets_values: ['A long note about the character swap workflow goes here.'] },
        { id: 5, type: 'JWTFRunTimer', title: 'Timer', widgets_values: ['', ''] },
      ], groups: [{ title: 'Bake the character' }] };
      const index = S.indexWorkflow(wf);
      return { index, cat: S.categorize(index) };
    """)
    assert out["index"]["nodeCount"] == 5
    assert "minimax_h3_ref2va_pruned_int8_convrot.safetensors" in out["index"]["models"]
    assert "character swap" in out["index"]["text"] and "Bake the character" in out["index"]["text"]
    assert set(out["cat"]["makes"]) >= {"Video", "Uses a LoRA", "Uses JezzWTF nodes"}
    assert out["cat"]["models"] == ["MiniMax H3"]


def test_three_d_and_video_workflows_are_not_filed_as_images() -> None:
    out = run_js("""
      const cat = (types) => S.categorize({ types, models: [] }).makes;
      return {
        glb: cat(['LoadImage', 'Hy3DModelLoader', 'SaveGLB', 'PreviewImage']),
        mesh: cat(['LoadImage', 'JWTFLoadMesh', 'JWTFMeshUnwrap', 'SaveImage']),
        video: cat(['LoadImage', 'SaveVideo', 'PreviewImage']),
        image: cat(['LoadImage', 'KSampler', 'SaveImage']),
        audio: cat(['TextEncode', 'SaveAudio']),
      };
    """)
    assert out["glb"] == ["3D"] and out["mesh"] == ["3D", "Uses JezzWTF nodes"]
    assert out["video"] == ["Video"] and out["image"] == ["Image"] and out["audio"] == ["Audio"]


def test_api_format_workflows_are_indexed() -> None:
    out = run_js("""
      const api = { "3": { class_type: "KSampler", inputs: { seed: 1, model: ["1", 0] } },
                    "6": { class_type: "UNETLoader", inputs: { unet_name: "flux1-dev.safetensors" } },
                    "7": { class_type: "CLIPTextEncode", inputs: { text: "a long prompt about a person on a beach" } } };
      const index = S.indexWorkflow(api);
      return { index, cat: S.categorize(index) };
    """)
    assert out["index"]["apiFormat"] is True and out["index"]["nodeCount"] == 3
    assert out["index"]["models"] == ["flux1-dev.safetensors"] and "person on a beach" in out["index"]["text"]
    assert out["cat"]["models"] == ["Flux"]


def test_ago_formatting() -> None:
    out = run_js("""
      const now = Date.UTC(2026, 10, 9, 12, 0, 0);
      return [now - 20e3, now - 5 * 60e3, now - 3 * 3600e3, now - 5 * 86400e3, now - 90 * 86400e3, 0, NaN]
        .map((t) => S.ago(t, now));
    """)
    assert out == ["just now", "5m ago", "3h ago", "5 days ago", "2026-08-11", "", ""]


def test_thumbnail_geometry() -> None:
    out = run_js("""
      const wf = { nodes: [{ id: 1, pos: [0, 0], size: [100, 50] }, { id: 2, pos: [300, 100], size: [100, 100] }, { id: 3 }],
                   groups: [{ bounding: [-20, -20, 500, 300] }] };
      const b = P.workflowBounds(wf);
      const f = P.fit(b, 200, 100, 8);
      return { b, f, empty: P.workflowBounds({ nodes: [{ pos: ['x'] }] }) };
    """)
    assert out["b"] == {"x": -20, "y": -20, "right": 480, "bottom": 280}
    assert out["empty"] is None
    f = out["f"]
    assert f["scale"] == pytest.approx(min(184 / 500, 84 / 300))
    # the whole box lands inside the canvas
    assert f["ox"] + out["b"]["x"] * f["scale"] >= 0 and f["oy"] + out["b"]["y"] * f["scale"] >= 0
