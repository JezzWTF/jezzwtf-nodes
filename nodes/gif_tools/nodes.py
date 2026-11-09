"""ComfyUI node classes for the GIF tools family. Heavy lifting lives in the pure modules next to this file."""
from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import replace
from fractions import Fraction

import numpy as np
import torch
from numpy.typing import NDArray

from comfy_api.latest import io

from .animated import FORMATS, AnimResult, encode_animated
from .frames import Clip, Frame, FrameSource, PrepOptions, make_clip, source_from_arrays, source_from_timed_arrays, source_from_video_file
from .gifio import read_gif
from .optimise import OptimiseRequest, OptimiseResult, optimise
from .output import reserve_output_path, resolve_existing_file
from .quality import compare_sequences
from .runtime import Progress, check_interrupt
from .settings import (DELAY_MODES, DENOISE, DITHERS, MODES, PALETTES, RESIZE_FILTERS, check_choice, check_colors, check_float,
                       check_int)
from .timing import MAX_FPS, fps_notes, resolve_fps

try:
    from ..utility_core._comfy import input_dir, temp_dir
except ImportError:  # imported as a top-level package (tests)
    from utility_core._comfy import input_dir, temp_dir  # type: ignore[no-redef]

CATEGORY = "JezzWTF/gif"
MAX_PREVIEW_FRAMES = 240
UIResult = dict[str, object]


def output_dir() -> str:
    try:
        import folder_paths  # type: ignore[import-not-found]

        return str(folder_paths.get_output_directory())
    except Exception:
        import tempfile

        path = os.path.join(tempfile.gettempdir(), "jezzwtf_output")
        os.makedirs(path, exist_ok=True)
        return path


def read_roots() -> list[str]:
    return [input_dir(), output_dir(), temp_dir()]


# ------------------------------------------------------------------ conversions

def tensor_to_frames(images: torch.Tensor) -> list[Frame]:
    if images.ndim == 3:
        images = images[None]
    if images.ndim != 4:
        raise ValueError(f"expected an IMAGE batch (N,H,W,C); got shape {tuple(images.shape)}")
    out: list[Frame] = []
    for start in range(0, images.shape[0], 32):
        chunk = (images[start : start + 32].detach().float().clamp(0, 1) * 255.0 + 0.5).to(torch.uint8).cpu().numpy()
        if chunk.shape[-1] == 1:
            chunk = np.repeat(chunk, 3, axis=-1)
        out.extend(np.ascontiguousarray(c[..., :3]) for c in chunk)
    return out


def frames_to_tensor(frames: Sequence[Frame]) -> torch.Tensor:
    return torch.from_numpy(np.stack(frames)).to(torch.float32) / 255.0


def preview_tensor(frames: list[Frame]) -> tuple[torch.Tensor, bool]:
    if len(frames) <= MAX_PREVIEW_FRAMES:
        return frames_to_tensor(frames), False
    idx = np.linspace(0, len(frames) - 1, MAX_PREVIEW_FRAMES).astype(int)
    return frames_to_tensor([frames[i] for i in idx]), True


def video_source(video: object) -> FrameSource:
    """Frames of a core VIDEO value: stream the file when it has one, otherwise take decoded components."""
    cropped = getattr(video, "_VideoFromFile__crop", None) is not None
    source: object = None
    try:
        source = video.get_stream_source()  # type: ignore[attr-defined]
    except Exception:
        source = None
    if isinstance(source, str) and os.path.isfile(source) and not cropped:
        window = (0.0, 0.0)
        getter = getattr(video, "get_active_trim_window", None)
        if callable(getter):
            try:
                start, length = getter()
                window = (float(start), float(length))
            except Exception:
                window = (0.0, 0.0)
        return source_from_video_file(source, window)
    comps = video.get_components()  # type: ignore[attr-defined]
    rate = getattr(comps, "frame_rate", Fraction(24))
    return source_from_arrays(tensor_to_frames(getattr(comps, "images")), float(rate))


def gif_source(path: str) -> tuple[FrameSource, list[str], int]:
    g = read_gif(path)
    return source_from_timed_arrays(g.frames, g.durations), g.notes, g.loop


# Leading picker entry for GIF Optimise: ComfyUI validates the picker value even when it is greyed out,
# so a workflow that feeds a path needs a value that is valid on every machine.
USE_PATH = "(use path input)"


def list_input_gifs() -> list[str]:
    try:
        names = sorted(n for n in os.listdir(input_dir()) if n.lower().endswith(".gif") and os.path.isfile(os.path.join(input_dir(), n)))
    except OSError:
        names = []
    return names or [""]


def loop_value(loop_count: int) -> int:
    """UI semantics (0 = forever, 1 = play once, n = n plays) -> NETSCAPE value (-1 none, 0 forever, n-1 repeats)."""
    return 0 if loop_count == 0 else loop_count - 1 if loop_count > 1 else -1


# ------------------------------------------------------------------ shared widgets

def _optimise_widgets() -> dict[str, tuple[object, ...]]:
    return {
        "trim_start": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 36000.0, "step": 0.05, "tooltip": "Seconds cut from the start (source time)."}),
        "trim_end": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 36000.0, "step": 0.05, "tooltip": "Seconds where the clip stops (0 = to the end)."}),
        "speed": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 10.0, "step": 0.05}),
        "max_width": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1, "tooltip": "0 = no limit. Never upscales."}),
        "max_height": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1}),
        "resize_filter": (list(RESIZE_FILTERS), {"default": "lanczos"}),
        "crop_left": ("INT", {"default": 0, "min": 0, "max": 8192}),
        "crop_top": ("INT", {"default": 0, "min": 0, "max": 8192}),
        "crop_right": ("INT", {"default": 0, "min": 0, "max": 8192}),
        "crop_bottom": ("INT", {"default": 0, "min": 0, "max": 8192}),
        "loop_count": ("INT", {"default": 0, "min": 0, "max": 65535, "tooltip": "0 = forever, 1 = play once, n = play n times."}),
        "colors": ("INT", {"default": 0, "min": 0, "max": 256, "tooltip": "0 = by mode, otherwise 16-256."}),
        "palette": (list(PALETTES), {"default": "auto"}),
        "dither": (list(DITHERS), {"default": "auto"}),
        "dedupe_threshold": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 20.0, "step": 0.05,
                                       "tooltip": "-1 = by mode, 0 = exact duplicates only, else mean pixel difference (0-255) under which a frame merges into the previous one."}),
        "transparency_opt": ("BOOLEAN", {"default": True, "tooltip": "Store only the changed rectangle of each frame."}),
        "denoise": (list(DENOISE), {"default": "auto"}),
        "delay_mode": (list(DELAY_MODES), {"default": "exact", "tooltip": "exact keeps real-time speed with mixed 10 ms steps; even snaps fps to a whole 10 ms period."}),
        "target_size_mb": ("FLOAT", {"default": 2.0, "min": 0.05, "max": 512.0, "step": 0.05, "tooltip": "Used by target_size mode."}),
        "max_trials": ("INT", {"default": 10, "min": 2, "max": 40, "tooltip": "Encode attempts the target_size search may spend."}),
        "time_budget_s": ("FLOAT", {"default": 120.0, "min": 5.0, "max": 3600.0, "step": 5.0}),
        "compare_naive": ("BOOLEAN", {"default": True, "tooltip": "Also encode a naive one-liner GIF to report the saving."}),
    }


def _validated(values: dict[str, object]) -> tuple[PrepOptions, OptimiseRequest, str]:
    """Check every numeric/enum input once, returning engine settings and the requested delay mode."""
    mode = check_choice("mode", values["mode"], MODES)
    delay_mode = check_choice("delay_mode", values["delay_mode"], DELAY_MODES)
    crop = tuple(check_int(k, values[k], 0, 8192) for k in ("crop_left", "crop_top", "crop_right", "crop_bottom"))
    prep = PrepOptions(
        start=check_float("trim_start", values["trim_start"], 0.0, 36000.0),
        end=check_float("trim_end", values["trim_end"], 0.0, 36000.0),
        fps=check_float("fps", values["fps"], 0.0, 1000.0),
        speed=check_float("speed", values["speed"], 0.1, 10.0),
        max_width=check_int("max_width", values["max_width"], 0, 8192),
        max_height=check_int("max_height", values["max_height"], 0, 8192),
        resize_filter=check_choice("resize_filter", values["resize_filter"], RESIZE_FILTERS),
        crop=(crop[0], crop[1], crop[2], crop[3]),
    )
    req = OptimiseRequest(
        mode=mode,
        palette=check_choice("palette", values["palette"], PALETTES),
        colors=check_colors(values["colors"]),
        dither=check_choice("dither", values["dither"], DITHERS),
        dedupe_threshold=check_float("dedupe_threshold", values["dedupe_threshold"], -1.0, 20.0),
        transparency_opt=bool(values["transparency_opt"]),
        denoise=check_choice("denoise", values["denoise"], DENOISE),
        loop=loop_value(check_int("loop_count", values["loop_count"], 0, 65535)),
        target_size_mb=check_float("target_size_mb", values["target_size_mb"], 0.05, 512.0),
        max_trials=check_int("max_trials", values["max_trials"], 2, 40),
        time_budget_s=check_float("time_budget_s", values["time_budget_s"], 5.0, 3600.0),
        compare_naive=bool(values["compare_naive"]),
    )
    return prep, req, delay_mode


def save_bytes(data: bytes, prefix: str, ext: str) -> tuple[str, str, str]:
    path, subfolder, filename = reserve_output_path(output_dir(), prefix, ext)
    try:
        with open(path, "wb") as fh:
            fh.write(data)
    except BaseException:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    return path, subfolder, filename


def _ui(subfolder: str, filename: str, stats: dict[str, float | int | str | bool | None], mode: str = "") -> dict[str, list[object]]:
    return {"jwtf_gif": [{"filename": filename, "subfolder": subfolder, "type": "output", "stats": stats, "mode": mode}]}


def _run_optimise(source: FrameSource, values: dict[str, object], native_notes: list[str], prefix: str) -> tuple[OptimiseResult, str, str, str, list[str]]:
    prep, req, delay_mode = _validated(values)
    notes = list(native_notes)
    fps = prep.fps
    if fps == 0 and source.native_fps > MAX_FPS:
        notes.append(f"source runs at {source.native_fps:.1f} fps; GIF tops out at 50 fps, so frames are resampled to 50")
        fps = MAX_FPS
    if fps > 0:
        notes.extend(fps_notes(fps, delay_mode))
        fps = resolve_fps(fps, delay_mode)
    elif source.native_fps > 0 and (len(source.starts) > 1):
        notes.extend(fps_notes(source.native_fps, delay_mode))
    prep = replace(prep, fps=fps)
    progress = Progress(req.max_trials + 2)
    clip = make_clip(source, prep, check_interrupt)
    result = optimise(clip, req, progress.update_to, check_interrupt)
    result.warnings[:0] = notes
    path, subfolder, filename = save_bytes(result.data, prefix, "gif")
    return result, path, subfolder, filename, notes


def _finish_gif(result: OptimiseResult, path: str, subfolder: str, filename: str, mode: str) -> io.NodeOutput:
    from .encoder import decode_result

    frames, _ = decode_result(result.encode)
    tensor, sampled = preview_tensor(frames)
    report = result.report()
    report += f"\nsaved: output/{subfolder + '/' if subfolder else ''}{filename}"
    if sampled:
        report += f"\nnote: preview output holds {MAX_PREVIEW_FRAMES} evenly spaced frames of {len(frames)}"
    return io.NodeOutput(path, tensor, report, ui=_ui(subfolder, filename, result.stats(), mode))


# ------------------------------------------------------------------ nodes

class JWTFVideoToGif(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFVideoToGif",
            display_name='Video to GIF (Optimised)',
            category='JezzWTF/gif',
            inputs=[
                io.Combo.Input("mode", options=list(MODES), default='balanced'),
                io.String.Input("filename_prefix", default='gifs/clip', tooltip='Relative to the output folder. Put a subfolder in the prefix, e.g. gifs/clip saves to output/gifs/clip_00001.gif.'),
                io.Image.Input("images", optional=True),
                io.Video.Input("video", optional=True),
                io.Float.Input("source_fps", default=24.0, min=0.1, max=1000.0, step=0.1, optional=True, tooltip='Frame rate of the IMAGE batch (ignored for VIDEO).'),
                io.Float.Input("fps", default=20.0, min=0.0, max=1000.0, step=0.5, optional=True, tooltip='Output frame rate; 0 = keep the source rate (capped at 50). 25, 20 and 12.5 give an even GIF cadence.'),
                io.Float.Input("trim_start", default=0.0, min=0.0, max=36000.0, step=0.05, optional=True, tooltip='Seconds cut from the start (source time).'),
                io.Float.Input("trim_end", default=0.0, min=0.0, max=36000.0, step=0.05, optional=True, tooltip='Seconds where the clip stops (0 = to the end).'),
                io.Float.Input("speed", default=1.0, min=0.1, max=10.0, step=0.05, optional=True),
                io.Int.Input("max_width", default=0, min=0, max=8192, step=1, optional=True, tooltip='0 = no limit. Never upscales.'),
                io.Int.Input("max_height", default=0, min=0, max=8192, step=1, optional=True),
                io.Combo.Input("resize_filter", options=['lanczos', 'bicubic', 'bilinear', 'box', 'nearest'], default='lanczos', optional=True),
                io.Int.Input("crop_left", default=0, min=0, max=8192, optional=True),
                io.Int.Input("crop_top", default=0, min=0, max=8192, optional=True),
                io.Int.Input("crop_right", default=0, min=0, max=8192, optional=True),
                io.Int.Input("crop_bottom", default=0, min=0, max=8192, optional=True),
                io.Int.Input("loop_count", default=0, min=0, max=65535, optional=True, tooltip='0 = forever, 1 = play once, n = play n times.'),
                io.Int.Input("colors", default=0, min=0, max=256, optional=True, tooltip='0 = by mode, otherwise 16-256.'),
                io.Combo.Input("palette", options=['auto', 'global_full', 'global_diff', 'per_frame'], default='auto', optional=True),
                io.Combo.Input("dither", options=['auto', 'none', 'bayer_1', 'bayer_2', 'bayer_3', 'bayer_4', 'bayer_5', 'sierra2_4a', 'floyd_steinberg'], default='auto', optional=True),
                io.Float.Input("dedupe_threshold", default=-1.0, min=-1.0, max=20.0, step=0.05, optional=True, tooltip='-1 = by mode, 0 = exact duplicates only, else mean pixel difference (0-255) under which a frame merges into the previous one.'),
                io.Boolean.Input("transparency_opt", default=True, optional=True, tooltip='Store only the changed rectangle of each frame.'),
                io.Combo.Input("denoise", options=['auto', 'off', 'light', 'strong'], default='auto', optional=True),
                io.Combo.Input("delay_mode", options=['exact', 'even'], default='exact', optional=True, tooltip='exact keeps real-time speed with mixed 10 ms steps; even snaps fps to a whole 10 ms period.'),
                io.Float.Input("target_size_mb", default=2.0, min=0.05, max=512.0, step=0.05, optional=True, tooltip='Used by target_size mode.'),
                io.Int.Input("max_trials", default=10, min=2, max=40, optional=True, tooltip='Encode attempts the target_size search may spend.'),
                io.Float.Input("time_budget_s", default=120.0, min=5.0, max=3600.0, step=5.0, optional=True),
                io.Boolean.Input("compare_naive", default=True, optional=True, tooltip='Also encode a naive one-liner GIF to report the saving.'),
            ],
            outputs=[
                io.String.Output("gif_path"),
                io.Image.Output("preview"),
                io.String.Output("report"),
            ],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, mode: str, filename_prefix: str, images: torch.Tensor | None = None, video: object | None = None, source_fps: float = 24.0,
            **kwargs: object) -> io.NodeOutput:
        warnings: list[str] = []
        if images is not None:
            if video is not None:
                warnings.append("both images and video were connected; the IMAGE batch was used")
            rate = check_float("source_fps", source_fps, 0.1, 1000.0)
            source = source_from_arrays(tensor_to_frames(images), rate)
        elif video is not None:
            source = video_source(video)
        else:
            raise ValueError("connect an IMAGE batch or a VIDEO")
        values: dict[str, object] = {"mode": mode, **kwargs}
        result, path, subfolder, filename, _ = _run_optimise(source, _defaults(values), warnings, filename_prefix)
        return _finish_gif(result, path, subfolder, filename, mode)


class JWTFGifOptimise(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFGifOptimise",
            display_name='GIF Optimise',
            category='JezzWTF/gif',
            inputs=[
                io.Combo.Input("gif", options=[USE_PATH, *list_input_gifs()], upload=io.UploadType.image),
                io.Combo.Input("mode", options=list(MODES), default='balanced'),
                io.String.Input("filename_prefix", default='gifs/optimised', tooltip='Relative to the output folder. Put a subfolder in the prefix, e.g. gifs/optimised saves to output/gifs/optimised_00001.gif.'),
                io.String.Input("path", default='', optional=True, tooltip='Optional GIF path (inside input, output or temp). Overrides the picker, e.g. the output of another GIF node.'),
                io.Float.Input("fps", default=0.0, min=0.0, max=1000.0, step=0.5, optional=True, tooltip="0 = keep the GIF's own frame timing."),
                io.Float.Input("trim_start", default=0.0, min=0.0, max=36000.0, step=0.05, optional=True, tooltip='Seconds cut from the start (source time).'),
                io.Float.Input("trim_end", default=0.0, min=0.0, max=36000.0, step=0.05, optional=True, tooltip='Seconds where the clip stops (0 = to the end).'),
                io.Float.Input("speed", default=1.0, min=0.1, max=10.0, step=0.05, optional=True),
                io.Int.Input("max_width", default=0, min=0, max=8192, step=1, optional=True, tooltip='0 = no limit. Never upscales.'),
                io.Int.Input("max_height", default=0, min=0, max=8192, step=1, optional=True),
                io.Combo.Input("resize_filter", options=['lanczos', 'bicubic', 'bilinear', 'box', 'nearest'], default='lanczos', optional=True),
                io.Int.Input("crop_left", default=0, min=0, max=8192, optional=True),
                io.Int.Input("crop_top", default=0, min=0, max=8192, optional=True),
                io.Int.Input("crop_right", default=0, min=0, max=8192, optional=True),
                io.Int.Input("crop_bottom", default=0, min=0, max=8192, optional=True),
                io.Int.Input("loop_count", default=0, min=0, max=65535, optional=True, tooltip='0 = forever, 1 = play once, n = play n times.'),
                io.Int.Input("colors", default=0, min=0, max=256, optional=True, tooltip='0 = by mode, otherwise 16-256.'),
                io.Combo.Input("palette", options=['auto', 'global_full', 'global_diff', 'per_frame'], default='auto', optional=True),
                io.Combo.Input("dither", options=['auto', 'none', 'bayer_1', 'bayer_2', 'bayer_3', 'bayer_4', 'bayer_5', 'sierra2_4a', 'floyd_steinberg'], default='auto', optional=True),
                io.Float.Input("dedupe_threshold", default=-1.0, min=-1.0, max=20.0, step=0.05, optional=True, tooltip='-1 = by mode, 0 = exact duplicates only, else mean pixel difference (0-255) under which a frame merges into the previous one.'),
                io.Boolean.Input("transparency_opt", default=True, optional=True, tooltip='Store only the changed rectangle of each frame.'),
                io.Combo.Input("denoise", options=['auto', 'off', 'light', 'strong'], default='auto', optional=True),
                io.Combo.Input("delay_mode", options=['exact', 'even'], default='exact', optional=True, tooltip='exact keeps real-time speed with mixed 10 ms steps; even snaps fps to a whole 10 ms period.'),
                io.Float.Input("target_size_mb", default=2.0, min=0.05, max=512.0, step=0.05, optional=True, tooltip='Used by target_size mode.'),
                io.Int.Input("max_trials", default=10, min=2, max=40, optional=True, tooltip='Encode attempts the target_size search may spend.'),
                io.Float.Input("time_budget_s", default=120.0, min=5.0, max=3600.0, step=5.0, optional=True),
                io.Boolean.Input("compare_naive", default=True, optional=True, tooltip='Also encode a naive one-liner GIF to report the saving.'),
            ],
            outputs=[
                io.String.Output("gif_path"),
                io.Image.Output("preview"),
                io.String.Output("report"),
            ],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, gif: str = "", path: str = "", **_: object) -> str:
        try:
            real = resolve_existing_file(path or gif, read_roots())
            st = os.stat(real)
            return f"{real}:{st.st_mtime_ns}:{st.st_size}"
        except (ValueError, OSError):
            return "missing"

    @classmethod
    def execute(cls, gif: str, mode: str, filename_prefix: str, path: str = "", **kwargs: object) -> io.NodeOutput:
        chosen = path.strip() or ("" if gif == USE_PATH else gif)
        if not chosen:
            raise ValueError("GIF Optimise: pick a GIF, or connect a path (for example from Load GIF).")
        real = resolve_existing_file(chosen, read_roots())
        source, notes, _ = gif_source(real)
        values: dict[str, object] = {"mode": mode, **kwargs}
        result, out_path, subfolder, filename, _ = _run_optimise(source, _defaults(values), notes, filename_prefix)
        original = os.path.getsize(real)
        result.notes.append(f"source GIF {original:,} bytes -> {len(result.data):,} bytes ({(1 - len(result.data) / original) * 100:.1f}% saved)")
        return _finish_gif(result, out_path, subfolder, filename, mode)


def _defaults(values: dict[str, object]) -> dict[str, object]:
    """Fill any widget the caller (or an older saved workflow) left out with its declared default."""
    out: dict[str, object] = {"fps": 0.0}
    for name, spec in _optimise_widgets().items():
        cfg = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
        out[name] = cfg.get("default", spec[0][0] if isinstance(spec[0], list) else None)
    out.update(values)
    return out


class JWTFGifCompare(io.ComfyNode):
    LAYOUTS = ("side_by_side", "split", "difference")

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFGifCompare",
            display_name='GIF Analyse / Compare',
            category='JezzWTF/gif',
            description="Compare two GIFs or image batches: sizes, frame counts, SSIM and PSNR, with side-by-side, split or difference output.",
            inputs=[
                io.Combo.Input("layout", options=list(cls.LAYOUTS), default='side_by_side'),
                io.String.Input("gif_a", default='', optional=True, tooltip='Reference GIF path (input, output or temp folder). Relative names resolve under input.'),
                io.String.Input("gif_b", default='', optional=True, tooltip='GIF to judge against A, e.g. an optimised result.'),
                io.Image.Input("images_a", optional=True),
                io.Image.Input("images_b", optional=True),
                io.Float.Input("fps_a", default=20.0, min=0.1, max=1000.0, step=0.1, optional=True, tooltip='Rate of images_a.'),
                io.Float.Input("fps_b", default=20.0, min=0.1, max=1000.0, step=0.1, optional=True, tooltip='Rate of images_b.'),
                io.Int.Input("sample_frames", default=24, min=1, max=400, optional=True, tooltip='Frames of A measured for SSIM/PSNR (evenly spread).'),
                io.Int.Input("output_frames", default=60, min=1, max=400, optional=True, tooltip='Frames in the comparison image batch.'),
            ],
            outputs=[
                io.Image.Output("compare"),
                io.String.Output("report"),
            ],
            is_output_node=True,
        )

    @staticmethod
    def _load(path: str, images: torch.Tensor | None, fps: float, label: str) -> tuple[list[Frame], list[float], int | None]:
        if images is not None:
            return tensor_to_frames(images), [1.0 / fps] * int(images.shape[0]), None
        if not path.strip():
            raise ValueError(f"give {label} as a GIF path or an IMAGE batch")
        real = resolve_existing_file(path, read_roots())
        g = read_gif(real)
        return g.frames, g.durations, os.path.getsize(real)

    @classmethod
    def execute(cls, layout: str, gif_a: str = "", gif_b: str = "", images_a: torch.Tensor | None = None, images_b: torch.Tensor | None = None,
            fps_a: float = 20.0, fps_b: float = 20.0, sample_frames: int = 24, output_frames: int = 60) -> io.NodeOutput:
        from .frames import resize_frame
        from .quality import align

        check_choice("layout", layout, cls.LAYOUTS)
        n_sample = check_int("sample_frames", sample_frames, 1, 400)
        n_out = check_int("output_frames", output_frames, 1, 400)
        a_frames, a_durs, a_bytes = cls._load(gif_a, images_a, check_float("fps_a", fps_a, 0.1, 1000.0), "A")
        b_frames, b_durs, b_bytes = cls._load(gif_b, images_b, check_float("fps_b", fps_b, 0.1, 1000.0), "B")
        report = compare_sequences(a_frames, a_durs, b_frames, b_durs, sample=n_sample)
        pairing = align(a_durs, b_durs)
        w, h = a_frames[0].shape[1], a_frames[0].shape[0]
        lines = [
            f"A: {len(a_frames)} frames, {w}x{h}, {sum(a_durs):.2f}s" + (f", {a_bytes:,} bytes" if a_bytes is not None else ""),
            f"B: {len(b_frames)} frames, {b_frames[0].shape[1]}x{b_frames[0].shape[0]}, {sum(b_durs):.2f}s" + (f", {b_bytes:,} bytes" if b_bytes is not None else ""),
        ]
        if a_bytes and b_bytes:
            lines.append(f"size B/A: {b_bytes / a_bytes * 100:.1f}% ({(1 - b_bytes / a_bytes) * 100:+.1f}% saved)")
        if (b_frames[0].shape[1], b_frames[0].shape[0]) != (w, h):
            lines.append("note: B was resized to A's dimensions for the comparison")
        lines.append(report.line())
        idx = np.linspace(0, len(a_frames) - 1, num=min(n_out, len(a_frames))).astype(int)
        out: list[Frame] = []
        for i in idx:
            a = a_frames[int(i)]
            b = resize_frame(b_frames[pairing[int(i)]], w, h, "bicubic")
            out.append(_compose(a, b, layout))
        tensor = frames_to_tensor(out)
        text = "\n".join(lines)
        return io.NodeOutput(tensor, text, ui={"jwtf_gif_text": [text]})


def _compose(a: Frame, b: Frame, layout: str) -> Frame:
    if layout == "side_by_side":
        return np.concatenate([a, b], axis=1)
    if layout == "split":
        half = a.shape[1] // 2
        out = a.copy()
        out[:, half:] = b[:, half:]
        out[:, max(0, half - 1) : half + 1] = 255
        return out
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16)) * 4
    return np.clip(diff, 0, 255).astype(np.uint8)


class JWTFLoadGif(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFLoadGif",
            display_name='Load GIF',
            category='JezzWTF/gif',
            inputs=[
                io.Combo.Input("gif", options=list_input_gifs(), upload=io.UploadType.image),
                io.String.Input("path", default='', optional=True, tooltip='Optional GIF path (input, output or temp). Overrides the picker.'),
                io.Int.Input("max_frames", default=0, min=0, max=10000, optional=True, tooltip='0 = all frames.'),
            ],
            outputs=[
                io.Image.Output("images"),
                io.Mask.Output("mask"),
                io.Float.Output("fps"),
                io.Int.Output("frame_count"),
                io.String.Output("delays_ms"),
                io.String.Output("gif_path"),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, gif: str = "", path: str = "", **_: object) -> str:
        return JWTFGifOptimise.fingerprint_inputs(gif, path)

    @classmethod
    def execute(cls, gif: str, path: str = "", max_frames: int = 0) -> io.NodeOutput:
        limit = check_int("max_frames", max_frames, 0, 10000)
        real = resolve_existing_file(path.strip() or gif, read_roots())
        g = read_gif(real)
        frames, alphas, durations = g.frames, g.alphas, g.durations
        if limit:
            frames, alphas, durations = frames[:limit], alphas[:limit], durations[:limit]
        images = frames_to_tensor(frames)
        mask: NDArray[np.float32] = 1.0 - np.stack(alphas).astype(np.float32) / 255.0  # ComfyUI mask: 1 = transparent
        fps = len(durations) / sum(durations) if sum(durations) else 0.0
        return io.NodeOutput(images, torch.from_numpy(mask), float(fps), len(frames), json.dumps([round(d * 1000) for d in durations]), os.path.abspath(real))


class JWTFFramesToAnimated(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFFramesToAnimated",
            display_name='Frames to Animated WebP / APNG',
            category='JezzWTF/gif',
            description="Encode an image batch as an animated WebP or APNG, optionally searching for the best quality under a size target.",
            inputs=[
                io.Image.Input("images"),
                io.Float.Input("fps", default=20.0, min=0.1, max=240.0, step=0.5),
                io.Combo.Input("format", options=list(FORMATS), default='webp'),
                io.String.Input("filename_prefix", default='gifs/anim', tooltip='Relative to the output folder. Put a subfolder in the prefix, e.g. gifs/anim saves to output/gifs/anim_00001.webp.'),
                io.Boolean.Input("lossless", default=False, optional=True),
                io.Int.Input("quality", default=80, min=0, max=100, optional=True, tooltip='WebP lossy quality; ignored when a target size is set.'),
                io.Int.Input("method", default=4, min=0, max=6, optional=True, tooltip='WebP effort: 0 fast, 6 smallest.'),
                io.Float.Input("dedupe_threshold", default=0.0, min=0.0, max=20.0, step=0.05, optional=True, tooltip='0 = merge exact duplicates only.'),
                io.Float.Input("target_size_mb", default=0.0, min=0.0, max=512.0, step=0.05, optional=True, tooltip='0 = off. Lossy WebP searches the best quality that fits.'),
                io.Int.Input("loop_count", default=0, min=0, max=65535, optional=True, tooltip='0 = forever.'),
            ],
            outputs=[
                io.String.Output("file_path"),
                io.String.Output("report"),
            ],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, images: torch.Tensor, fps: float, format: str, filename_prefix: str, lossless: bool = False, quality: int = 80,
            method: int = 4, dedupe_threshold: float = 0.0, target_size_mb: float = 0.0, loop_count: int = 0) -> io.NodeOutput:
        check_choice("format", format, FORMATS)
        rate = check_float("fps", fps, 0.1, 240.0)
        frames = tensor_to_frames(images)
        clip = Clip(frames, [1.0 / rate] * len(frames))
        res: AnimResult = encode_animated(
            clip, format, check_int("quality", quality, 0, 100), check_int("method", method, 0, 6), bool(lossless),
            check_float("dedupe_threshold", dedupe_threshold, 0.0, 20.0), check_float("target_size_mb", target_size_mb, 0.0, 512.0),
            check_int("loop_count", loop_count, 0, 65535),
        )
        ext = "webp" if format == "webp" else "png"
        path, subfolder, filename = save_bytes(res.data, filename_prefix, ext)
        report = res.report()
        return io.NodeOutput(path, report, ui=_ui(subfolder, filename, res.stats(), "animated"))



NODES = [JWTFVideoToGif, JWTFGifOptimise, JWTFGifCompare, JWTFLoadGif, JWTFFramesToAnimated]
