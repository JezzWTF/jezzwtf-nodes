"""Synchronized A/B video comparison preview node.

Saves both videos to the ComfyUI temp directory as lightweight preview MP4s
(the same trick ComfyUI core uses for video previews) and hands them to a
frontend widget that plays them frame-locked with a draggable wipe slider.
"""
import os
from fractions import Fraction

import folder_paths

try:
    from comfy_api.latest import InputImpl, Types

    _HAS_COMFY_API = True
except ImportError:  # ComfyUI without the native VIDEO type / comfy_api package
    _HAS_COMFY_API = False


class VideoCompare:
    TITLE = "Video Compare"
    CATEGORY = "JezzWTF/video"
    DESCRIPTION = (
        "Synchronized A/B comparison of two videos in the UI. Play both side-by-side, "
        "wipe between them with a slider, or view the difference blend — useful for "
        "checking body/scene swap results against the original."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "video_a": ("VIDEO", {"tooltip": "Reference video, usually the original source (shown left/top)."}),
                "video_b": ("VIDEO", {"tooltip": "Result video to compare against A (shown right/bottom)."}),
                "image_a": ("IMAGE", {
                    "tooltip": "Fallback for A when the pipeline only outputs frames (e.g. VHS or Wan decode). Ignored while video_a is connected.",
                }),
                "image_b": ("IMAGE", {
                    "tooltip": "Fallback for B when the pipeline only outputs frames (e.g. VHS or Wan decode). Ignored while video_b is connected.",
                }),
                "frame_rate": ("FLOAT", {
                    "default": 16.0,
                    "min": 1.0,
                    "max": 120.0,
                    "step": 0.5,
                    "tooltip": "Frame rate used only when building a video from IMAGE fallback inputs.",
                }),
                "b_offset": ("FLOAT", {
                    "default": 0.0,
                    "min": -1000.0,
                    "max": 1000.0,
                    "step": 0.001,
                    "tooltip": "Seconds to shift B against A: B plays at A's time + offset (positive skips into B, negative delays it).",
                }),
                "audio_a": ("AUDIO", {
                    "tooltip": "Audio mixed into the preview when A is built from IMAGE frames. Ignored while video_a is connected.",
                }),
                "audio_b": ("AUDIO", {
                    "tooltip": "Audio mixed into the preview when B is built from IMAGE frames. Ignored while video_b is connected.",
                }),
                "filename_prefix": ("STRING", {"default": "videoCompare"}),
            },
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "compare"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Always re-run: this is a live preview, not a cacheable output.
        return float("NaN")

    def _materialize(self, video, image, audio, frame_rate: float, tag: str):
        """Prefer the connected VIDEO, else build one from IMAGE frames (+ optional audio)."""
        if video is not None:
            return video
        if image is None:
            raise ValueError(
                f"Video Compare: input '{tag.lower()}' needs either a VIDEO connection "
                f"or IMAGE frames on image_{tag.lower()} — neither is connected."
            )
        return InputImpl.VideoFromComponents(
            Types.VideoComponents(images=image, audio=audio, frame_rate=Fraction(frame_rate).limit_denominator(1001))
        )

    def compare(self, video_a=None, video_b=None, image_a=None, image_b=None, audio_a=None, audio_b=None,
                frame_rate=16.0, b_offset=0.0, filename_prefix="videoCompare"):
        if not _HAS_COMFY_API:
            raise RuntimeError(
                "Video Compare needs a recent ComfyUI with the comfy_api package "
                "(native VIDEO type). Please update ComfyUI."
            )

        source_a = self._materialize(video_a, image_a, audio_a, frame_rate, "A")
        source_b = self._materialize(video_b, image_b, audio_b, frame_rate, "B")

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
        return {
            "ui": {
                "comparisons": [{
                    "a": A,
                    "b": B,
                    "width": int(width),
                    "height": int(height),
                    "b_offset": float(b_offset),
                    "fps": fps,
                }],
            },
            "result": (),
        }
