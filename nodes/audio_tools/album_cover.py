"""Album Cover: embed an image as the cover art of an mp3, flac or m4a file (and optionally set its basic tags)."""
from __future__ import annotations

import os
from io import BytesIO

import av
import numpy as np
import torch
from comfy_api.latest import io
from PIL import Image

from . import paths

SAVE_COPY = "save a copy in output"
REPLACE = "replace the original"
ATTACHED_PIC = av.stream.Disposition.attached_pic.value
JPEG_QUALITY = 92


def tensor_to_cover(image: torch.Tensor, index: int, max_edge: int) -> bytes:
    """One IMAGE-batch frame as JPEG bytes, scaled down (never up) so its longest edge is `max_edge` (0 = keep)."""
    frame = image[min(max(index, 0), image.shape[0] - 1)].detach().cpu().float().clamp(0, 1)
    if frame.shape[-1] == 1:
        frame = frame.expand(*frame.shape[:-1], 3)
    pixels = (frame[..., :3].numpy() * 255.0 + 0.5).astype(np.uint8)
    pic = Image.fromarray(pixels, "RGB")
    if max_edge > 0 and max(pic.size) > max_edge:
        scale = max_edge / max(pic.size)
        pic = pic.resize((max(1, round(pic.width * scale)), max(1, round(pic.height * scale))), Image.Resampling.LANCZOS)
    buf = BytesIO()
    pic.save(buf, "JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def embed_cover(src: str, dst: str, cover_jpeg: bytes, tags: dict[str, str] | None = None) -> None:
    """Copy `src` to `dst` (same container, audio untouched) with `cover_jpeg` as its attached picture."""
    ext = os.path.splitext(dst)[1].lower()
    if ext not in paths.COVER_EXTENSIONS:
        raise ValueError(f"cover art can be embedded in {', '.join(paths.COVER_EXTENSIONS)} files, not {ext or 'this file type'}")
    container_format = "mp4" if ext == ".m4a" else None  # the default ipod muxer refuses a picture stream
    with av.open(src) as source, av.open(dst, "w", format=container_format) as target:
        audio = {s.index: target.add_stream_from_template(s) for s in source.streams.audio[:1]}
        if not audio:
            raise ValueError(f"{os.path.basename(src)} has no audio stream")
        target.metadata.update(source.metadata)
        for key, value in (tags or {}).items():
            if value.strip():
                target.metadata[key] = value.strip()
        with av.open(BytesIO(cover_jpeg), format="image2") as picture:
            picture_stream = picture.streams.video[0]
            cover = target.add_stream_from_template(picture_stream)
            cover.disposition = ATTACHED_PIC
            packets = [p for p in picture.demux(picture_stream) if p.size]
        for packet in packets:
            packet.stream = cover
            target.mux(packet)
        for packet in source.demux(*[s for s in source.streams if s.index in audio]):
            if packet.dts is None:
                continue
            packet.stream = audio[packet.stream.index]
            target.mux(packet)


def read_cover(path: str) -> bytes | None:
    """The attached picture bytes of an audio file, or None when it has none."""
    with av.open(path) as container:
        for stream in container.streams.video:
            if stream.disposition & av.stream.Disposition.attached_pic:
                for packet in container.demux(stream):
                    if packet.size:
                        return bytes(packet)
    return None


def unique_path(folder: str, stem: str, ext: str) -> str:
    os.makedirs(folder, exist_ok=True)
    candidate = os.path.join(folder, f"{stem}{ext}")
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{stem}_{counter:03d}{ext}")
        counter += 1
    return candidate


def safe_prefix(prefix: str) -> str:
    """A relative sub-folder for the output (no drive, no `..`)."""
    parts = [p for p in prefix.replace("\\", "/").split("/") if p and p not in (".", "..") and ":" not in p]
    return "/".join(parts)


class JWTFAlbumCover(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFAlbumCover",
            display_name="Album Cover",
            category="JezzWTF/audio",
            description="Embed an image as the cover art of an mp3, flac or m4a file; optionally set title, artist and album.",
            inputs=[
                io.Image.Input("image", tooltip="The first frame of the batch (or the chosen index) becomes the cover."),
                io.String.Input("audio_path", default="", tooltip="An audio file in the input, output or temp folder, e.g. from Audio Loader."),
                io.Combo.Input("save_mode", options=[SAVE_COPY, REPLACE], default=SAVE_COPY, tooltip="Saves a separate copy in output or replaces the original file, with replacement unavailable for temp files."),
                io.String.Input("filename_prefix", default="covers", optional=True, tooltip="Sub-folder of output for the copy."),
                io.Int.Input("cover_size", default=1000, min=0, max=4096, step=10, optional=True, tooltip="Longest edge in pixels; 0 keeps the image size."),
                io.Int.Input("image_index", default=0, min=0, max=4096, optional=True, tooltip="Zero-based frame to use from the batch, clamped to the last frame if the index is too large."),
                io.String.Input("title", default="", optional=True, tooltip="Optional title tag, with blank preserving the existing metadata."),
                io.String.Input("artist", default="", optional=True, tooltip="Optional artist tag, with blank preserving the existing metadata."),
                io.String.Input("album", default="", optional=True, tooltip="Optional album tag, with blank preserving the existing metadata."),
            ],
            outputs=[io.String.Output("file_path", tooltip="Full path to the audio file containing the embedded cover.")],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, image: torch.Tensor, audio_path: str, save_mode: str, filename_prefix: str = "covers", cover_size: int = 1000,
                image_index: int = 0, title: str = "", artist: str = "", album: str = "") -> io.NodeOutput:
        src = paths.resolve_audio(audio_path)
        stem, ext = os.path.splitext(os.path.basename(src))
        cover = tensor_to_cover(image, int(image_index), int(cover_size))
        tags = {"title": title, "artist": artist, "album": album}
        if save_mode == REPLACE:
            if paths.inside(paths.temp_dir(), src):
                raise ValueError("Album Cover: refusing to replace a file in the temp folder; save a copy instead")
            scratch = unique_path(os.path.dirname(src), f".{stem}.cover", ext)
            try:
                embed_cover(src, scratch, cover, tags)
                os.replace(scratch, src)
            finally:
                if os.path.exists(scratch):
                    os.remove(scratch)
            dest = src
        else:
            folder = os.path.join(paths.output_dir(), *safe_prefix(filename_prefix).split("/")) if safe_prefix(filename_prefix) else paths.output_dir()
            dest = unique_path(folder, stem, ext)
            embed_cover(src, dest, cover, tags)
        return io.NodeOutput(dest, ui={"text": [f"cover embedded: {dest}"]})


NODES = [JWTFAlbumCover]
