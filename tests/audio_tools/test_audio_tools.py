from __future__ import annotations

import os
from pathlib import Path

import av
import numpy as np
import pytest
import torch
from audio_tools import NODES, album_cover, audio_loader, paths
from audio_tools.album_cover import JWTFAlbumCover, REPLACE, SAVE_COPY, embed_cover, read_cover, safe_prefix, tensor_to_cover
from audio_tools.audio_loader import JWTFAudioLoader, decode_audio, to_mono, trim
from v3_helpers import legacy, overrides

CODECS = {".mp3": "libmp3lame", ".flac": "flac", ".m4a": "aac"}


def make_audio(path: str, seconds: float = 1.0, rate: int = 44100, channels: int = 2) -> None:
    layout = "stereo" if channels == 2 else "mono"
    with av.open(path, "w") as out:
        stream = out.add_stream(CODECS[os.path.splitext(path)[1]], rate=rate)
        stream.layout = layout
        t = np.arange(int(rate * seconds)) / rate
        tone = (np.sin(2 * np.pi * 440 * t) * 0.3).astype(np.float32)
        frame = av.AudioFrame.from_ndarray(np.stack([tone] * channels), format="fltp", layout=layout)
        frame.sample_rate = rate
        for packet in stream.encode(frame):
            out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)


@pytest.fixture()
def dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    d = {name: str(tmp_path / name) for name in ("input", "output", "temp")}
    for p in d.values():
        os.makedirs(p)
    monkeypatch.setattr(paths, "input_dir", lambda: d["input"])
    monkeypatch.setattr(paths, "output_dir", lambda: d["output"])
    monkeypatch.setattr(paths, "temp_dir", lambda: d["temp"])
    return d


def test_family_exports_both_nodes() -> None:
    assert [n.GET_SCHEMA().node_id for n in NODES] == ["JWTFAudioLoader", "JWTFAlbumCover"]
    assert all(n.GET_SCHEMA().category == "JezzWTF/audio" for n in NODES)


def test_list_audio_is_recursive_sorted_and_filtered(dirs: dict[str, str]) -> None:
    for rel in ("b.mp3", "a.flac", "sub/c.wav", "sub/deep/d.m4a", "notes.txt", "a/b/c/d/e/too_deep.mp3"):
        full = os.path.join(dirs["input"], *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "wb").close()
    assert paths.list_audio() == ["a.flac", "b.mp3", "sub/c.wav", "sub/deep/d.m4a"]


def test_resolve_audio_stays_inside_the_known_folders(dirs: dict[str, str], tmp_path: Path) -> None:
    inside = os.path.join(dirs["input"], "x.mp3")
    open(inside, "wb").close()
    outside = tmp_path / "elsewhere.mp3"
    outside.write_bytes(b"")
    assert paths.resolve_audio("x.mp3") == os.path.realpath(inside)
    assert paths.resolve_audio(inside) == os.path.realpath(inside)
    with pytest.raises(ValueError, match="only be read"):
        paths.resolve_audio(str(outside))
    with pytest.raises(FileNotFoundError):
        paths.resolve_audio("missing.mp3")
    with pytest.raises(ValueError):
        paths.resolve_audio("  ")


def test_trim_and_mono_maths() -> None:
    samples = np.arange(20, dtype=np.float32).reshape(2, 10)
    assert trim(samples, 10, 0.0, 0.0).shape == (2, 10)
    assert trim(samples, 10, 0.2, 0.3).shape == (2, 3)
    assert trim(samples, 10, 5.0, 0.0).shape == (2, 0)
    assert np.allclose(to_mono(samples), samples.mean(axis=0, keepdims=True))
    assert to_mono(samples[:1]).shape == (1, 10)


@pytest.mark.parametrize("ext", [".mp3", ".flac", ".m4a"])
def test_decode_round_trip(dirs: dict[str, str], ext: str) -> None:
    path = os.path.join(dirs["input"], f"tone{ext}")
    make_audio(path, seconds=0.5)
    samples, rate = decode_audio(path)
    assert rate == 44100 and samples.shape[0] == 2 and abs(samples.shape[1] / rate - 0.5) < 0.1
    assert float(np.abs(samples).max()) > 0.1


def test_loader_outputs_trim_mono_and_path(dirs: dict[str, str]) -> None:
    path = os.path.join(dirs["input"], "tone.flac")
    make_audio(path, seconds=1.0)
    out = legacy(JWTFAudioLoader.execute("tone.flac", start=0.25, length=0.5, mono=True))
    audio, duration, rate, file_path = out
    assert audio["waveform"].shape[:2] == (1, 1) and rate == 44100 and audio["sample_rate"] == 44100
    assert duration == pytest.approx(0.5, abs=0.01) and file_path == os.path.realpath(path)
    with pytest.raises(ValueError, match="past the end"):
        JWTFAudioLoader.execute("tone.flac", start=5.0)


def test_loader_validation_and_fingerprint(dirs: dict[str, str]) -> None:
    path = os.path.join(dirs["input"], "tone.mp3")
    make_audio(path)
    assert JWTFAudioLoader.validate_inputs("tone.mp3") is True
    assert "pick an audio file" in JWTFAudioLoader.validate_inputs(audio_loader.NO_AUDIO)
    assert "not found" in JWTFAudioLoader.validate_inputs("gone.mp3")
    before = JWTFAudioLoader.fingerprint_inputs("tone.mp3")
    os.utime(path, (1, 1))
    assert JWTFAudioLoader.fingerprint_inputs("tone.mp3") != before
    assert JWTFAudioLoader.fingerprint_inputs("gone.mp3") == "missing"
    assert overrides(JWTFAudioLoader, "fingerprint_inputs")


def test_cover_conversion_scales_down_only() -> None:
    from PIL import Image
    from io import BytesIO

    big = torch.rand(2, 600, 400, 3)
    jpeg = tensor_to_cover(big, 1, 300)
    assert Image.open(BytesIO(jpeg)).size == (200, 300)
    assert Image.open(BytesIO(tensor_to_cover(big, 0, 0))).size == (400, 600)
    assert Image.open(BytesIO(tensor_to_cover(torch.rand(1, 50, 80, 3), 0, 1000))).size == (80, 50)
    assert Image.open(BytesIO(tensor_to_cover(torch.rand(1, 10, 10, 1), 9, 0))).size == (10, 10)


@pytest.mark.parametrize("ext", [".mp3", ".flac", ".m4a"])
def test_embed_cover_keeps_audio_and_adds_the_picture(dirs: dict[str, str], ext: str) -> None:
    src = os.path.join(dirs["input"], f"song{ext}")
    dst = os.path.join(dirs["output"], f"song_cover{ext}")
    make_audio(src, seconds=0.5)
    jpeg = tensor_to_cover(torch.rand(1, 64, 64, 3), 0, 0)
    embed_cover(src, dst, jpeg, {"title": "Tone", "artist": "", "album": "Sines"})
    assert read_cover(dst) == jpeg and read_cover(src) is None
    original, rate = decode_audio(src)
    tagged, rate2 = decode_audio(dst)
    assert rate == rate2 and abs(original.shape[1] - tagged.shape[1]) < 2400
    with av.open(dst) as container:
        meta = {k.lower(): v for k, v in container.metadata.items()}
    assert meta.get("title") == "Tone" and meta.get("album") == "Sines" and "artist" not in meta


def test_embed_cover_rejects_unsupported_containers(dirs: dict[str, str]) -> None:
    src = os.path.join(dirs["input"], "song.mp3")
    make_audio(src, seconds=0.2)
    with pytest.raises(ValueError, match="cover art can be embedded"):
        embed_cover(src, os.path.join(dirs["output"], "song.wav"), b"x")


def test_node_saves_a_copy_and_never_overwrites(dirs: dict[str, str]) -> None:
    src = os.path.join(dirs["input"], "song.mp3")
    make_audio(src, seconds=0.3)
    image = torch.rand(1, 32, 32, 3)
    first = legacy(JWTFAlbumCover.execute(image, "song.mp3", SAVE_COPY, "covers/../x", 0))
    second = legacy(JWTFAlbumCover.execute(image, "song.mp3", SAVE_COPY, "covers/../x", 0))
    assert first["result"][0] != second["result"][0]
    assert os.path.dirname(first["result"][0]) == os.path.join(dirs["output"], "covers", "x")
    assert os.path.basename(second["result"][0]) == "song_001.mp3"
    assert read_cover(first["result"][0]) is not None and read_cover(src) is None


def test_node_replace_updates_in_place_without_leftovers(dirs: dict[str, str]) -> None:
    src = os.path.join(dirs["input"], "song.flac")
    make_audio(src, seconds=0.3)
    out = legacy(JWTFAlbumCover.execute(torch.rand(1, 32, 32, 3), "song.flac", REPLACE, title="T"))
    assert out["result"][0] == os.path.realpath(src) and read_cover(src) is not None
    assert os.listdir(dirs["input"]) == ["song.flac"]


def test_node_refuses_to_replace_in_temp(dirs: dict[str, str]) -> None:
    src = os.path.join(dirs["temp"], "t.mp3")
    make_audio(src, seconds=0.2)
    with pytest.raises(ValueError, match="temp folder"):
        JWTFAlbumCover.execute(torch.rand(1, 16, 16, 3), src, REPLACE)


def test_safe_prefix_drops_escapes() -> None:
    assert safe_prefix("a/../b\\c/./d") == "a/b/c/d"
    assert safe_prefix("C:/evil") == "evil"
    assert safe_prefix("") == "" and album_cover.safe_prefix("..") == ""
