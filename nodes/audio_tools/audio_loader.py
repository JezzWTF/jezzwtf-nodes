"""Audio Loader: pick (or upload) an audio file from the input folder, with optional trim and mono mix."""
from __future__ import annotations

import os

import av
import numpy as np
import torch
from comfy_api.latest import io

from . import paths

MAX_SECONDS = 36000.0
NO_AUDIO = "(no audio in input)"


def decode_audio(path: str) -> tuple[np.ndarray, int]:
    """Decode the first audio stream to float32 samples shaped (channels, samples) at its native rate."""
    chunks: list[np.ndarray] = []
    with av.open(path) as container:
        if not container.streams.audio:
            raise ValueError(f"{os.path.basename(path)} has no audio stream")
        stream = container.streams.audio[0]
        rate = int(stream.rate or stream.codec_context.sample_rate)
        resampler = av.AudioResampler(format="fltp", layout=stream.layout.name, rate=rate)
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray())
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray())
    if not chunks:
        raise ValueError(f"{os.path.basename(path)} decoded to no audio")
    return np.concatenate(chunks, axis=1).astype(np.float32, copy=False), rate


def trim(samples: np.ndarray, rate: int, start: float, length: float) -> np.ndarray:
    first = min(int(max(0.0, start) * rate), samples.shape[1])
    last = samples.shape[1] if length <= 0 else min(samples.shape[1], first + int(length * rate))
    return samples[:, first:last]


def to_mono(samples: np.ndarray) -> np.ndarray:
    return samples.mean(axis=0, keepdims=True) if samples.shape[0] > 1 else samples


class JWTFAudioLoader(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFAudioLoader",
            display_name="Audio Loader",
            category="JezzWTF/audio",
            description="Load an audio file from the input folder (subfolders included) with optional start, length and mono mix.",
            inputs=[
                io.Combo.Input("audio", options=paths.list_audio() or [NO_AUDIO], tooltip="Audio file selected from ComfyUI's input folder, including subfolders, unless an explicit path overrides it."),  # upload and preview are added by js/audio_tools
                io.Float.Input("start", default=0.0, min=0.0, max=MAX_SECONDS, step=0.01, optional=True, tooltip="Seconds to skip from the start."),
                io.Float.Input("length", default=0.0, min=0.0, max=MAX_SECONDS, step=0.01, optional=True, tooltip="Seconds to keep; 0 = the rest of the file."),
                io.Boolean.Input("mono", default=False, optional=True, tooltip="Mix all channels down to one."),
                io.String.Input("path", default="", optional=True, tooltip="Optional file path (input, output or temp folder). Overrides the picker."),
            ],
            outputs=[
                io.Audio.Output("audio", tooltip="Decoded audio after trimming and any mono mixdown."),
                io.Float.Output("duration", tooltip="Length of the returned audio in seconds after trimming."),
                io.Int.Output("sample_rate", tooltip="Sample rate of the returned waveform in samples per second."),
                io.String.Output("file_path", tooltip="Resolved path to the original audio file, suitable for passing to Album Cover."),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, audio: str = "", start: float = 0.0, length: float = 0.0, mono: bool = False, path: str = "") -> str:
        try:
            real = paths.resolve_audio((path or "").strip() or audio)
            stat = os.stat(real)
            return f"{real}:{stat.st_mtime_ns}:{stat.st_size}:{start}:{length}:{mono}"
        except (ValueError, OSError):
            return "missing"

    @classmethod
    def validate_inputs(cls, audio: str = "", path: str = "", **_: object) -> bool | str:
        chosen = (path or "").strip() or audio
        if not chosen or chosen == NO_AUDIO:
            return "Audio Loader: pick an audio file or give a path."
        try:
            paths.resolve_audio(chosen)
        except (ValueError, OSError) as exc:
            return f"Audio Loader: {exc}"
        return True

    @classmethod
    def execute(cls, audio: str, start: float = 0.0, length: float = 0.0, mono: bool = False, path: str = "") -> io.NodeOutput:
        real = paths.resolve_audio((path or "").strip() or audio)
        samples, rate = decode_audio(real)
        samples = trim(samples, rate, float(start), float(length))
        if samples.shape[1] == 0:
            raise ValueError("Audio Loader: start is past the end of the file")
        if mono:
            samples = to_mono(samples)
        waveform = torch.from_numpy(np.ascontiguousarray(samples)).unsqueeze(0)
        return io.NodeOutput({"waveform": waveform, "sample_rate": rate}, waveform.shape[-1] / rate, rate, real)


NODES = [JWTFAudioLoader]
