"""Local audio previews and bounded waveform envelopes; honours the loader's path override."""
from __future__ import annotations

import asyncio
import os
from functools import lru_cache

import av
import numpy as np

from .paths import resolve_audio


@lru_cache(maxsize=16)
def envelope(path: str, modified: int, size: int) -> dict[str, object]:
    del modified, size  # cache identity includes file replacement, not just its name
    # Decode at low rate, taking the loudest channel so opposite-phase stereo cannot cancel.
    # Merge adjacent peak buckets as the file grows; memory stays bounded for long recordings.
    peaks: list[float] = []
    count = 0
    bucket_width, bucket_count, bucket_peak = 1, 0, 0.0
    with av.open(path) as container:
        if not container.streams.audio:
            raise ValueError("No audio stream")
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="fltp", layout=stream.layout.name, rate=8000, frame_size=80)
        def collect(frame):
            nonlocal count, peaks, bucket_width, bucket_count, bucket_peak
            for out in resampler.resample(frame):
                values = out.to_ndarray()
                count += values.shape[-1]
                bucket_peak = max(bucket_peak, float(np.abs(values).max()))
                bucket_count += 1
                if bucket_count >= bucket_width:
                    peaks.append(bucket_peak)
                    bucket_count, bucket_peak = 0, 0.0
                    if len(peaks) >= 2048:
                        peaks = [max(peaks[i:i + 2]) for i in range(0, len(peaks), 2)]
                        bucket_width *= 2
        for frame in container.decode(stream):
            collect(frame)
        collect(None)
    if bucket_count:
        peaks.append(bucket_peak)
    if not peaks or count == 0:
        raise ValueError("No audio samples")
    columns = [float(np.max(p)) for p in np.array_split(np.asarray(peaks), min(1024, len(peaks))) if len(p)]
    maximum = max(columns) or 1
    return {"duration": count / 8000, "peaks": [p / maximum for p in columns]}


def register_routes() -> None:
    from aiohttp import web
    try:
        from server import PromptServer
        instance = PromptServer.instance
    except Exception:  # noqa: BLE001 - outside ComfyUI, or its server module cannot load
        return
    if instance is None or getattr(instance, "_jwtf_audio_waveform", False):
        return
    try:
        from ..utility_core._comfy import is_loopback_request
    except ImportError:
        from utility_core._comfy import is_loopback_request

    def resolve(request):
        if not is_loopback_request(request.remote, request.headers.get("Host")):
            raise web.HTTPForbidden()
        try:
            return resolve_audio(request.query.get("file", ""))
        except (ValueError, OSError) as error:
            raise web.HTTPBadRequest(text=str(error)) from error

    @instance.routes.get("/jezzwtf/audio/source")
    async def source(request):
        return web.FileResponse(resolve(request))

    @instance.routes.get("/jezzwtf/audio/waveform")
    async def waveform(request):
        path = resolve(request)
        info = os.stat(path)
        try:
            return web.json_response(await asyncio.to_thread(envelope, path, info.st_mtime_ns, info.st_size))
        except (ValueError, av.error.FFmpegError) as error:
            raise web.HTTPBadRequest(text=str(error)) from error
    instance._jwtf_audio_waveform = True
