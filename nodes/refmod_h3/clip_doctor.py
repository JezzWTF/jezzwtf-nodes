"""H3 preflight checks with explicit repairs to accompanying decoded media."""
from __future__ import annotations

import json
import math

import torch
import torch.nn.functional as F
from comfy_api.latest import io


def inspect_clip(latent: dict, images: torch.Tensor | None = None, audio: dict | None = None,
                 auto_fix: bool = False, target_fps: float = 24, spatial_compression: int = 16) -> tuple[dict, object, object, list[dict]]:
    if not math.isfinite(target_fps) or target_fps <= 0 or spatial_compression < 1:
        raise ValueError("FPS and spatial compression must be positive")
    out = dict(latent)
    samples = out.get("samples")
    nested = bool(getattr(samples, "is_nested", False))
    parts = list(samples.unbind()) if nested else [samples]
    video = parts[0]
    checks: list[dict] = []
    def check(name, ok, detail, severity="error"):
        checks.append({"name": name, "status": "ok" if ok else severity, "detail": detail})
    if not isinstance(video, torch.Tensor) or video.ndim != 5 or min(video.shape) < 1:
        check("Video latent", False, "Expected non-empty [B,24,T,H,W] H3 video samples")
        return out, images, audio, checks
    batch, channels, time, height, width = video.shape
    check("Video channels", channels == 24 or (not nested and channels == 32),
          f"{channels} channels; H3 expects 24 for video or a plain 32-channel AV placeholder")
    if not nested and channels == 32:
        check("AV placeholder", False, "The H3 sampler expands this 32-channel placeholder into video/audio streams", "warning")
    check("Batch size", batch == 1, f"{batch}; H3 expects one video per latent")
    check("Finite samples", bool(torch.isfinite(video).all()), "Latents must contain no NaN or infinity")
    legal_time = time == 1 or (time >= 2 and (time - 2) % 5 == 0)
    frames = 1 if time == 1 else max(1, (time - 2) // 5 * 17 + 5)
    check("Frame grid", legal_time, f"T={time} → {frames} pixel frames; H3 maps 5k+2 latent frames to 17k+5 pixel frames (or 1→1 for a still)")
    if not legal_time:
        return out, images, audio, checks
    check("Pixel size", True, f"{width * spatial_compression}×{height * spatial_compression}; compression {spatial_compression}")
    if nested:
        check("Audio latent", len(parts) == 2, f"{len(parts)} nested streams; expected video and audio")
    fps = out.get("frame_rate", target_fps)
    ok = isinstance(fps, (int, float)) and math.isfinite(fps) and abs(fps - target_fps) < 0.001
    check("Frame rate", ok, f"{fps} fps; target {target_fps}")
    if not ok and auto_fix:
        out["frame_rate"] = target_fps
        checks[-1]["status"] = "fixed"
    if images is not None:
        if images.ndim != 4 or images.shape[0] < 1:
            check("Decoded images", False, "Expected non-empty [frames,height,width,channels]")
        else:
            correct = images.shape[:3] == (frames, height * spatial_compression, width * spatial_compression)
            check("Decoded images", correct, f"{list(images.shape[:3])}; expected [{frames}, {height * spatial_compression}, {width * spatial_compression}]")
            if not correct and auto_fix:
                # The latent is authoritative. Never resize or invent encoded reference latents.
                images = images[torch.arange(frames, device=images.device).clamp(max=images.shape[0] - 1)]
                if images.shape[1:3] != (height * spatial_compression, width * spatial_compression):
                    images = F.interpolate(images.movedim(-1, 1), size=(height * spatial_compression, width * spatial_compression), mode="bilinear", align_corners=False).movedim(1, -1)
                checks[-1]["status"] = "fixed"
    if audio is not None:
        waveform, rate = audio.get("waveform"), audio.get("sample_rate")
        if not isinstance(waveform, torch.Tensor) or waveform.ndim != 3 or not isinstance(rate, (int, float)) or rate <= 0:
            check("Decoded audio", False, "Expected waveform [batch,channels,samples] and a positive sample rate")
        else:
            wanted = round(frames / target_fps * rate)
            correct = abs(waveform.shape[-1] - wanted) <= round(rate / target_fps)
            check("Audio duration", correct, f"{waveform.shape[-1] / rate:.3f}s; video {frames / target_fps:.3f}s")
            if not correct and auto_fix:
                audio = dict(audio)
                audio["waveform"] = F.pad(waveform[..., :wanted], (0, max(0, wanted - waveform.shape[-1])))
                checks[-1]["status"] = "fixed"
    return out, images, audio, checks


class JWTFH3ClipDoctor(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFH3ClipDoctor", display_name="H3 Clip Doctor", category="JezzWTF/refmod",
            description="Check H3 video/AV latents before sampling or export. The latent is authoritative: optional repairs resize/trim/pad decoded media and correct FPS metadata, never invent encoded audio or resize latent samples.",
            inputs=[io.Latent.Input("latent"), io.Boolean.Input("auto_fix", default=False),
                    io.Boolean.Input("strict", default=True, tooltip="Raise if any hard check still fails."),
                    io.Float.Input("target_fps", default=24, min=1, max=240),
                    io.Int.Input("spatial_compression", default=16, min=1, max=128, tooltip="Pixel dimensions per latent grid cell; match the H3 VAE."),
                    io.Image.Input("images", optional=True), io.Audio.Input("audio", optional=True)],
            outputs=[io.Latent.Output("latent"), io.Image.Output("images"), io.Audio.Output("audio"), io.String.Output("report")], is_output_node=True,
        )

    @classmethod
    def execute(cls, latent: dict, auto_fix: bool = False, strict: bool = True, target_fps: float = 24,
                spatial_compression: int = 16, images=None, audio=None) -> io.NodeOutput:
        result, images, audio, checks = inspect_clip(latent, images, audio, auto_fix, target_fps, spatial_compression)
        errors = [f"{c['name']}: {c['detail']}" for c in checks if c["status"] == "error"]
        if strict and errors:
            raise ValueError("H3 Clip Doctor: " + "; ".join(errors))
        report = json.dumps(checks, indent=2)
        return io.NodeOutput(result, images, audio, report, ui={"text": [report], "jwtf_clip_checks": checks})


NODES = [JWTFH3ClipDoctor]
