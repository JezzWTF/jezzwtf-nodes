import wave
import asyncio
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from aiohttp import web

from audio_tools import waveform
from audio_tools.waveform import envelope


def test_waveform_envelope_decodes_duration_and_normalises_peaks(tmp_path):
    path = tmp_path / "tone.wav"
    sample_rate = 16000
    signal = (np.sin(np.arange(sample_rate) * 2 * np.pi * 440 / sample_rate) * 15000).astype("int16")
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(signal.tobytes())
    stat = path.stat()
    result = envelope(str(path), stat.st_mtime_ns, stat.st_size)
    assert abs(result["duration"] - 1) < 0.01
    assert 0 < len(result["peaks"]) <= 1024
    assert max(result["peaks"]) == 1 and min(result["peaks"]) >= 0


def test_silent_waveform_is_finite(tmp_path):
    path = tmp_path / "silence.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(bytes(16000))
    result = envelope(str(path), 0, path.stat().st_size)
    assert all(p == 0 for p in result["peaks"])


def test_opposite_phase_stereo_is_visible_and_long_files_have_bounded_columns(tmp_path):
    path = tmp_path / "stereo.wav"
    signal = (np.sin(np.arange(8000 * 30) * 2 * np.pi * 440 / 8000) * 15000).astype("int16")
    stereo = np.stack([signal, -signal], axis=1)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(stereo.tobytes())
    result = envelope(str(path), 0, path.stat().st_size)
    assert len(result["peaks"]) <= 1024 and max(result["peaks"]) == 1
    assert abs(result["duration"] - 30) < 0.01


def test_audio_preview_routes_resolve_paths_and_reject_nonlocal_requests(monkeypatch, tmp_path):
    handlers = {}
    class Routes:
        def get(self, path):
            def register(fn):
                handlers[path] = fn
                return fn
            return register
    server = SimpleNamespace(routes=Routes())
    monkeypatch.setitem(sys.modules, "server", SimpleNamespace(PromptServer=SimpleNamespace(instance=server)))
    path = tmp_path / "tone.wav"
    path.write_bytes(b"fixture")
    chosen = []
    def resolve(value):
        chosen.append(value)
        return str(path)
    monkeypatch.setattr(waveform, "resolve_audio", resolve)
    waveform.register_routes()
    waveform.register_routes()  # registration is idempotent
    request = SimpleNamespace(remote="127.0.0.1", headers={"Host": "localhost:8188"}, query={"file": "output/audio/tone.wav"})
    result = asyncio.run(handlers["/jezzwtf/audio/source"](request))
    assert isinstance(result, web.FileResponse) and chosen == ["output/audio/tone.wav"]
    request.remote = "192.168.1.2"
    with pytest.raises(web.HTTPForbidden):
        asyncio.run(handlers["/jezzwtf/audio/source"](request))
    assert len(chosen) == 1
