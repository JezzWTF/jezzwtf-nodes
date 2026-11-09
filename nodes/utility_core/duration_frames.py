"""Duration -> Frames: turn seconds into a frame count via a preset or an expression."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, TypedDict

from comfy_api.latest import io

from ._comfy import read_json_object
from .expr_eval import ExprError, to_frames

if TYPE_CHECKING:
    from aiohttp import web

MINIMAX_EXPR = "max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17"
FPS_EXPR = "max(1, round(a * fps))"
CUSTOM = "Custom"
PRESETS: dict[str, tuple[int, str]] = {
    "MiniMax H3 (24 FPS)": (24, MINIMAX_EXPR),
    "24 FPS": (24, FPS_EXPR),
    "30 FPS": (30, FPS_EXPR),
}
PRESET_NAMES = (*PRESETS, CUSTOM)
UI_KEY = "jezzwtf_duration_frames"
MAX_EVAL_VALUES = 40


def resolve(preset: str, expression: str, fps: int) -> tuple[int, str]:
    """A non-Custom preset always wins over the widgets."""
    if preset in PRESETS:
        return PRESETS[preset]
    return max(1, int(fps)), expression


class Row(TypedDict, total=False):
    a: float | str | None
    frames: int
    seconds: float
    error: str


def _echo(raw: object) -> float | int | str | None:
    """The input as it can go back through strict JSON (no inf/nan, no giant ints)."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return None
    if isinstance(raw, float) and not math.isfinite(raw):
        return str(raw)
    if isinstance(raw, int) and raw.bit_length() > 53:
        return str(raw)
    return raw


def eval_rows(preset: str, expression: str, fps: int, values: list[object]) -> tuple[int, str, list[Row]]:
    fps_used, expr = resolve(preset, expression, fps)
    rows: list[Row] = []
    for raw in values[:MAX_EVAL_VALUES]:
        try:
            if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
                raise ExprError("not a number")
            a = float(raw)
            frames = to_frames(expr, a, fps_used)
            rows.append({"a": a, "frames": frames, "seconds": frames / fps_used})
        except (ExprError, ValueError, OverflowError) as exc:
            rows.append({"a": _echo(raw), "error": str(exc)})
    return fps_used, expr, rows


class JWTFDurationFrames(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFDurationFrames",
            display_name='Duration to Frames',
            category='JezzWTF/utils',
            inputs=[
                io.Float.Input("duration", default=6.0, min=0.0, max=3600.0, step=0.1, round=0.001),
                io.Combo.Input("preset", options=list(PRESET_NAMES), default='MiniMax H3 (24 FPS)'),
                io.String.Input("expression", default='max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17', multiline=True),
                io.Int.Input("fps", default=24, min=1, max=240),
            ],
            outputs=[
                io.Int.Output("frames"),
                io.Float.Output("seconds"),
                io.Float.Output("fps"),
                io.Int.Output("fps_int"),
            ],
        )

    @classmethod
    def execute(cls, duration: float, preset: str, expression: str, fps: int) -> io.NodeOutput:
        fps_used, expr = resolve(preset, expression, fps)
        try:
            frames = to_frames(expr, float(duration), fps_used)
        except ExprError as exc:
            raise ValueError(f"Duration -> Frames: {exc} (expression: {expr})") from None
        seconds = frames / fps_used
        info = {"duration": duration, "frames": frames, "seconds": seconds, "fps": fps_used, "expression": expr}
        return io.NodeOutput(frames, seconds, float(fps_used), fps_used, ui={UI_KEY: [info]})


def register_routes(routes: "web.RouteTableDef") -> None:
    import asyncio

    from aiohttp import web

    @routes.get("/jezzwtf/duration_frames/presets")
    async def _presets(_request: web.Request) -> web.Response:
        return web.json_response({k: {"fps": f, "expression": e} for k, (f, e) in PRESETS.items()})

    @routes.post("/jezzwtf/duration_frames/eval")
    async def _eval(request: web.Request) -> web.Response:
        body = await read_json_object(request)
        if body is None:
            return web.json_response({"error": "bad request"}, status=400)
        raw_values = body.get("values")
        values: list[object] = list(raw_values) if isinstance(raw_values, list) else []
        try:
            fps = int(body.get("fps", 24))  # type: ignore[call-overload]
        except (TypeError, ValueError, OverflowError):
            fps = 24
        try:
            fps_used, expr, rows = await asyncio.to_thread(
                eval_rows, str(body.get("preset", CUSTOM)), str(body.get("expression", "")), fps, values)
        except (ExprError, ValueError, OverflowError, RecursionError, MemoryError):
            return web.json_response({"error": "evaluation failed"}, status=400)
        return web.json_response({"fps": fps_used, "expression": expr, "rows": rows})


NODES = [JWTFDurationFrames]
