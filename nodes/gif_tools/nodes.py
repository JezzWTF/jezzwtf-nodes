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

from .animated import FORMATS, AnimResult, encode_animated
from .frames import Clip, Frame, FrameSource, PrepOptions, make_clip, source_from_arrays, source_from_timed_arrays, source_from_video_file
from .gifio import read_gif
from .optimise import OptimiseRequest, OptimiseResult, optimise
from .output import OUTPUT_SUBFOLDER, reserve_output_path, resolve_existing_file
from .quality import compare_sequences
from .runtime import Progress, check_interrupt
from .settings import (DELAY_MODES, DENOISE, DITHERS, MODES, PALETTES, RESIZE_FILTERS, check_choice, check_colors, check_float,
                       check_int)
from .timing import MAX_FPS, fps_notes, resolve_fps

try:
    from ..utility_core._comfy import input_dir, temp_dir
    from ..utility_core._types import InputTypes
except ImportError:  # imported as a top-level package (tests)
    from utility_core._comfy import input_dir, temp_dir  # type: ignore[no-redef]
    from utility_core._types import InputTypes  # type: ignore[no-redef]

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


def _finish_gif(result: OptimiseResult, path: str, subfolder: str, filename: str, mode: str) -> tuple[str, torch.Tensor, str, UIResult]:
    from .encoder import decode_result

    frames, _ = decode_result(result.encode)
    tensor, sampled = preview_tensor(frames)
    report = result.report()
    report += f"\nsaved: output/{subfolder + '/' if subfolder else ''}{filename}"
    if sampled:
        report += f"\nnote: preview output holds {MAX_PREVIEW_FRAMES} evenly spaced frames of {len(frames)}"
    return path, tensor, report, {"ui": _ui(subfolder, filename, result.stats(), mode), "result": (path, tensor, report)}


# ------------------------------------------------------------------ nodes

class JWTFVideoToGif:
    CATEGORY = CATEGORY
    FUNCTION = "run"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "IMAGE", "STRING")
    RETURN_NAMES = ("gif_path", "preview", "report")

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        optional: dict[str, tuple[object, ...]] = {
            "images": ("IMAGE", {}),
            "video": ("VIDEO", {}),
            "source_fps": ("FLOAT", {"default": 24.0, "min": 0.1, "max": 1000.0, "step": 0.1, "tooltip": "Frame rate of the IMAGE batch (ignored for VIDEO)."}),
            "fps": ("FLOAT", {"default": 20.0, "min": 0.0, "max": 1000.0, "step": 0.5, "tooltip": "Output frame rate; 0 = keep the source rate (capped at 50). 25, 20 and 12.5 give an even GIF cadence."}),
            **_optimise_widgets(),
        }
        return {"required": {"mode": (list(MODES), {"default": "balanced"}), "filename_prefix": ("STRING", {"default": "gifs/clip", "tooltip": "Relative to the output folder. Put a subfolder in the prefix, e.g. gifs/clip saves to output/gifs/clip_00001.gif."})}, "optional": optional}

    def run(self, mode: str, filename_prefix: str, images: torch.Tensor | None = None, video: object | None = None, source_fps: float = 24.0,
            **kwargs: object) -> UIResult:
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
        return _finish_gif(result, path, subfolder, filename, mode)[3]


class JWTFGifOptimise:
    CATEGORY = CATEGORY
    FUNCTION = "run"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "IMAGE", "STRING")
    RETURN_NAMES = ("gif_path", "preview", "report")

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        optional: dict[str, tuple[object, ...]] = {
            "path": ("STRING", {"default": "", "tooltip": "Optional GIF path (inside input, output or temp). Overrides the picker, e.g. the output of another GIF node."}),
            "fps": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1000.0, "step": 0.5, "tooltip": "0 = keep the GIF's own frame timing."}),
            **_optimise_widgets(),
        }
        return {"required": {"gif": ([USE_PATH, *list_input_gifs()], {"image_upload": True}),
                             "mode": (list(MODES), {"default": "balanced"}),
                             "filename_prefix": ("STRING", {"default": "gifs/optimised", "tooltip": "Relative to the output folder. Put a subfolder in the prefix, e.g. gifs/optimised saves to output/gifs/optimised_00001.gif."})}, "optional": optional}

    @classmethod
    def IS_CHANGED(cls, gif: str = "", path: str = "", **_: object) -> str:
        try:
            real = resolve_existing_file(path or gif, read_roots())
            st = os.stat(real)
            return f"{real}:{st.st_mtime_ns}:{st.st_size}"
        except (ValueError, OSError):
            return "missing"

    def run(self, gif: str, mode: str, filename_prefix: str, path: str = "", **kwargs: object) -> UIResult:
        chosen = path.strip() or ("" if gif == USE_PATH else gif)
        if not chosen:
            raise ValueError("GIF Optimise: pick a GIF, or connect a path (for example from Load GIF).")
        real = resolve_existing_file(chosen, read_roots())
        source, notes, _ = gif_source(real)
        values: dict[str, object] = {"mode": mode, **kwargs}
        result, out_path, subfolder, filename, _ = _run_optimise(source, _defaults(values), notes, filename_prefix)
        original = os.path.getsize(real)
        result.notes.append(f"source GIF {original:,} bytes -> {len(result.data):,} bytes ({(1 - len(result.data) / original) * 100:.1f}% saved)")
        return _finish_gif(result, out_path, subfolder, filename, mode)[3]


def _defaults(values: dict[str, object]) -> dict[str, object]:
    """Fill any widget the caller (or an older saved workflow) left out with its declared default."""
    out: dict[str, object] = {"fps": 0.0}
    for name, spec in _optimise_widgets().items():
        cfg = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
        out[name] = cfg.get("default", spec[0][0] if isinstance(spec[0], list) else None)
    out.update(values)
    return out


class JWTFGifCompare:
    CATEGORY = CATEGORY
    FUNCTION = "run"
    OUTPUT_NODE = True
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("compare", "report")
    LAYOUTS = ("side_by_side", "split", "difference")

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {"layout": (list(cls.LAYOUTS), {"default": "side_by_side"})},
            "optional": {
                "gif_a": ("STRING", {"default": "", "tooltip": "Reference GIF path (input, output or temp folder). Relative names resolve under input."}),
                "gif_b": ("STRING", {"default": "", "tooltip": "GIF to judge against A, e.g. an optimised result."}),
                "images_a": ("IMAGE", {}),
                "images_b": ("IMAGE", {}),
                "fps_a": ("FLOAT", {"default": 20.0, "min": 0.1, "max": 1000.0, "step": 0.1, "tooltip": "Rate of images_a."}),
                "fps_b": ("FLOAT", {"default": 20.0, "min": 0.1, "max": 1000.0, "step": 0.1, "tooltip": "Rate of images_b."}),
                "sample_frames": ("INT", {"default": 24, "min": 1, "max": 400, "tooltip": "Frames of A measured for SSIM/PSNR (evenly spread)."}),
                "output_frames": ("INT", {"default": 60, "min": 1, "max": 400, "tooltip": "Frames in the comparison image batch."}),
            },
        }

    @staticmethod
    def _load(path: str, images: torch.Tensor | None, fps: float, label: str) -> tuple[list[Frame], list[float], int | None]:
        if images is not None:
            return tensor_to_frames(images), [1.0 / fps] * int(images.shape[0]), None
        if not path.strip():
            raise ValueError(f"give {label} as a GIF path or an IMAGE batch")
        real = resolve_existing_file(path, read_roots())
        g = read_gif(real)
        return g.frames, g.durations, os.path.getsize(real)

    def run(self, layout: str, gif_a: str = "", gif_b: str = "", images_a: torch.Tensor | None = None, images_b: torch.Tensor | None = None,
            fps_a: float = 20.0, fps_b: float = 20.0, sample_frames: int = 24, output_frames: int = 60) -> dict[str, object]:
        from .frames import resize_frame
        from .quality import align

        check_choice("layout", layout, self.LAYOUTS)
        n_sample = check_int("sample_frames", sample_frames, 1, 400)
        n_out = check_int("output_frames", output_frames, 1, 400)
        a_frames, a_durs, a_bytes = self._load(gif_a, images_a, check_float("fps_a", fps_a, 0.1, 1000.0), "A")
        b_frames, b_durs, b_bytes = self._load(gif_b, images_b, check_float("fps_b", fps_b, 0.1, 1000.0), "B")
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
        return {"ui": {"jwtf_gif_text": [text]}, "result": (tensor, text)}


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


class JWTFLoadGif:
    CATEGORY = CATEGORY
    FUNCTION = "run"
    # gif_path lets Load GIF feed GIF Optimise (path) and GIF Analyse / Compare (gif_a) directly.
    RETURN_TYPES = ("IMAGE", "MASK", "FLOAT", "INT", "STRING", "STRING")
    RETURN_NAMES = ("images", "mask", "fps", "frame_count", "delays_ms", "gif_path")

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {"gif": (list_input_gifs(), {"image_upload": True})},
            "optional": {
                "path": ("STRING", {"default": "", "tooltip": "Optional GIF path (input, output or temp). Overrides the picker."}),
                "max_frames": ("INT", {"default": 0, "min": 0, "max": 10000, "tooltip": "0 = all frames."}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, gif: str = "", path: str = "", **_: object) -> str:
        return JWTFGifOptimise.IS_CHANGED(gif, path)

    def run(self, gif: str, path: str = "", max_frames: int = 0) -> tuple[torch.Tensor, torch.Tensor, float, int, str, str]:
        limit = check_int("max_frames", max_frames, 0, 10000)
        real = resolve_existing_file(path.strip() or gif, read_roots())
        g = read_gif(real)
        frames, alphas, durations = g.frames, g.alphas, g.durations
        if limit:
            frames, alphas, durations = frames[:limit], alphas[:limit], durations[:limit]
        images = frames_to_tensor(frames)
        mask: NDArray[np.float32] = 1.0 - np.stack(alphas).astype(np.float32) / 255.0  # ComfyUI mask: 1 = transparent
        fps = len(durations) / sum(durations) if sum(durations) else 0.0
        return (images, torch.from_numpy(mask), float(fps), len(frames),
                json.dumps([round(d * 1000) for d in durations]), os.path.abspath(real))


class JWTFFramesToAnimated:
    CATEGORY = CATEGORY
    FUNCTION = "run"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("file_path", "report")

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {
                "images": ("IMAGE", {}),
                "fps": ("FLOAT", {"default": 20.0, "min": 0.1, "max": 240.0, "step": 0.5}),
                "format": (list(FORMATS), {"default": "webp"}),
                "filename_prefix": ("STRING", {"default": "gifs/anim", "tooltip": "Relative to the output folder. Put a subfolder in the prefix, e.g. gifs/anim saves to output/gifs/anim_00001.webp."}),
            },
            "optional": {
                "lossless": ("BOOLEAN", {"default": False}),
                "quality": ("INT", {"default": 80, "min": 0, "max": 100, "tooltip": "WebP lossy quality; ignored when a target size is set."}),
                "method": ("INT", {"default": 4, "min": 0, "max": 6, "tooltip": "WebP effort: 0 fast, 6 smallest."}),
                "dedupe_threshold": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 20.0, "step": 0.05, "tooltip": "0 = merge exact duplicates only."}),
                "target_size_mb": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 512.0, "step": 0.05, "tooltip": "0 = off. Lossy WebP searches the best quality that fits."}),
                "loop_count": ("INT", {"default": 0, "min": 0, "max": 65535, "tooltip": "0 = forever."}),
            },
        }

    def run(self, images: torch.Tensor, fps: float, format: str, filename_prefix: str, lossless: bool = False, quality: int = 80,
            method: int = 4, dedupe_threshold: float = 0.0, target_size_mb: float = 0.0, loop_count: int = 0) -> UIResult:
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
        return {"ui": _ui(subfolder, filename, res.stats(), "animated"), "result": (path, report)}


NODE_CLASS_MAPPINGS = {
    "JWTFVideoToGif": JWTFVideoToGif,
    "JWTFGifOptimise": JWTFGifOptimise,
    "JWTFGifCompare": JWTFGifCompare,
    "JWTFLoadGif": JWTFLoadGif,
    "JWTFFramesToAnimated": JWTFFramesToAnimated,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "JWTFVideoToGif": "Video to GIF (Optimised)",
    "JWTFGifOptimise": "GIF Optimise",
    "JWTFGifCompare": "GIF Analyse / Compare",
    "JWTFLoadGif": "Load GIF",
    "JWTFFramesToAnimated": "Frames to Animated WebP / APNG",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
