"""Visual / audio extraction: H3 grid snapping, canvas, budget fitting, folder loading, sidecars."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import torch
from PIL import Image

from fakes import FakeAudioVAE, FakeH3VideoVAE
from refmod_h3 import extract
from refmod_h3._types import RefModError


def img(h: int = 64, w: int = 96, v: float = 0.5) -> torch.Tensor:
    return torch.full((1, h, w, 3), v)


def test_grid_helpers() -> None:
    assert [extract.valid_len(n) for n in (1, 4, 5, 21, 22, 23, 39, 40)] == [5, 5, 5, 5, 22, 22, 39, 39]
    assert [extract.snap_h3(n) for n in (1, 4, 5, 16, 22, 39)] == [1, 1, 5, 5, 22, 39]
    assert extract.round32(10) == 32 and extract.round32(1000) == 992


def test_sample_clip_default_cap_snaps_to_five_frames_keeping_endpoints() -> None:
    clip = torch.arange(100, dtype=torch.float32).view(100, 1, 1, 1).expand(100, 2, 2, 3)
    out = extract.sample_clip(clip, extract.VIDEO_FRAME_CAP)
    assert out.shape[0] == 5
    assert float(out[0, 0, 0, 0]) == 0.0 and float(out[-1, 0, 0, 0]) == 99.0
    assert extract.sample_clip(clip[:3], 16).shape[0] == 1  # below 5 frames a clip is one frame
    assert extract.sample_clip(clip, 40).shape[0] == 39


def test_normalise_frames_layouts() -> None:
    assert extract.normalise_frames(torch.rand(8, 8, 3), "x").shape == (1, 8, 8, 3)
    assert extract.normalise_frames(torch.rand(2, 8, 8, 3), "x").shape == (2, 8, 8, 3)
    assert extract.normalise_frames(torch.rand(1, 3, 8, 8, 3), "x").shape == (3, 8, 8, 3)
    assert extract.normalise_frames(torch.rand(1, 3, 8, 8), "x").shape == (1, 8, 8, 3)
    assert extract.normalise_frames(torch.rand(1, 8, 8, 4), "x").shape[-1] == 3
    with pytest.raises(RefModError):
        extract.normalise_frames(torch.rand(4), "x")


def test_size_helpers() -> None:
    assert extract.down_only_size(1024, 2048, 512) == (1024, 512)
    assert extract.down_only_size(200, 300, 1024) == (288, 192)  # never upscales
    assert extract.min_size(200, 100) == (640, 320)
    assert extract.min_size(640, 480) == (640, 480)
    assert extract.shared_canvas(100, 200, 1024) == (192, 96)


def test_make_visual_single_image_and_ref_resolution_is_honoured() -> None:
    vae = FakeH3VideoVAE()
    mod = extract.make_visual("m", vae, {"ref_image_1": img(1024, 1024)}, {}, [], ref_resolution=512)
    assert mod.kind == "image" and mod.latent.dtype == torch.float16
    assert tuple(mod.latent.shape) == (1, 24, 1, 32, 32)  # 512 px / 16, user value passed through
    assert vae.calls == [(1, 512, 512)]
    assert mod.source == "image" and mod.tags == ["1 img, 0 vid"] and "8192" not in mod.pool
    tiny = extract.make_visual("t", FakeH3VideoVAE(), {"ref_image_1": img(100, 100)}, {}, [], ref_resolution=1024)
    assert tuple(tiny.latent.shape[3:]) == (20, 20)  # lifted to the 320 px minimum


def test_make_visual_video_clip_becomes_five_frames_and_stack_uses_shared_canvas() -> None:
    vae = FakeH3VideoVAE()
    clip = torch.rand(60, 256, 256, 3)
    mod = extract.make_visual("m", vae, {"ref_image_1": img(512, 512)}, {"ref_video_1": clip}, [], ref_resolution=512)
    assert mod.kind == "video" and mod.latent.shape[2] == 1 + 5
    assert mod.source == "stack" and mod.tags == ["1 img, 1 vid"] and mod.source_shape.count("x") >= 4
    assert {(h, w) for _, h, w in vae.calls} == {(512, 512)}
    only_clip = extract.make_visual("c", FakeH3VideoVAE(), {}, {"ref_video_1": clip}, [])
    assert only_clip.latent.shape[2] == 5
    uncapped = extract.make_visual("c", FakeH3VideoVAE(), {}, {"ref_video_1": clip}, [], video_cap=22)
    assert uncapped.latent.shape[2] == 22


def test_sources_are_ordered_by_numeric_suffix() -> None:
    srcs = extract.order_sources({"ref_image_10": img(v=0.1), "ref_image_2": img(v=0.2)},
                                 {"ref_video_1": torch.rand(3, 8, 8, 3)}, [img(v=0.9)])
    assert [s.kind for s in srcs] == ["image", "image", "video", "image"]
    assert float(srcs[0].frames.mean()) == pytest.approx(0.2) and float(srcs[1].frames.mean()) == pytest.approx(0.1)


def test_budget_error_and_fit() -> None:
    vae = FakeH3VideoVAE()
    clip = torch.rand(60, 320, 320, 3)
    per_frame = 10 * 10
    with pytest.raises(RefModError, match="over max_visual_tokens"):
        extract.make_visual("m", vae, {}, {"ref_video_1": clip}, [], max_tokens=4 * per_frame, budget_policy="error")
    mod = extract.make_visual("m", vae, {}, {"ref_video_1": clip}, [], max_tokens=3 * per_frame, budget_policy="truncate")
    assert mod.latent.shape[2] <= 3
    with pytest.raises(RefModError, match="one reference frame"):
        extract.make_visual("m", vae, {}, {"ref_video_1": clip}, [], max_tokens=per_frame - 1, budget_policy="truncate")


def test_temporal_dedup_keeps_changing_frames_and_fit_resamples() -> None:
    lat = torch.ones(1, 24, 6, 4, 4)
    lat[:, :, 3:] = 2.0  # frames 0-2 identical, 3-5 identical but different
    assert extract.temporal_dedup(lat).shape[2] == 2
    ramp = torch.stack([torch.full((1, 24, 4, 4), float(i + 1)) for i in range(8)], dim=2)
    fitted = extract.fit_to_budget(ramp, 3 * 4)
    assert fitted.shape[2] == 3 and tuple(fitted.shape[3:]) == (4, 4)
    assert extract.fit_to_budget(ramp, 10_000) is ramp


def test_make_audio_and_truncation_policies() -> None:
    vae = FakeAudioVAE()
    wave = torch.zeros(1, 1, 32000 * 2)  # mono 2 s at 32 kHz
    mod = extract.make_audio(vae, {"waveform": wave, "sample_rate": 32000}, "a", 30.0, 5120, "error", "d", "voice")
    assert mod.kind == "audio" and mod.latent.shape == (1, 32, 2, 80) and mod.sample_rate == 32000
    assert mod.concept_type == "voice" and mod.token_count == 160
    cut = extract.make_audio(vae, {"waveform": wave, "sample_rate": 32000}, "a", 1.0, 5120, "error", "", "voice")
    assert cut.latent.shape[-1] == 40
    with pytest.raises(RefModError, match="over audio_max_tokens"):
        extract.make_audio(vae, {"waveform": wave, "sample_rate": 32000}, "a", 30.0, 100, "error", "", "voice")
    assert extract.truncate_audio_latent(torch.zeros(1, 32, 2, 80), 100, "truncate").shape[-1] == 50
    with pytest.raises(RefModError, match="non-negative integer"):
        extract.truncate_audio_latent(torch.zeros(1, 32, 2, 8), -1, "error")
    with pytest.raises(RefModError, match="MiniMaxH3AudioVAE"):
        extract.make_audio(object(), {"waveform": wave, "sample_rate": 32000}, "a", 3.0, 0, "error", "", "voice")
    with pytest.raises(RefModError, match="waveform"):
        extract.make_audio(vae, {"waveform": torch.zeros(1, 3, 10), "sample_rate": 32000}, "a", 3.0, 0, "error", "", "v")
    resampled = extract.prepare_waveform({"waveform": torch.zeros(1, 2, 16000), "sample_rate": 16000}, 30.0)
    assert resampled.shape == (1, 2, 32000)


def test_folder_loading_images_first_and_skips_unreadable(tmp_path: Path) -> None:
    folder = str(tmp_path)
    Image.new("RGB", (40, 30), (255, 0, 0)).save(os.path.join(folder, "b.png"))
    Image.new("RGB", (4000, 1000), (0, 255, 0)).save(os.path.join(folder, "a.jpg"))
    with open(os.path.join(folder, "broken.png"), "wb") as fh:
        fh.write(b"not an image")
    with open(os.path.join(folder, "notes.txt"), "w") as fh:
        fh.write("ignored")
    items, skipped = extract.load_folder(folder, 8, 1536)
    assert len(items) == 2 and len(skipped) == 1 and "broken.png" in skipped[0]
    assert items[0].shape[1:3] == (384, 1536)  # a.jpg, down-only to the long edge
    assert items[1].shape == (1, 30, 40, 3)
    assert extract.folder_change_key(folder, 8).count("|") == 2
    assert extract.folder_change_key(os.path.join(folder, "nope"), 8) == "missing"
    with pytest.raises(RefModError, match="folder not found"):
        extract.load_folder(os.path.join(folder, "nope"), 8, 1536)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(RefModError, match="no readable"):
        extract.load_folder(str(empty), 8, 1536)


def test_pick_frames_and_reservoir_are_deterministic() -> None:
    assert extract._pick_frames(10, 240) is None
    picks = extract._pick_frames(1000, 5)
    assert picks == [0, 250, 500, 749, 999] or (picks[0] == 0 and picks[-1] == 999 and len(picks) == 5)
    frames = [torch.zeros(1).numpy() + i for i in range(500)]
    a = extract._reservoir(iter(frames), 20)
    b = extract._reservoir(iter(frames), 20)
    assert [float(x[0]) for x in a] == [float(x[0]) for x in b]
    assert [float(x[0]) for x in a] == sorted(float(x[0]) for x in a)


def test_sidecars_thumbnail_and_peaks(tmp_path: Path) -> None:
    stem = os.path.join(str(tmp_path), "char")
    frame = torch.rand(1, 600, 400, 3)
    wave = torch.sin(torch.linspace(0, 200, 32000 * 3)).view(1, 1, -1)
    extract.write_sidecars(stem, frame, {"waveform": wave, "sample_rate": 32000}, 2.0)
    with Image.open(stem + ".jezzwtf.jpg") as im:
        assert im.size == (256, 256) and im.format == "JPEG"
    data = json.loads(Path(stem + ".jezzwtf.json").read_text(encoding="utf-8"))
    assert len(data["peaks"]) == 64 and max(data["peaks"]) == 1.0 and data["seconds"] == pytest.approx(2.0)
    assert isinstance(data["created"], int)
    assert sorted(os.listdir(tmp_path)) == ["char.jezzwtf.jpg", "char.jezzwtf.json"]
    extract.write_sidecars(stem, None, None, 30.0)  # no image: the stale thumbnail goes away
    assert not os.path.exists(stem + ".jezzwtf.jpg")
    assert "peaks" not in json.loads(Path(stem + ".jezzwtf.json").read_text(encoding="utf-8"))


def _write_video(path: str, frames: int, w: int = 64, h: int = 48) -> bool:
    cv2 = pytest.importorskip("cv2")
    import numpy as np
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 10, (w, h))
    if not vw.isOpened():
        return False
    for i in range(frames):
        vw.write(np.full((h, w, 3), (i * 3) % 255, dtype=np.uint8))
    vw.release()
    return True


def test_video_loading_downscales_per_frame_and_caps_frames(tmp_path) -> None:
    path = str(tmp_path / "clip.avi")
    if not _write_video(path, 60):
        pytest.skip("no MJPG writer")
    out = extract.load_video_file(path, max_edge=32, max_frames=8)
    assert out.dtype == torch.float32 and out.shape[0] == 8 and max(out.shape[1:3]) == 32


def test_video_loading_survives_a_wrong_container_frame_count(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    cv2 = pytest.importorskip("cv2")
    path = str(tmp_path / "clip.avi")
    if not _write_video(path, 40):
        pytest.skip("no MJPG writer")

    real = cv2.VideoCapture

    class Liar:
        def __init__(self, p: str) -> None:
            self.cap = real(p)

        def get(self, prop: int) -> float:
            return 400.0 if prop == cv2.CAP_PROP_FRAME_COUNT else self.cap.get(prop)

        def __getattr__(self, name: str) -> object:
            return getattr(self.cap, name)

    monkeypatch.setattr(cv2, "VideoCapture", Liar)
    out = extract.load_video_file(path, max_edge=64, max_frames=8)
    assert out.shape[0] == 8  # picks past the real end would have left only a handful
