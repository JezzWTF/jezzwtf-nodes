"""Runs the dependency-free Canvas Tools and Gallery modules under Node and checks the results."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[2] / "js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_js(body: str) -> object:
    script = (f"import * as G from {json.dumps((JS / 'canvas_tools' / 'geometry.js').as_uri())};\n"
              f"import * as L from {json.dumps((JS / 'gallery' / 'gallery_logic.js').as_uri())};\n"
              f"const out = (() => {{ {body} }})();\nconsole.log(JSON.stringify(out));")
    done = subprocess.run([NODE or "node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


BOXES = "const b = (id, x, y, w, h) => ({ id, x, y, w, h });"


def test_slash_hits_only_the_boxes_it_crosses() -> None:
    hit = run_js(BOXES + """
      const boxes = [b(1, 0, 0, 100, 50), b(2, 200, 0, 100, 50), b(3, 0, 200, 100, 50)];
      return [G.boxesOnSlash(boxes, -10, 25, 310, 25), G.boxesOnSlash(boxes, 50, -10, 50, 300), G.boxesOnSlash(boxes, 120, 0, 180, 60), G.boxesOnSlash(boxes, 5, 5, 5, 5)];
    """)
    assert hit == [[1, 2], [1, 3], [], [1]]


def test_align_modes() -> None:
    out = run_js(BOXES + """
      const boxes = [b(1, 0, 0, 100, 40), b(2, 50, 100, 200, 60)];
      return Object.fromEntries(G.ALIGN_MODES.map((m) => [m, G.align(boxes, m)]));
    """)
    assert out["left"] == {"1": {"x": 0}, "2": {"x": 0}}
    assert out["right"] == {"1": {"x": 150}, "2": {"x": 50}}
    assert out["top"] == {"1": {"y": 0}, "2": {"y": 0}}
    assert out["bottom"] == {"1": {"y": 120}, "2": {"y": 100}}
    assert out["center-x"] == {"1": {"x": 75}, "2": {"x": 25}}
    assert out["center-y"]["1"] == {"y": 60}
    assert run_js(BOXES + "return [G.align([b(1,0,0,1,1)], 'left'), G.align([b(1,0,0,1,1), b(2,5,5,1,1)], 'nope')];") == [{}, {}]


def test_distribute_equalises_gaps_and_keeps_the_ends() -> None:
    out = run_js(BOXES + """
      return [G.distribute([b(1, 0, 0, 100, 10), b(2, 120, 0, 50, 10), b(3, 500, 0, 100, 10)], 'x'),
              G.distribute([b(1, 0, 0, 10, 50), b(2, 0, 40, 10, 50), b(3, 0, 400, 10, 50), b(4, 0, 900, 10, 50)], 'y'),
              G.distribute([b(1, 0, 0, 1, 1), b(2, 9, 0, 1, 1)], 'x')];
    """)
    assert out[0] == {"2": {"x": 275}}  # gap = (500 - 100 - 50) / 2 = 175 on both sides
    assert out[1] == {"2": {"y": 300}, "3": {"y": 600}}
    assert out[2] == {}


def test_tidy_orders_columns_by_dependency() -> None:
    out = run_js(BOXES + """
      const boxes = [b("c", 700, 300, 100, 80), b("a", 0, 0, 120, 60), b("b", 300, 500, 100, 60), b("d", 50, 900, 100, 40)];
      const links = [{ from: "a", to: "b" }, { from: "b", to: "c" }, { from: "a", to: "c" }];
      return G.tidyByDependency(boxes, links, { gapX: 50, gapY: 20 });
    """)
    # a (depth 0) and d (no links, depth 0) share column 0; b is column 1; c column 2
    assert out["a"] == {"x": 0, "y": 0} and out["d"] == {"x": 0, "y": 80}
    assert out["b"]["x"] == 120 + 50 and out["c"]["x"] == 120 + 50 + 100 + 50
    assert out["b"]["y"] == 0 and out["c"]["y"] == 0


def test_tidy_survives_cycles_and_foreign_links() -> None:
    out = run_js(BOXES + """
      const boxes = [b(1, 10, 10, 50, 50), b(2, 300, 10, 50, 50), b(3, 600, 10, 50, 50)];
      return G.tidyByDependency(boxes, [{ from: 1, to: 2 }, { from: 2, to: 3 }, { from: 3, to: 1 }, { from: 9, to: 1 }, { from: 2, to: 2 }]);
    """)
    assert set(out) == {"1", "2", "3"} and all(p["x"] >= 10 for p in out.values())
    assert run_js("return G.tidyByDependency([], []);") == {}


@pytest.mark.parametrize("selection, moves", [
    ([], True),              # whole workflow
    ([1, 2, 3, 4], True),    # selection containing both forms of pin state
    ([3], True),             # one selected node still targets the whole workflow
    ([1, 3], False),         # filtering pins must not expand the selection
    ([3, 4], False),         # entirely pinned selection
    ([1, 2], True),          # unpinned selection still tidies normally
])
def test_tidy_command_leaves_pins_in_place(selection: list[int], moves: bool) -> None:
    module = (JS / "canvas_tools" / "canvas_tools.js").as_uri()
    out = run_js(f"""
      const {{ readFileSync }} = process.getBuiltinModule('node:fs');
      const {{ runInNewContext }} = process.getBuiltinModule('node:vm');
      const source = readFileSync(new URL({json.dumps(module)}), 'utf8').replace(/^import .*;$/gm, '');
      const nodes = [
        {{ id: 1, pos: [100, 200], size: [120, 60] }},
        {{ id: 2, pos: [900, 800], size: [100, 60], flags: {{ pinned: false }}, inputs: [{{ link: 1 }}, {{ link: 2 }}] }},
        {{ id: 3, pos: [-1000.5, -2000.5], size: [500, 400], flags: {{ pinned: true }} }},
        {{ id: 4, pos: [-500.5, -800.5], size: [300, 200], pinned: true, flags: {{ collapsed: true }} }},
      ];
      let extension, changes = 0, redraws = 0;
      const app = {{
        registerExtension: value => {{ extension = value; }},
        canvas: {{ selected_nodes: Object.fromEntries({json.dumps(selection)}.map(id => [id, nodes[id - 1]])) }},
        graph: {{
          _nodes: nodes,
          links: {{ 1: {{ origin_id: 1 }}, 2: {{ origin_id: 3 }} }},
          change: () => changes++, setDirtyCanvas: () => redraws++,
        }},
      }};
      runInNewContext(source, {{ ...G, app, getLink: (graph, id) => graph.links[id] }});
      extension.commands.find(c => c.id === 'JezzWTF.Canvas.Tidy').function();
      return {{ positions: nodes.map(n => n.pos), changes, redraws }};
    """)
    assert out["positions"] == [
        [100, 200], [290, 200] if moves else [900, 800],
        [-1000.5, -2000.5], [-500.5, -800.5],
    ]
    assert out["changes"] == out["redraws"] == int(moves)


def test_group_rect_pads_with_a_title_bar() -> None:
    assert run_js(BOXES + "return G.groupRect([b(1, 100, 100, 50, 50), b(2, 200, 150, 100, 100)], { pad: 10, title: 30 });") == \
        {"x": 90, "y": 60, "w": 220, "h": 200}


def test_gallery_click_semantics() -> None:
    out = run_js("""
      const order = ["a", "b", "c", "d", "e"];
      const click = (state, ref, mods) => L.applyClick({ ...state, order }, ref, mods);
      let s = { selection: [], anchor: null };
      s = click(s, "b", {});
      const plain = s;
      s = click(s, "d", { ctrl: true });
      const ctrl = s;
      s = click(s, "b", { ctrl: true });
      const untoggled = s;
      s = click({ selection: ["b"], anchor: "b" }, "e", { shift: true });
      const range = s;
      const noAnchor = click({ selection: [], anchor: null }, "c", { shift: true });
      return { plain, ctrl, untoggled, range, noAnchor };
    """)
    assert out["plain"] == {"selection": ["b"], "anchor": "b"}
    assert out["ctrl"] == {"selection": ["b", "d"], "anchor": "d"}
    assert out["untoggled"] == {"selection": ["d"], "anchor": "b"}
    assert out["range"] == {"selection": ["b", "c", "d", "e"], "anchor": "b"}
    assert out["noAnchor"] == {"selection": ["c"], "anchor": "c"}


def test_gallery_selection_helpers() -> None:
    out = run_js("""
      return {
        move: [L.movePick(["a", "b", "c"], "c", -1), L.movePick(["a", "b"], "a", -1), L.movePick(["a", "b"], "z", 1)],
        all: L.selectAll(["c"], ["a", "b", "c"]),
        parse: [L.parseSelection('["a", "a", "", 1, "b"]'), L.parseSelection("nope"), L.parseSelection('{"a":1}')],
        crumbs: L.crumbs("output", "x/y"),
        parent: [L.parentOf("x/y"), L.parentOf("x"), L.parentOf("")],
        ref: [L.refOf("input", "a.png"), L.refOf("output", "a.png")],
        summary: [L.summary([]), L.summary(["d/a.png"]), L.summary(["a.png", "b.png", "c.png", "d.png"])],
      };
    """)
    assert out["move"] == [["a", "c", "b"], ["a", "b"], ["a", "b"]]
    assert out["all"] == ["c", "a", "b"]
    assert out["parse"] == [["a", "b"], [], []]
    assert [c["folder"] for c in out["crumbs"]] == ["", "x", "x/y"] and out["crumbs"][0]["label"] == "output"
    assert out["parent"] == ["x", "", ""]
    assert out["ref"] == ["a.png", "a.png [output]"]
    assert out["summary"] == ["No images picked", "1 image: a.png", "4 images: a.png, b.png, +2 more"]
