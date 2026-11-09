"""Folder Image / Video batch loaders, the caption saver and the scan route."""
from __future__ import annotations

import logging
import os
from collections.abc import Generator, Iterator
from fractions import Fraction
from typing import TYPE_CHECKING, TypedDict

import numpy as np
import torch
from PIL import Image, ImageOps

from comfy_api.latest import io

from ._comfy import is_loopback_request, temp_dir
from ._types import UIPayload
from .folder_utils import (
    SORT_MODES, FrameSelector, caption_target, clean_path, fit_even, list_media, next_index, preview_name,
    resolve_index,
)

if TYPE_CHECKING:
    from aiohttp import web

log = logging.getLogger("jezzwtf.utility_core.folder_batch")

FrameIter = Iterator[np.ndarray]
FrameGen = Generator[np.ndarray, None, None]


class AudioDict(TypedDict):
    waveform: torch.Tensor
    sample_rate: int


class PreviewRef(TypedDict):
    filename: str
    subfolder: str
    type: str


# ---------------------------------------------------------------- previews

def save_preview(img: Image.Image, fullpath: str) -> PreviewRef:
    try:
        mtime_ns = os.stat(fullpath).st_mtime_ns
    except OSError:
        mtime_ns = 0
    name = preview_name(fullpath, mtime_ns)
    out = os.path.join(temp_dir(), name)
    if not os.path.exists(out):
        has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        thumb = img.convert("RGBA" if has_alpha else "RGB")
        thumb.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        thumb.save(out, compress_level=1)
    return {"filename": name, "subfolder": "", "type": "temp"}


def _ui(preview: PreviewRef | None, idx: int, total: int, auto: bool, fullpath: str) -> UIPayload:
    return {
        "preview": [preview] if preview else [],
        "batch_info": [idx, total],
        "auto_run": [1 if auto else 0],
        "next_index": [next_index(idx, total, auto)],
        "file_name": [os.path.basename(fullpath)],
    }


def _resolve(folder_path: str, sort_mode: str, index: int, kind: str, auto: bool = False) -> tuple[list[str], int]:
    files = list_media(folder_path, kind, sort_mode)
    if not files:
        raise ValueError(f"No {'videos' if kind == 'video' else 'images'} found in {clean_path(folder_path)}")
    return files, resolve_index(index, len(files), auto)


def _change_key(folder_path: str, sort_mode: str, index: int, auto: bool, kind: str, extra: str = "") -> str | float:
    if auto:
        return float("nan")
    try:
        files, idx = _resolve(folder_path, sort_mode, index, kind)
        st = os.stat(files[idx])
        return f"{files[idx]}|{st.st_mtime_ns}|{st.st_size}|{len(files)}{extra}"
    except Exception:
        return float("nan")


# ---------------------------------------------------------------- image loading

def load_image(path: str) -> tuple[torch.Tensor, torch.Tensor, Image.Image]:
    with Image.open(path) as opened:
        opened.seek(0)
        img = ImageOps.exif_transpose(opened) or opened
        img.load()
        img = img.copy()
    if img.mode == "I":
        img = img.point(lambda v: v * (1 / 255))
    if img.mode == "P" and "transparency" in img.info:
        img = img.convert("RGBA")
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    image = torch.from_numpy(rgb)[None]
    if "A" in img.getbands():
        alpha = np.asarray(img.getchannel("A"), dtype=np.float32) / 255.0
        mask = 1.0 - torch.from_numpy(alpha)[None]
    else:
        mask = torch.zeros((1, rgb.shape[0], rgb.shape[1]), dtype=torch.float32)
    return image, mask, img


class JWTFFolderImageBatch(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFFolderImageBatch",
            display_name='Folder Image Batch',
            category='JezzWTF/dataset',
            inputs=[
                io.String.Input("folder_path", default=''),
                io.Combo.Input("sort_mode", options=['numeric (001, 002, 10...)', 'alphabetical']),
                io.Int.Input("index", default=0, min=0, max=16777215),
                io.Boolean.Input("auto_run_folder", default=True, label_on='run whole folder', label_off='single image'),
            ],
            outputs=[
                io.Image.Output("image"),
                io.Mask.Output("mask"),
                io.String.Output("filename"),
                io.String.Output("path"),
                io.Int.Output("index"),
                io.Int.Output("total"),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, folder_path: str, sort_mode: str, index: int, auto_run_folder: bool) -> str | float:
        return _change_key(folder_path, sort_mode, index, auto_run_folder, "image")

    @classmethod
    def execute(cls, folder_path: str, sort_mode: str, index: int, auto_run_folder: bool) -> io.NodeOutput:
        files, idx = _resolve(folder_path, sort_mode, index, "image", auto_run_folder)
        path = files[idx]
        image, mask, img = load_image(path)
        preview = save_preview(img, path)
        stem = os.path.splitext(os.path.basename(path))[0]
        return io.NodeOutput(image, mask, stem, path, idx, len(files), ui=_ui(preview, idx, len(files), auto_run_folder, path))


# ---------------------------------------------------------------- video loading

def silent_audio() -> AudioDict:
    return {"waveform": torch.zeros((1, 2, 4410), dtype=torch.float32), "sample_rate": 44100}


def _decode_audio(path: str, start: float, end: float | None) -> AudioDict:
    try:
        import av  # type: ignore[import-not-found]
    except ImportError:
        return silent_audio()
    try:
        with av.open(path) as container:
            if not container.streams.audio:
                return silent_audio()
            stream = container.streams.audio[0]
            rate = int(stream.rate or 44100)
            resampler = av.AudioResampler(format="fltp", layout="stereo", rate=rate)
            chunks: list[np.ndarray] = []
            for frame in container.decode(stream):
                for out in resampler.resample(frame):
                    chunks.append(out.to_ndarray())
            for out in resampler.resample(None):
                chunks.append(out.to_ndarray())
        if not chunks:
            return silent_audio()
        data = np.concatenate(chunks, axis=1).astype(np.float32)
        s0 = int(start * rate)
        s1 = data.shape[1] if end is None else int(end * rate)
        data = data[:, s0:s1]
        if data.shape[1] == 0:
            return silent_audio()
        return {"waveform": torch.from_numpy(np.ascontiguousarray(data))[None], "sample_rate": rate}
    except Exception as exc:
        log.warning("audio decode failed for %s: %s", path, exc)
        return silent_audio()


def _iter_frames_av(path: str) -> tuple[float, FrameIter]:
    import av  # type: ignore[import-not-found]

    container = av.open(path)
    stream = container.streams.video[0]
    rate = stream.average_rate
    src_fps = float(rate) if rate else 24.0

    def gen() -> FrameGen:
        try:
            for frame in container.decode(stream):
                yield frame.to_ndarray(format="rgb24")
        finally:
            container.close()

    return src_fps, gen()


def _iter_frames_cv2(path: str) -> tuple[float, FrameIter]:
    import cv2  # type: ignore[import-not-found]

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {path}")
    src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 24.0

    def gen() -> FrameGen:
        try:
            while True:
                ok, bgr = cap.read()
                if not ok:
                    break
                yield cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        finally:
            cap.release()

    return src_fps, gen()


def decode_video(path: str, force_rate: float = 0.0, frame_load_cap: int = 0, skip_first_frames: int = 0,
                 select_every_nth: int = 1, resize_longest_side: int = 0
                 ) -> tuple[torch.Tensor, float, FrameSelector, bool]:
    """Returns (frames[N,H,W,3], out_fps, selector, used_pyav)."""
    try:
        src_fps, frames_iter = _iter_frames_av(path)
        used_av = True
    except ImportError:
        src_fps, frames_iter = _iter_frames_cv2(path)
        used_av = False
    sel = FrameSelector(src_fps, force_rate, skip_first_frames, select_every_nth, frame_load_cap)
    size: tuple[int, int] | None = None
    kept: list[np.ndarray] = []
    for i, arr in enumerate(frames_iter):
        if sel.done:
            break
        if not sel.offer(i):
            continue
        h, w = arr.shape[:2]
        if size is None:
            size = fit_even(w, h, resize_longest_side)
        if (w, h) != size:
            arr = np.asarray(Image.fromarray(arr).resize(size, Image.Resampling.BILINEAR))
        kept.append(arr)
    close = getattr(frames_iter, "close", None)
    if callable(close):
        close()
    if not kept:
        raise ValueError(f"no frames decoded from {path}")
    frames = torch.from_numpy(np.stack(kept).astype(np.float32) / 255.0)
    return frames, sel.out_fps, sel, used_av


def build_video(frames: torch.Tensor, audio: AudioDict, fps: float) -> object | None:
    rate = Fraction(fps).limit_denominator(1000)
    try:
        from comfy_api.latest import InputImpl, Types  # type: ignore[import-not-found]

        return InputImpl.VideoFromComponents(Types.VideoComponents(images=frames, audio=audio, frame_rate=rate))
    except ImportError:
        pass
    try:
        from comfy_api.input import VideoComponents  # type: ignore[import-not-found]
        from comfy_api.input_impl import VideoFromComponents  # type: ignore[import-not-found]

        return VideoFromComponents(VideoComponents(images=frames, audio=audio, frame_rate=rate))
    except ImportError:
        log.warning("comfy_api video types unavailable; VIDEO output is None")
        return None


class JWTFFolderVideoBatch(io.ComfyNode):
    OPTIONAL_KEYS = ("force_rate", "frame_load_cap", "skip_first_frames", "select_every_nth", "resize_longest_side")

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFFolderVideoBatch",
            display_name='Folder Video Batch',
            category='JezzWTF/dataset',
            inputs=[
                io.String.Input("folder_path", default=''),
                io.Combo.Input("sort_mode", options=['numeric (001, 002, 10...)', 'alphabetical']),
                io.Int.Input("index", default=0, min=0, max=16777215),
                io.Boolean.Input("auto_run_folder", default=True, label_on='run whole folder', label_off='single video'),
                io.Float.Input("force_rate", default=0.0, min=0.0, max=120.0, step=0.5, optional=True),
                io.Int.Input("frame_load_cap", default=0, min=0, max=100000, optional=True),
                io.Int.Input("skip_first_frames", default=0, min=0, max=1000000, optional=True),
                io.Int.Input("select_every_nth", default=1, min=1, max=1000, optional=True),
                io.Int.Input("resize_longest_side", default=0, min=0, max=8192, step=2, optional=True),
            ],
            outputs=[
                io.Image.Output("frames"),
                io.Audio.Output("audio"),
                io.String.Output("filename"),
                io.String.Output("path"),
                io.Int.Output("index"),
                io.Int.Output("total"),
                io.Float.Output("fps"),
                io.Video.Output("video"),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, folder_path: str, sort_mode: str, index: int, auto_run_folder: bool,
                   **opts: object) -> str | float:
        extra = "".join(f"|{k}={opts[k]}" for k in sorted(opts))
        return _change_key(folder_path, sort_mode, index, auto_run_folder, "video", extra)

    @classmethod
    def execute(cls, folder_path: str, sort_mode: str, index: int, auto_run_folder: bool, force_rate: float = 0.0,
            frame_load_cap: int = 0, skip_first_frames: int = 0, select_every_nth: int = 1,
            resize_longest_side: int = 0) -> io.NodeOutput:
        files, idx = _resolve(folder_path, sort_mode, index, "video", auto_run_folder)
        path = files[idx]
        frames, fps, sel, used_av = decode_video(path, force_rate, frame_load_cap, skip_first_frames,
                                                 select_every_nth, resize_longest_side)
        start, end = sel.audio_window()
        audio = _decode_audio(path, start, end) if used_av else silent_audio()
        first = Image.fromarray((frames[0].numpy() * 255).round().astype(np.uint8))
        preview = save_preview(first, path)
        video = build_video(frames, audio, fps)
        stem = os.path.splitext(os.path.basename(path))[0]
        return io.NodeOutput(frames, audio, stem, path, idx, len(files), float(fps), video, ui=_ui(preview, idx, len(files), auto_run_folder, path))


# ---------------------------------------------------------------- caption saver

def save_caption(text: str, image_path: str, save_location: str, custom_folder: str, extension: str,
                 overwrite: bool) -> tuple[str, bool]:
    """Returns (path, written)."""
    target = caption_target(image_path, save_location, custom_folder, extension)
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    if os.path.exists(target) and not overwrite:
        log.info("caption exists, skipped: %s", target)
        return target, False
    body = text.strip().replace("\r\n", "\n").replace("\r", "\n")
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    return target, True


class JWTFSaveCaptionMatchImage(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFSaveCaptionMatchImage",
            display_name='Save Caption (Match Image)',
            category='JezzWTF/dataset',
            inputs=[
                io.String.Input("text", force_input=True),
                io.String.Input("image_path", force_input=True),
                io.Combo.Input("save_location", options=['next to image', 'custom folder']),
                io.String.Input("custom_folder", default=''),
                io.String.Input("extension", default='txt'),
                io.Boolean.Input("overwrite", default=True, label_on='overwrite existing', label_off='skip if exists'),
            ],
            outputs=[
                io.String.Output("saved_path"),
            ],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **_: object) -> float:
        return float("nan")

    @classmethod
    def execute(cls, text: str, image_path: str, save_location: str, custom_folder: str, extension: str,
            overwrite: bool) -> io.NodeOutput:
        path, _ = save_caption(text, image_path, save_location, custom_folder, extension, overwrite)
        return io.NodeOutput(path, ui={"text": [path]})


# ---------------------------------------------------------------- scan route

def _first_video_frame(path: str) -> Image.Image:
    _fps, it = (_iter_frames_av(path) if _has_av() else _iter_frames_cv2(path))
    try:
        arr = next(iter(it))
    finally:
        close = getattr(it, "close", None)
        if callable(close):
            close()
    return Image.fromarray(arr)


def _has_av() -> bool:
    try:
        import av  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return False
    return True


MAX_SCAN_FILES = 20000
MAX_SCAN_CONCURRENCY = 2


def scan(folder: str, sort: str, kind: str, requested: int) -> dict[str, object]:
    try:
        files = list_media(folder, kind, sort)
        if not files:
            raise ValueError("no matching files in folder")
        if len(files) > MAX_SCAN_FILES:
            raise ValueError(f"too many files to scan (over {MAX_SCAN_FILES})")
        idx = requested if 0 <= requested < len(files) else 0
        path = files[idx]
        if kind == "video":
            img = _first_video_frame(path)
        else:
            img = load_image(path)[2]
        return {"ok": True, "total": len(files), "index": idx, "requested_index": requested,
                "name": os.path.basename(path), "first": os.path.basename(files[0]),
                "last": os.path.basename(files[-1]), "preview": save_preview(img, path)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def register_routes(routes: "web.RouteTableDef") -> None:
    import asyncio

    from aiohttp import web

    slots = asyncio.Semaphore(MAX_SCAN_CONCURRENCY)

    @routes.get("/jezzwtf/folder_batch/scan")
    async def _scan(request: web.Request) -> web.Response:
        if not is_loopback_request(request.remote, request.headers.get("Host")):
            return web.json_response({"ok": False, "error": "folder scan is only available locally"}, status=403)
        q = request.rel_url.query
        try:
            requested = int(q.get("index", "0"))
        except ValueError:
            requested = 0
        kind = "video" if q.get("kind") == "video" else "image"
        if slots.locked():
            return web.json_response({"ok": False, "error": "scan busy, try again"}, status=429)
        async with slots:
            result = await asyncio.to_thread(scan, q.get("folder", ""), q.get("sort", SORT_MODES[0]), kind,
                                             requested)
        return web.json_response(result)


NODES = [JWTFFolderImageBatch, JWTFFolderVideoBatch, JWTFSaveCaptionMatchImage]
