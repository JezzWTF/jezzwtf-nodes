"""Bounding-box editor node and its pure geometry/parsing helpers (spec section 4)."""

from __future__ import annotations

import json
import math
import re
from typing import Mapping, Sequence, TypedDict

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from comfy_api.latest import io

from .common import JSONValue, frame_to_pil, pil_to_tensor

TAG = "[JezzWTF Bounding Boxes]"
PREVIEW_LONG_EDGE = 1024
GREY = (140, 140, 140)
WRAPPER_KEYS = ("elements", "items", "boxes", "bboxes", "layout", "regions", "objects")
_HEX = re.compile(r"^#[0-9A-F]{6}$")


class BoxMeta(TypedDict):
    type: str
    text: str
    desc: str
    palette: list[str]


class _PixelBoxBase(TypedDict):
    x: float
    y: float
    width: float
    height: float


class PixelBox(_PixelBoxBase, total=False):
    metadata: BoxMeta


class Region(TypedDict):
    x: float
    y: float
    w: float
    h: float
    type: str
    text: str
    desc: str
    palette: list[str]


class _ElementBase(TypedDict):
    type: str
    bbox: list[int]


class Element(_ElementBase, total=False):
    text: str
    desc: str
    color_palette: list[str]


class BBoxParseError(ValueError):
    pass


# --------------------------------------------------------------------------- small helpers


_NUM_LIMIT = 1e9  # any coordinate beyond this is garbage; it would overflow round() after scaling


def _finite(v: float) -> float | None:
    return v if math.isfinite(v) and abs(v) <= _NUM_LIMIT else None


def _num(value: object) -> float | None:
    """A finite float, or None for non-numbers, bools, NaN, infinities and absurd magnitudes."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return _finite(float(value))
        except OverflowError:
            return None
    if isinstance(value, str):
        try:
            return _finite(float(value.strip()))
        except ValueError:
            return None
    return None


def _intish(v: float) -> float:
    return int(v) if float(v).is_integer() else v


def norm_kind(value: object) -> str:
    return "text" if isinstance(value, str) and value.strip().lower() == "text" else "obj"


def norm_palette(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        s = item.strip().upper()
        if not s.startswith("#"):
            s = "#" + s
        if len(s) == 4 and re.match(r"^#[0-9A-F]{3}$", s):
            s = "#" + "".join(c * 2 for c in s[1:])
        if _HEX.match(s):
            out.append(s)
        if len(out) == 5:
            break
    return out


def _str(value: object) -> str:
    return value if isinstance(value, str) else ""


# --------------------------------------------------------------------------- LLM JSON


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.I | re.S)
_CODE_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.I | re.S)
_TRAILING_COMMA = re.compile(r",\s*([\]}])")


def extract_llm_json(text: str) -> JSONValue:
    """Pull a JSON value out of LLM output (think blocks, fences, chatter around it)."""
    original = text
    s = _THINK_BLOCK.sub("", text)
    close = s.lower().rfind("</think>")
    if close >= 0:
        s = s[close + len("</think>") :]
    m = _CODE_FENCE.search(s)
    if m:
        s = m.group(1)
    s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("[", "]"), ("{", "}")):
        i, j = s.find(opener), s.rfind(closer)
        if i < 0 or j <= i:
            continue
        sub = s[i : j + 1]
        for candidate in (sub, _TRAILING_COMMA.sub(r"\1", sub)):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    raise BBoxParseError(f"Could not find bounding-box JSON in the input: {original[:200]!r}")


# --------------------------------------------------------------------------- input parsing


def _has_bbox(item: object) -> bool:
    return isinstance(item, dict) and isinstance(item.get("bbox"), (list, tuple)) and len(item["bbox"]) == 4


def _has_xywh(item: object) -> bool:
    return isinstance(item, dict) and all(k in item for k in ("x", "y", "width", "height"))


def classify_input(value: object) -> tuple[str, list[dict[str, JSONValue]]]:
    """Return ("elements" | "pixels" | "none", items) for any accepted `bboxes` value."""
    if value is None:
        return "none", []
    if isinstance(value, str):
        if not value.strip():
            return "none", []
        value = extract_llm_json(value)
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, dict):
        for key in WRAPPER_KEYS:
            if isinstance(value.get(key), list):
                return classify_input(value[key])
        if _has_bbox(value):
            return "elements", [value]
        if _has_xywh(value):
            return "pixels", [value]
        raise BBoxParseError(f"Unrecognised bounding-box object with keys {sorted(value)[:12]}")
    if isinstance(value, list):
        if not value:
            return "none", []
        if isinstance(value[0], (list, tuple)):
            return classify_input(list(value[0]))
        if any(_has_bbox(item) for item in value):
            return "elements", [item for item in value if isinstance(item, dict)]
        if _has_xywh(value[0]):
            return "pixels", [item for item in value if isinstance(item, dict)]
        raise BBoxParseError("Unrecognised bounding-box list: items need a 4-value `bbox` or x/y/width/height")
    raise BBoxParseError(f"Unsupported bounding-box input type: {type(value).__name__}")


def element_meta(item: Mapping[str, object]) -> BoxMeta:
    kind = norm_kind(item.get("type") if item.get("type") is not None else item.get("label"))
    return {
        "type": kind,
        "text": _str(item.get("text")) if kind == "text" else "",
        "desc": _str(item.get("desc")) or _str(item.get("caption")),
        "palette": norm_palette(item.get("color_palette") or item.get("palette") or []),
    }


def element_grid(item: Mapping[str, object]) -> list[float] | None:
    bbox = item.get("bbox")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    vals = [_num(v) for v in bbox]
    if any(v is None for v in vals):
        return None
    return [min(1000.0, max(0.0, float(v))) for v in vals]  # type: ignore[arg-type]


def elements_to_pixels(items: Sequence[Mapping[str, object]], width: int, height: int) -> list[PixelBox]:
    out: list[PixelBox] = []
    for i, item in enumerate(items):
        grid = element_grid(item)
        if grid is None:
            print(f"{TAG} skipped element {i + 1}: invalid bbox {item.get('bbox')!r}")
            continue
        ymin, xmin, ymax, xmax = (v / 1000.0 for v in grid)
        out.append({
            "x": round(min(xmin, xmax) * width),
            "y": round(min(ymin, ymax) * height),
            "width": round(abs(xmax - xmin) * width),
            "height": round(abs(ymax - ymin) * height),
            "metadata": element_meta(item),
        })
    return out


def normalise_pixel_boxes(items: Sequence[Mapping[str, object]]) -> list[PixelBox]:
    out: list[PixelBox] = []
    for item in items:
        box: PixelBox = {
            "x": _intish(_num(item.get("x")) or 0.0),
            "y": _intish(_num(item.get("y")) or 0.0),
            "width": _intish(_num(item.get("width")) or 0.0),
            "height": _intish(_num(item.get("height")) or 0.0),
        }
        meta = item.get("metadata")
        if isinstance(meta, dict):
            box["metadata"] = meta  # type: ignore[typeddict-item]
        out.append(box)
    return out


def parse_bboxes_input(value: object, width: int, height: int) -> tuple[list[PixelBox], str]:
    """Parse the `bboxes` socket. Returns (pixel boxes, upstream key).

    The key identifies the upstream value independently of the canvas size, so resizing
    the canvas does not count as "upstream changed" (fix over the original).
    """
    kind, items = classify_input(value)
    if kind == "none":
        return [], ""
    if kind == "elements":
        boxes = elements_to_pixels(items, width, height)
        canon: list[JSONValue] = [
            {"bbox": element_grid(it), **element_meta(it)} for it in items if element_grid(it) is not None  # type: ignore[dict-item]
        ]
    else:
        boxes = normalise_pixel_boxes(items)
        canon = boxes  # type: ignore[assignment]
    if not boxes:
        return [], ""
    return boxes, json.dumps({"kind": kind, "items": canon}, sort_keys=True, separators=(",", ":"))


# --------------------------------------------------------------------------- regions


def pixel_boxes_to_regions(boxes: Sequence[PixelBox], width: int, height: int) -> list[Region]:
    out: list[Region] = []
    w = max(1, width)
    h = max(1, height)
    for box in boxes:
        x, y, bw, bh = float(box["x"]), float(box["y"]), float(box["width"]), float(box["height"])
        if bw < 0:
            x, bw = x + bw, -bw
        if bh < 0:
            y, bh = y + bh, -bh
        meta = box.get("metadata") or {}
        kind = norm_kind(meta.get("type"))
        out.append({
            "x": x / w, "y": y / h, "w": bw / w, "h": bh / h,
            "type": kind,
            "text": _str(meta.get("text")) if kind == "text" else "",
            "desc": _str(meta.get("desc")),
            "palette": norm_palette(meta.get("palette")),
        })
    return out


def regions_from_state(state: object) -> list[Region]:
    """Parse `editor_state` (JSON string, `{regions: [...]}` or a bare list)."""
    if isinstance(state, str):
        if not state.strip():
            return []
        try:
            state = json.loads(state)
        except json.JSONDecodeError:
            print(f"{TAG} editor_state is not valid JSON; starting empty")
            return []
    if isinstance(state, dict):
        state = state.get("regions")
    if not isinstance(state, list):
        return []
    out: list[Region] = []
    for r in state:
        if not isinstance(r, dict):
            continue
        vals = [_num(r.get(k)) for k in ("x", "y", "w", "h")]
        if any(v is None for v in vals):
            continue
        x, y, w, h = (float(v) for v in vals)  # type: ignore[arg-type]
        kind = norm_kind(r.get("type"))
        out.append({
            "x": x, "y": y, "w": w, "h": h, "type": kind,
            "text": _str(r.get("text")), "desc": _str(r.get("desc")),
            "palette": norm_palette(r.get("palette")),
        })
    return out


def _normalised(r: Region) -> tuple[float, float, float, float]:
    x, y, w, h = r["x"], r["y"], r["w"], r["h"]
    if w < 0:
        x, w = x + w, -w
    if h < 0:
        y, h = y + h, -h
    return x, y, w, h


def regions_to_frames(regions: Sequence[Region], width: int, height: int) -> list[list[dict[str, int]]]:
    if not regions:
        return []
    frame: list[dict[str, int]] = []
    for r in regions:
        x, y, w, h = _normalised(r)
        frame.append({"x": round(x * width), "y": round(y * height),
                      "width": round(w * width), "height": round(h * height)})
    return [frame]


def _grid(v: float) -> int:
    return max(0, min(1000, round(v * 1000)))


def regions_to_elements(regions: Sequence[Region]) -> list[Element]:
    out: list[Element] = []
    for r in regions:
        ymin, xmin = _grid(r["y"]), _grid(r["x"])
        ymax, xmax = _grid(r["y"] + r["h"]), _grid(r["x"] + r["w"])
        if ymin > ymax:
            ymin, ymax = ymax, ymin
        if xmin > xmax:
            xmin, xmax = xmax, xmin
        el: Element = {"type": r["type"], "bbox": [ymin, xmin, ymax, xmax]}
        if r["type"] == "text":
            el["text"] = r["text"]
        el["desc"] = r["desc"]
        palette = norm_palette(r["palette"])
        if palette:
            el["color_palette"] = palette
        out.append(el)
    return out


# --------------------------------------------------------------------------- preview


def hex_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def luma(c: tuple[int, int, int]) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def readable(c: tuple[int, int, int], target: float = 130.0) -> tuple[int, int, int]:
    lum = luma(c)
    if lum >= target:
        return c
    t = (target - lum) / max(1e-6, 255.0 - lum)
    return tuple(round(ch + (255 - ch) * t) for ch in c)  # type: ignore[return-value]


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except (TypeError, AttributeError, OSError):
        return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont | ImageFont.FreeTypeFont) -> float:
    return float(draw.textlength(text, font=font))


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
          max_w: float) -> list[str]:
    lines: list[str] = []
    for para in text.splitlines() or [""]:
        words = para.split()
        line = ""
        for word in words:
            trial = f"{line} {word}".strip()
            if not line or _text_width(draw, trial, font) <= max_w:
                line = trial
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
    return lines


def preview_canvas(width: int, height: int, background: Image.Image | None) -> Image.Image:
    if background is not None:
        img = background.convert("RGB")
        scale = min(1.0, PREVIEW_LONG_EDGE / max(img.size))
        if scale < 1.0:
            img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
        return ImageEnhance.Brightness(img).enhance(0.25)
    scale = min(1.0, PREVIEW_LONG_EDGE / max(1, width, height))
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    v = round(0.25 * 128)
    return Image.new("RGB", size, (v, v, v))


def render_preview(regions: Sequence[Region], width: int, height: int,
                   background: Image.Image | None = None) -> Image.Image:
    img = preview_canvas(width, height, background)
    cw, ch = img.size
    draw = ImageDraw.Draw(img)
    fs = max(10, round(ch / 64))
    font = _font(fs)
    tag_font = _font(max(9, fs - 2))
    for i, r in enumerate(regions):
        x, y, w, h = _normalised(r)
        x0 = max(0, min(cw - 1, round(x * cw)))
        y0 = max(0, min(ch - 1, round(y * ch)))
        x1 = max(0, min(cw - 1, round((x + w) * cw)))
        y1 = max(0, min(ch - 1, round((y + h) * ch)))
        if x1 <= x0 or y1 <= y0:
            continue
        palette = norm_palette(r["palette"])
        color = hex_rgb(palette[0]) if palette else GREY
        draw.rectangle([x0, y0, x1, y1], outline=color, width=2)
        if palette:
            strip_h = max(3, fs // 3)
            seg = (x1 - x0) / len(palette)
            for j, p in enumerate(palette):
                draw.rectangle([round(x0 + j * seg), y0, round(x0 + (j + 1) * seg), y0 + strip_h], fill=hex_rgb(p))
        tag = f"{i + 1:02d}"
        tw = _text_width(draw, tag, tag_font)
        tag_h = max(9, fs - 2) + 4
        draw.rectangle([x0, y0, x0 + tw + 6, y0 + tag_h], fill=color)
        draw.text((x0 + 3, y0 + 1), tag, fill=(0, 0, 0) if luma(color) > 140 else (255, 255, 255), font=tag_font)
        body = r["desc"]
        if r["type"] == "text":
            body = f"“{r['text']}” — {r['desc']}" if r["desc"] else f"“{r['text']}”"
        if not body.strip():
            continue
        ty = y0 + tag_h + 4
        line_h = fs + 3
        fill = readable(color)
        for line in _wrap(draw, body, font, max(8, x1 - x0 - 8)):
            if ty + line_h > y1:
                break
            draw.text((x0 + 4, ty), line, fill=fill, font=font)
            ty += line_h
    return img


# --------------------------------------------------------------------------- node


class JWTFBoundingBoxes(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFBoundingBoxes",
            display_name='Bounding Boxes',
            category='JezzWTF/LLM',
            inputs=[
                io.Int.Input("width", default=1024, min=64, max=16384, step=16),
                io.Int.Input("height", default=1024, min=64, max=16384, step=16),
                io.Image.Input("background", optional=True),
                io.Custom("BOUNDING_BOX,ARRAY,STRING").Input("bboxes", optional=True),
                io.String.Input("editor_state", default='', optional=True),
                io.String.Input("last_incoming", default='', optional=True),
            ],
            outputs=[
                io.Image.Output("preview"),
                io.Custom("BOUNDING_BOX").Output("bboxes"),
                io.Custom("ARRAY").Output("elements"),
            ],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, width: int, height: int, background: object = None, bboxes: object = None,
            editor_state: str = "", last_incoming: str = "") -> io.NodeOutput:
        width, height = int(width), int(height)
        incoming, key = parse_bboxes_input(bboxes, width, height)
        if incoming and key != (last_incoming or ""):
            regions = pixel_boxes_to_regions(incoming, width, height)
        else:
            regions = regions_from_state(editor_state)

        bg_img: Image.Image | None = None
        if background is not None and len(getattr(background, "shape", ())) == 4:
            bg_img = frame_to_pil(background[0])  # type: ignore[index]
        preview = render_preview(regions, width, height, bg_img)

        ui: dict[str, list[object]] = {"dims": [width, height]}
        if incoming:
            ui["input_bboxes"] = list(incoming)
            ui["input_key"] = [key]
        if background is not None:
            try:
                import nodes as comfy_nodes  # type: ignore[import-not-found]

                saved = comfy_nodes.PreviewImage().save_images(background[0:1], "jezzwtf.bboxes.background")  # type: ignore[index]
                ui["background_images"] = list(saved.get("ui", {}).get("images", []))
            except Exception as exc:  # noqa: BLE001 - preview only
                print(f"{TAG} could not save the background preview: {exc}")
        return io.NodeOutput(pil_to_tensor(preview), regions_to_frames(regions, width, height), regions_to_elements(regions), ui=ui)


NODES = [JWTFBoundingBoxes]
