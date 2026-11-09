"""Bounding-box parsing/conversion, the layout prompt, the prompt box and the LM Studio request path."""

import base64
import io
import json
import wave

import numpy as np
import pytest
import torch

from nodes.llm_cards import bboxes as bb
from nodes.llm_cards import layout_prompt as lp
from nodes.llm_cards import lmstudio as lms
from v3_helpers import legacy, legacy_h

# --------------------------------------------------------------------------- LLM JSON extraction


def test_extract_llm_json_variants():
    assert bb.extract_llm_json("<THINK>\n[1]\n</think>[2]") == [2]
    assert bb.extract_llm_json("reasoning without open tag </think> [3]") == [3]
    assert bb.extract_llm_json("Sure!\n```json\n[{\"a\": 1}]\n```\nDone") == [{"a": 1}]
    assert bb.extract_llm_json("here: [{\"a\": 1},] thanks") == [{"a": 1}]
    assert bb.extract_llm_json("obj {\"x\": 1, } end") == {"x": 1}
    with pytest.raises(bb.BBoxParseError, match="nothing here"):
        bb.extract_llm_json("nothing here")


ELEMENTS = [
    {"type": "text", "bbox": [100, 200, 300, 800], "text": "HELLO", "desc": "bold", "color_palette": ["#ff0000"]},
    {"label": "dog", "bbox": [900, 900, 500, 500], "caption": "a dog"},
    {"type": "obj", "bbox": [1, 2, "x", 4]},
]


def test_elements_to_pixels():
    boxes, key = bb.parse_bboxes_input(json.dumps({"layout": ELEMENTS}), 1000, 500)
    assert len(boxes) == 2  # invalid bbox skipped
    assert boxes[0] == {"x": 200, "y": 50, "width": 600, "height": 100,
                        "metadata": {"type": "text", "text": "HELLO", "desc": "bold", "palette": ["#FF0000"]}}
    assert boxes[1]["x"] == 500 and boxes[1]["y"] == 250 and boxes[1]["width"] == 400
    assert boxes[1]["metadata"] == {"type": "obj", "text": "", "desc": "a dog", "palette": []}
    _, key2 = bb.parse_bboxes_input(ELEMENTS, 2048, 2048)
    assert key == key2  # the upstream key does not depend on the canvas size


def test_pixel_and_frame_inputs():
    frames = [[{"x": 10, "y": 20, "width": 30, "height": 40, "metadata": {"type": "text"}}, {"x": 1}]]
    boxes, _ = bb.parse_bboxes_input(frames, 100, 100)
    assert boxes[0] == {"x": 10, "y": 20, "width": 30, "height": 40, "metadata": {"type": "text"}}
    assert bb.parse_bboxes_input({"x": 1, "y": 2, "width": 3, "height": 4}, 9, 9)[0][0]["width"] == 3
    assert bb.parse_bboxes_input({"bbox": [0, 0, 500, 500]}, 10, 10)[0][0]["width"] == 5
    assert bb.parse_bboxes_input(None, 1, 1) == ([], "")
    assert bb.parse_bboxes_input("   ", 1, 1) == ([], "")
    assert bb.parse_bboxes_input([], 1, 1) == ([], "")
    with pytest.raises(bb.BBoxParseError):
        bb.parse_bboxes_input([{"foo": 1}], 1, 1)
    with pytest.raises(bb.BBoxParseError):
        bb.parse_bboxes_input({"foo": 1}, 1, 1)
    with pytest.raises(bb.BBoxParseError):
        bb.parse_bboxes_input(42, 1, 1)


def test_region_conversions():
    boxes = [{"x": 110, "y": 60, "width": -10, "height": 40,
              "metadata": {"type": "text", "text": "T", "desc": "d", "palette": ["#abcdef", "nope"]}}]
    regions = bb.pixel_boxes_to_regions(boxes, 200, 100)
    assert regions[0]["x"] == pytest.approx(0.5) and regions[0]["w"] == pytest.approx(0.05)
    assert regions[0]["palette"] == ["#ABCDEF"]
    assert bb.regions_to_frames(regions, 200, 100) == [[{"x": 100, "y": 60, "width": 10, "height": 40}]]
    assert bb.regions_to_frames([], 1, 1) == []
    els = bb.regions_to_elements(regions)
    assert els == [{"type": "text", "bbox": [600, 500, 1000, 550], "text": "T", "desc": "d",
                    "color_palette": ["#ABCDEF"]}]
    assert list(els[0]) == ["type", "bbox", "text", "desc", "color_palette"]
    neg = bb.regions_to_elements([{"x": 0.9, "y": 0.5, "w": -0.2, "h": 0.7, "type": "obj", "text": "x", "desc": "",
                                   "palette": []}])
    assert neg == [{"type": "obj", "bbox": [500, 700, 1000, 900], "desc": ""}]


def test_editor_state_parsing():
    state = json.dumps({"v": 1, "regions": [
        {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4, "type": "TEXT", "text": "a", "desc": "b", "palette": ["#00ff00"]},
        {"x": "bad"}, "junk"]})
    regions = bb.regions_from_state(state)
    assert len(regions) == 1 and regions[0]["type"] == "text" and regions[0]["palette"] == ["#00FF00"]
    assert bb.regions_from_state([{"x": 0, "y": 0, "w": 1, "h": 1}])[0]["type"] == "obj"
    assert bb.regions_from_state("{broken") == []


def test_node_upstream_vs_canvas():
    node = bb.JWTFBoundingBoxes()
    state = json.dumps({"regions": [{"x": 0, "y": 0, "w": 0.5, "h": 0.5, "type": "obj"}]})
    out = legacy(node.execute(512, 256, bboxes=ELEMENTS[:1], editor_state=state, last_incoming=""))
    preview, frames, elements = out["result"]
    assert tuple(preview.shape) == (1, 256, 512, 3) and preview.dtype == torch.float32
    assert elements[0]["type"] == "text"  # upstream changed -> regions from the input
    key = out["ui"]["input_key"][0]
    out2 = legacy(node.execute(1024, 512, bboxes=ELEMENTS[:1], editor_state=state, last_incoming=key))
    assert out2["result"][2][0]["type"] == "obj"  # canvas edits win; resize is not an upstream change
    assert out2["result"][1] == [[{"x": 0, "y": 0, "width": 512, "height": 256}]]


def test_preview_with_background_and_colours():
    bg = bb.Image.new("RGB", (2048, 1024), (200, 200, 200))
    regions = bb.regions_from_state([{"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5, "type": "text", "text": "Hi",
                                      "desc": "long words " * 30, "palette": ["#101010", "#FFFFFF"]}])
    img = bb.render_preview(regions, 2048, 1024, bg)
    assert img.size == (1024, 512)
    assert img.getpixel((1000, 500))[0] == 50  # brightness x0.25
    assert bb.luma(bb.readable((16, 16, 16))) == pytest.approx(130, abs=1.5)


# --------------------------------------------------------------------------- layout prompt + prompt box


def test_layout_prompt():
    assert lp.shape_label(1200, 1000) == "landscape"
    assert lp.shape_label(1000, 1150) == "roughly square"
    assert lp.shape_label(100, 200) == "portrait"
    sys_p = lp.build_system_prompt(1536, 1024, 4, "  no people  ")
    assert "1536x1024" in sys_p and "landscape" in sys_p and "1.54 px" in sys_p and "1.02 px" in sys_p
    assert "at most 4 boxes" in sys_p and "- no people\n" in sys_p
    assert sys_p.endswith("\n") and not sys_p.endswith("\n\n")
    user = lp.build_user_prompt("  a cat  ")
    assert user.startswith("Scene description:\na cat\n\n")


@pytest.mark.parametrize("mode,inc,loc,expected", [
    ("APPEND", "a", "b", "a|b"), ("APPEND", "", "b", "b"), ("PREPEND", "a", "b", "b|a"),
    ("PREPEND", "a", "", "a"), ("REPLACE (local wins)", "a", "", "a"), ("REPLACE (local wins)", "a", "b", "b"),
    ("PASSTHROUGH (incoming wins)", "a", "b", "a"), ("PASSTHROUGH (incoming wins)", None, "b", "b"),
])
def test_prompt_box(mode, inc, loc, expected):
    assert lms.combine_prompt(mode, inc, loc, "|") == expected


# --------------------------------------------------------------------------- LM Studio


def test_payload_and_messages():
    msgs = lms.build_messages("  ", [lms.text_part("hi")], "hi")
    assert msgs == [{"role": "user", "content": "hi"}]
    parts = [lms.image_part("AAA"), lms.text_part("hi")]
    msgs = lms.build_messages("sys", parts, "hi")
    assert msgs[0] == {"role": "system", "content": "sys"} and msgs[1]["content"] == parts
    assert parts[0]["image_url"]["url"] == "data:image/jpeg;base64,AAA"
    p = lms.build_payload(" ", msgs, 0.5, 0.9, True, 0, 0)
    assert p["model"] == "local-model" and "max_tokens" not in p and "seed" not in p
    p = lms.build_payload("m", msgs, 0.5, 0.9, False, 100, 7)
    assert p["max_tokens"] == 100 and p["seed"] == 7
    assert lms.resolve_user_text("  over ", "gen") == "over"
    assert lms.resolve_user_text("   ", "gen") == "gen"
    assert lms.to_int("x", 8) == 8 and lms.max_side_of("768") == 768
    assert lms.model_ids({"data": [{"id": "a"}, {"id": 3}, {"x": 1}]}) == ["a"]


def test_image_encoding_downscales():
    img = torch.rand(2, 300, 600, 3)
    parts = lms.image_batch_b64(img, 512)
    assert len(parts) == 2
    decoded = lms.Image.open(io.BytesIO(base64.b64decode(parts[0])))
    assert decoded.format == "JPEG" and decoded.size == (512, 256)
    assert len(lms.image_batch_b64(torch.rand(10, 10, 3), 1024)) == 1


def test_video_tensor_sampling():
    frames = lms.video_frames_b64(torch.rand(20, 8, 8, 3), 4, 512)
    assert len(frames) == 4
    assert len(lms.video_frames_b64([torch.rand(2, 8, 8, 3)], 8, 512)) == 2


def test_audio_wav():
    audio = {"waveform": torch.zeros(1, 2, 100), "sample_rate": 16000}
    raw = base64.b64decode(lms.audio_b64(audio))
    with wave.open(io.BytesIO(raw)) as w:
        assert w.getnchannels() == 2 and w.getframerate() == 16000 and w.getsampwidth() == 2
        assert w.getnframes() == 100


def test_sse_parsing():
    lines = ["", ": ping", 'data: {"choices":[{"delta":{"content":"Hel"}}]}', "data: not json",
             'data: {"choices":[{"delta":{}}]}', 'data:{"choices":[{"delta":{"content":"lo"}}]}', "data: [DONE]",
             'data: {"choices":[{"delta":{"content":"late"}}]}']
    pieces = [lms._delta_text(c) for c in lms.iter_sse_chunks(lines)]
    assert "".join(pieces) == "Hello"


def test_run_completion_stream(monkeypatch):
    sent = {}

    def fake_post(url, payload, stream):
        sent.update(url=url, payload=payload, stream=stream)
        yield 'data: {"choices":[{"delta":{"content":"A"}}]}'
        yield 'data: {"choices":[{"delta":{"content":"B"}}]}'
        yield "data: [DONE]"

    monkeypatch.setattr(lms, "_http_post", fake_post)
    seen = []
    text, tokens = lms.run_completion("http://h:1/", {"stream": True}, lambda t, n: seen.append((t, n)))
    assert (text, tokens) == ("AB", 2) and seen == [("A", 1), ("AB", 2)]
    assert sent["url"] == "http://h:1/v1/chat/completions" and sent["stream"] is True


def test_run_completion_non_stream(monkeypatch):
    body = {"choices": [{"message": {"content": "done"}}], "usage": {"completion_tokens": 9}}
    monkeypatch.setattr(lms, "_http_post", lambda u, p, s: iter([json.dumps(body)]))
    assert lms.run_completion("http://h", {"stream": False}) == ("done", 9)


def test_node_run_success_and_error(monkeypatch):
    events = []
    monkeypatch.setattr(lms, "send_event", lambda e, p: events.append((e, dict(p))))
    captured = {}

    def fake_completion(base, payload, on_piece):
        captured.update(base=base, payload=payload)
        on_piece("partial", 1)
        return "reply", 1

    monkeypatch.setattr(lms, "run_completion", fake_completion)
    node = lms.JWTFLMStudio
    out = legacy_h(node, "7", lambda: node.execute("http://x:1/", "", "sys", "gen", 0, 0.7, 0.95, True, 0, "512", 8,
                   image=torch.rand(1, 4, 4, 3), prompt_override="over"))
    assert out["result"] == ("reply", "over") and out["ui"]["text"] == ["reply"]
    assert captured["base"] == "http://x:1"
    content = captured["payload"]["messages"][1]["content"]
    assert content[0]["type"] == "image_url" and content[-1] == {"type": "text", "text": "over"}
    states = [p["state"] for _, p in events]
    assert states == ["start", "stream", "done"]
    assert events[0][1]["media"] == {"image": 1, "video": 0, "audio": 0} and events[0][1]["max_tokens"] == 0
    assert all(e == lms.EVENT for e, _ in events)

    def boom(*_a):
        raise ConnectionError("refused")

    monkeypatch.setattr(lms, "run_completion", boom)
    events.clear()
    out = legacy_h(node, None, lambda: node.execute("", "m", "", "hello", 512, 0.7, 0.95, False, 0, "1024", 8, video="missing.mp4"))
    assert "refused" in out["result"][0] and lms.DEFAULT_URL in out["result"][0]
    assert out["result"][1] == "hello"
    assert events[-1][1]["state"] == "error" and events[-1][1]["node"] == "-1"
    assert lms.JWTFLMStudio.fingerprint_inputs() != lms.JWTFLMStudio.fingerprint_inputs()  # NaN
    assert np.isnan(lms.JWTFLMStudio.fingerprint_inputs())
