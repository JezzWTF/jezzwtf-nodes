"""Runs the dependency-free frontend logic module under Node and checks the results."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

LOGIC = Path(__file__).resolve().parents[2] / "js" / "paste_stack" / "stack_logic.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_js(body: str) -> object:
    script = f"import * as L from {json.dumps(LOGIC.as_uri())};\nconst out = await (async () => {{ {body} }})();\nconsole.log(JSON.stringify(out));"
    done = subprocess.run([NODE or "node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_fingerprint_is_sha256_prefix_and_dedupes_by_kind() -> None:
    out = run_js(
        """
        const a = await L.fingerprint(new Blob(['hello']));
        const b = await L.fingerprint(new Blob(['hello']));
        const c = await L.fingerprint(new Blob(['hellp']));
        const items = [{kind:'text',key:a,id:'1'},{kind:'image',key:c,id:'2'}];
        return {a, same: a===b, diff: a!==c, hit: L.findDuplicate(items,'text',a)?.id,
                miss: L.findDuplicate(items,'image',a), len: a.length};
        """
    )
    assert isinstance(out, dict)
    assert out["a"] == "2cf24dba5fb0a30e26e83b2ac5b9e29e"
    assert out["same"] and out["diff"] and out["hit"] == "1" and out["miss"] is None and out["len"] == 32


def test_fingerprint_falls_back_without_subtle() -> None:
    out = run_js("return [await L.fingerprint(new Blob(['abc'], {type:'image/png'}), null), L.fallbackKey(3, '')];")
    assert out == ["3:image/png", "3:"]


def test_eviction_removes_smallest_ts_regardless_of_order() -> None:
    out = run_js(
        """
        const items = [{id:'a',ts:50,ord:-2},{id:'b',ts:10,ord:-1},{id:'c',ts:30,ord:0},{id:'d',ts:20,ord:1}];
        return {two: L.pickEvictions(items, 2).map(x=>x.id), none: L.pickEvictions(items, 4), all: L.pickEvictions(items, 0).length};
        """
    )
    assert out == {"two": ["b", "d"], "none": [], "all": 4}


def test_midpoint_reorder() -> None:
    out = run_js(
        """
        const o = [0, 1, 2, 3];
        return {
          noop: L.planMove(o, 1, 1),
          mid: L.planMove(o, 0, 2),      // lifted list [1,2,3] -> between 2 and 3
          top: L.planMove(o, 3, 0),
          bottom: L.planMove(o, 0, 3),
          alone: L.planMove([5], 0, 0),
          between: L.planMove([0, 10, 20], 2, 1),
        };
        """
    )
    assert out == {
        "noop": None,
        "mid": {"ord": 2.5, "to": 2},
        "top": {"ord": -1, "to": 0},
        "bottom": {"ord": 4, "to": 3},
        "alone": None,
        "between": {"ord": 5, "to": 1},
    }


def test_reorder_renumbers_when_floats_exhausted() -> None:
    out = run_js("const a = 1; const b = 1 + Number.EPSILON; return L.planMove([a, b, 9], 2, 1);")
    assert out == {"renumber": True, "to": 1}


def test_move_in_array() -> None:
    assert run_js("return L.moveInArray(['a','b','c','d'], 0, 2);") == ["b", "c", "a", "d"]


def test_normalize_order_legacy_above_ordered() -> None:
    out = run_js(
        """
        const recs = [{id:'o1',ord:5,ts:1},{id:'l_old',ts:100},{id:'o0',ord:3,ts:2},{id:'l_new',ts:200}];
        const {items, changed} = L.normalizeOrder(recs);
        return {ids: items.map(i=>i.id), ords: items.map(i=>i.ord), changed: changed.map(i=>i.id),
                top: L.nextTopOrd(items), empty: L.nextTopOrd([])};
        """
    )
    assert out == {
        "ids": ["l_new", "l_old", "o0", "o1"],
        "ords": [1, 2, 3, 5],
        "changed": ["l_new", "l_old"],
        "top": 0,
        "empty": 0,
    }


def test_limits_and_refusals() -> None:
    out = run_js(
        """
        return {
          t: L.refusalFor('text', 1000001), tok: L.refusalFor('text', 1000000),
          i: L.refusalFor('image', 25*1024*1024+1), iok: L.refusalFor('image', 25*1024*1024),
          f: L.refusalFor('file', 26*1024*1024, 'a.zip'),
          tf: L.refusalFor('text-file', 1000001, 'big.txt'),
          lim: [L.normalizeLimit(0), L.normalizeLimit('abc'), L.normalizeLimit(1), L.normalizeLimit(9999), L.normalizeLimit(75)],
        };
        """
    )
    assert isinstance(out, dict)
    assert out["t"] == "That text is too long to save (over 1,000,000 characters)."
    assert out["tok"] == "" and out["iok"] == ""
    assert out["i"] == "That image is over 25 MB, so it wasn't saved."
    assert out["f"] == "a.zip is over 25 MB, so it wasn't saved."
    assert out["tf"] == "big.txt is too large to save as text."
    assert out["lim"] == [50, 50, 5, 500, 75]


def test_classification_and_image_path_detection() -> None:
    out = run_js(
        """
        return {
          c: [L.classifyFile('a.PNG',''), L.classifyFile('x.bin','application/octet-stream'), L.classifyFile('n.py',''),
              L.classifyFile('d','application/json'), L.classifyFile('m.mp4','video/mp4'), L.classifyFile('r.md','text/markdown')],
          mime: [L.imageMimeFromName('a.jpg'), L.imageMimeFromName('a.txt')],
          p: [L.looksLikeImagePath('C:\\\\pics\\\\a.PNG'), L.looksLikeImagePath('/home/u/a.jpeg'), L.looksLikeImagePath('a.png'),
              L.looksLikeImagePath('/a.png\\n/b.png'), L.looksLikeImagePath('/a.txt'), L.looksLikeImagePath('a cat')],
        };
        """
    )
    assert out == {
        "c": ["image", "file", "text", "text", "file", "text"],
        "mime": ["image/jpeg", ""],
        "p": [True, True, False, False, False, False],
    }


def test_upload_name_and_widget_value() -> None:
    out = run_js(
        """
        return [
          L.safeUploadName('a/b:c*d.png', 'id1', 'image/png'),
          L.safeUploadName('', 'id2', 'image/jpeg'),
          L.safeUploadName('shot', 'id3', 'image/svg+xml'),
          L.safeUploadName('w<>|.x', 'id4', ''),
          L.widgetValueFrom({name:'a.png', subfolder:'sub'}), L.widgetValueFrom({name:'a.png', subfolder:''}),
        ];
        """
    )
    assert out == ["a_b_c_d.png", "paste_id2.jpg", "shot.svg", "w_.x.png", "sub/a.png", "a.png"]


def test_node_accepts_image() -> None:
    out = run_js(
        """
        const combo = {name:'image', type:'combo'};
        return [
          L.nodeAcceptsImage({widgets:[combo]}),
          L.nodeAcceptsImage({widgets:[{name:'image', options:{values:[]}}]}),
          L.nodeAcceptsImage({widgets:[combo], flags:{collapsed:true}}),
          L.nodeAcceptsImage({widgets:[combo], comfyClass:'LoadImageOutput'}),
          L.nodeAcceptsImage({widgets:[{name:'image', type:'text'}]}),
          L.nodeAcceptsImage({widgets:[{name:'img', type:'combo'}]}),
          L.nodeAcceptsImage(null),
        ];
        """
    )
    assert out == [True, True, False, False, False, False, False]


def test_age_size_and_id_formatting() -> None:
    out = run_js(
        """
        const now = 10_000_000_000;
        return {
          age: [0, 44, 45, 150, 3599, 3600, 86399, 86400*3].map(s => L.relativeAge(now - s*1000, now)),
          size: [L.formatSize(10), L.formatSize(2048), L.formatSize(5*1024*1024+104858)],
          id: L.makeId(1000, () => 0.5), idLen: L.makeId().length >= 8,
        };
        """
    )
    assert out == {
        "age": ["just now", "just now", "1m ago", "2m ago", "59m ago", "1h ago", "23h ago", "3d ago"],
        "size": ["10 B", "2 KB", "5.1 MB"],
        "id": "rsiiii",
        "idLen": True,
    }
