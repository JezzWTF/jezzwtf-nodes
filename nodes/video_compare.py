"""Synchronized A/B video comparison preview node.

Saves both videos to the ComfyUI temp directory as lightweight preview MP4s
(the same trick ComfyUI core uses for video previews) and hands them to a
frontend widget that plays them frame-locked with a draggable wipe slider.
"""
from __future__ import annotations

import os
from fractions import Fraction

import folder_paths
import torch
from comfy_api.latest import InputImpl, Types, io


def even_dimensions(image: torch.Tensor) -> torch.Tensor:
    """Pad an IMAGE batch [B, H, W, C] by one edge row/column where needed so H and W are even.

    The preview is encoded as H.264 in yuv420p, which libx264 refuses to open for an odd width
    or height (a 508x337 GIF, for example). Replicating the edge keeps every original pixel.
    """
    height, width = int(image.shape[1]), int(image.shape[2])
    if height % 2:
        image = torch.cat([image, image[:, -1:, :, :]], dim=1)
    if width % 2:
        image = torch.cat([image, image[:, :, -1:, :]], dim=2)
    return image


class VideoCompare(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="VideoCompare",
            display_name='Video Compare',
            category='JezzWTF/video',
            description='Synchronized A/B comparison of two videos in the UI. Play both side-by-side, wipe between them with a slider, or view the difference blend — useful for checking body/scene swap results against the original.',
            inputs=[
                io.Video.Input("video_a", optional=True, tooltip='Reference video, usually the original source (shown left/top).'),
                io.Video.Input("video_b", optional=True, tooltip='Result video to compare against A (shown right/bottom).'),
                io.Image.Input("image_a", optional=True, tooltip='Fallback for A when the pipeline only outputs frames (e.g. VHS or Wan decode). Ignored while video_a is connected.'),
                io.Image.Input("image_b", optional=True, tooltip='Fallback for B when the pipeline only outputs frames (e.g. VHS or Wan decode). Ignored while video_b is connected.'),
                io.Float.Input("frame_rate", default=16.0, min=1.0, max=120.0, step=0.5, optional=True, tooltip='Frame rate used only when building a video from IMAGE fallback inputs.'),
                io.Float.Input("b_offset", default=0.0, min=-1000.0, max=1000.0, step=0.001, optional=True, tooltip="Seconds to shift B against A: B plays at A's time + offset (positive skips into B, negative delays it)."),
                io.Audio.Input("audio_a", optional=True, tooltip='Audio mixed into the preview when A is built from IMAGE frames. Ignored while video_a is connected.'),
                io.Audio.Input("audio_b", optional=True, tooltip='Audio mixed into the preview when B is built from IMAGE frames. Ignored while video_b is connected.'),
                io.String.Input("filename_prefix", default='videoCompare', optional=True),
            ],
            outputs=[],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **_: object) -> float:
        # Always re-run: this is a live preview, not a cacheable output.
        return float("NaN")

    @staticmethod
    def _materialize(video: object | None, image: torch.Tensor | None, audio: object | None,
                     frame_rate: float, tag: str) -> object:
        """Prefer the connected VIDEO, else build one from IMAGE frames (+ optional audio)."""
        if video is not None:
            return video
        if image is None:
            raise ValueError(
                f"Video Compare: input '{tag.lower()}' needs either a VIDEO connection "
                f"or IMAGE frames on image_{tag.lower()} — neither is connected."
            )
        return InputImpl.VideoFromComponents(
            Types.VideoComponents(images=even_dimensions(image), audio=audio,
                                  frame_rate=Fraction(frame_rate).limit_denominator(1001))
        )

    @classmethod
    def execute(cls, video_a: object | None = None, video_b: object | None = None,
                image_a: torch.Tensor | None = None, image_b: torch.Tensor | None = None,
                audio_a: object | None = None, audio_b: object | None = None, frame_rate: float = 16.0,
                b_offset: float = 0.0, filename_prefix: str = "videoCompare") -> io.NodeOutput:
        source_a = cls._materialize(video_a, image_a, audio_a, frame_rate, "A")
        source_b = cls._materialize(video_b, image_b, audio_b, frame_rate, "B")

        out_dir, base, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix, folder_paths.get_temp_directory(), 0, 0
        )
        width, height = source_a.get_dimensions()
        try:
            fps = float(source_a.get_frame_rate())
        except Exception:
            fps = float(frame_rate)

        saved = {}
        for tag, source in (("a", source_a), ("b", source_b)):
            file = f"{base}_{tag}_{counter:05}_.mp4"
            source.save_to(
                os.path.join(out_dir, file),
                format=Types.VideoContainer.MP4,
                codec="auto",
                preset="ultrafast",
            )
            saved[tag] = {"filename": file, "subfolder": subfolder, "type": "temp"}

        A, B = saved["a"], saved["b"]
        return io.NodeOutput(ui={
                "comparisons": [{
                    "a": A,
                    "b": B,
                    "width": int(width),
                    "height": int(height),
                    "b_offset": float(b_offset),
                    "fps": fps,
                }],
            })


NODES = [VideoCompare]
