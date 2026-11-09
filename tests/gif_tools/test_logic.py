"""Pure logic: delay rounding, paths and containment, frame planning, de-duplication, metrics, GIF structure."""
from __future__ import annotations

import io
import os

import numpy as np
import pytest
from PIL import Image

from gif_tools import frames as F
from gif_tools import gifio, output, quality, timing
from gif_tools.settings import check_choice, check_colors, check_float, check_int

import synth


# ------------------------------------------------------------------ timing

def test_even_fps_snaps_to_whole_centiseconds() -> None:
    assert timing.even_fps(25) == pytest.approx(25)
    assert timing.even_fps(20) == pytest.approx(20)
    assert timing.even_fps(12.5) == pytest.approx(12.5)
    assert timing.even_fps(24) == pytest.approx(25)        # 4 cs
    assert timing.even_fps(30) == pytest.approx(100 / 3)   # 3 cs, closer than 25
    assert timing.even_fps(120) == pytest.approx(50)       # never below 2 cs


def test_quantise_delays_never_uses_the_10ms_delay() -> None:
    delays = timing.quantise_delays([0.005] * 20 + [0.0] * 3)
    assert min(delays) >= 2


def test_quantise_delays_track_real_time() -> None:
    delays = timing.quantise_delays([1 / 30] * 90)       # 3.33 cs frames: 3,3,4 pattern
    assert set(delays) == {3, 4}
    assert abs(sum(delays) - 300) <= 1
    assert timing.quantise_delays([0.04] * 10) == [4] * 10


def test_quantise_delays_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        timing.quantise_delays([float("nan")])
    with pytest.raises(ValueError):
        timing.quantise_delays([-0.1])


def test_fps_notes_warn_only_when_cadence_is_uneven() -> None:
    assert timing.fps_notes(25, "exact") == []
    assert timing.fps_notes(12.5, "exact") == []
    assert "alternate" in timing.fps_notes(30, "exact")[0]
    assert "snapped" in timing.fps_notes(30, "even")[0]
    assert "50 fps" in timing.fps_notes(60, "exact")[0]
    assert timing.resolve_fps(60, "exact") == 50
    assert timing.resolve_fps(30, "even") == pytest.approx(100 / 3)


# ------------------------------------------------------------------ settings validation

def test_validators() -> None:
    assert check_colors(0) == 0 and check_colors(16) == 16 and check_colors(256) == 256
    for bad in (1, 15, 257, True, 3.5):
        with pytest.raises(ValueError):
            check_colors(bad)
    for bad in (float("nan"), float("inf"), "3", None, True):
        with pytest.raises(ValueError):
            check_float("x", bad, 0, 10)
    with pytest.raises(ValueError):
        check_int("x", 11, 0, 10)
    with pytest.raises(ValueError):
        check_choice("d", "none; rm -rf /", ("none",))


# ------------------------------------------------------------------ paths

@pytest.mark.parametrize("bad", ["../evil", "a/../../evil", "/abs/path", "C:/abs", "C:evil", "x\x00y", "..\\evil"])
def test_prefix_escapes_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        output.sanitize_prefix(bad)


def test_prefix_is_cleaned_not_trusted() -> None:
    assert output.sanitize_prefix("My Clip: take?1") == ["My Clip_ take_1"]
    assert output.sanitize_prefix("proj\\scene/ünï cödé") == ["proj", "scene", "ünï cödé"]
    assert output.sanitize_prefix("   ") == ["gif"]
    assert output.sanitize_prefix("con")[0].startswith("_")


def test_reserve_output_counts_up_and_stays_inside(tmp_path: pytest.TempPathFactory) -> None:
    root = str(tmp_path)
    p1, sub, name = output.reserve_output_path(root, "my clip ünï", "gif")
    p2, _, name2 = output.reserve_output_path(root, "my clip ünï", "gif")
    assert name == "my clip ünï_00001.gif" and name2 == "my clip ünï_00002.gif"
    assert sub == "gifs" and os.path.isfile(p1) and os.path.isfile(p2)
    assert output.is_inside(root, p1)
    p3, sub3, _ = output.reserve_output_path(root, "deep/er/clip", "gif")
    assert sub3 == "gifs/deep/er" and output.is_inside(root, p3)
    with pytest.raises(ValueError):
        output.reserve_output_path(root, "../../outside", "gif")
    with pytest.raises(ValueError):
        output.reserve_output_path(root, "ok", "gif;rm")


def test_symlinked_subfolder_cannot_escape(tmp_path: pytest.TempPathFactory) -> None:
    root, outside = tmp_path / "out", tmp_path / "elsewhere"
    (root / "gifs").mkdir(parents=True)
    outside.mkdir()
    try:
        os.symlink(outside, root / "gifs" / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted here")
    with pytest.raises(ValueError):
        output.reserve_output_path(str(root), "link/file", "gif")
    assert not any(outside.iterdir())


def test_resolve_existing_file_contains_reads(tmp_path: pytest.TempPathFactory) -> None:
    inp, other = tmp_path / "in put", tmp_path / "other"
    inp.mkdir(), other.mkdir()
    good, evil = inp / "ünï a.gif", other / "x.gif"
    good.write_bytes(b"GIF89a"), evil.write_bytes(b"GIF89a")
    assert output.resolve_existing_file("ünï a.gif", [str(inp)]) == os.path.realpath(good)
    assert output.resolve_existing_file(str(good), [str(inp)]) == os.path.realpath(good)
    for bad in (str(evil), "../other/x.gif"):
        with pytest.raises(ValueError):
            output.resolve_existing_file(bad, [str(inp)])
    (inp / "note.txt").write_text("x")
    with pytest.raises(ValueError):
        output.resolve_existing_file("note.txt", [str(inp)])


# ------------------------------------------------------------------ frame planning

def test_plan_resample_counts_and_trim() -> None:
    starts = [i / 30 for i in range(90)]  # 3 s at 30 fps
    picks, durs = F.plan_resample(starts, 3.0, F.PrepOptions(fps=10))
    assert len(picks) == 30 and picks[:3] == [0, 3, 6] and durs == [0.1] * 30
    picks, _ = F.plan_resample(starts, 3.0, F.PrepOptions(fps=10, start=1.0, end=2.0))
    assert len(picks) == 10 and picks[0] == 30
    picks, durs = F.plan_resample(starts, 3.0, F.PrepOptions(fps=10, speed=2.0))
    assert len(picks) == 15 and picks[1] == 6 and durs[0] == 0.1
    with pytest.raises(ValueError):
        F.plan_resample(starts, 3.0, F.PrepOptions(start=5.0))
    with pytest.raises(ValueError):
        F.plan_resample(starts, 3.0, F.PrepOptions(fps=10, speed=0))


def test_native_timing_keeps_per_frame_durations() -> None:
    picks, durs = F.plan_resample([0.0, 0.1, 0.5], 0.6, F.PrepOptions())
    assert picks == [0, 1, 2] and durs == pytest.approx([0.1, 0.4, 0.1])
    _, durs = F.plan_resample([0.0, 0.1, 0.5], 0.6, F.PrepOptions(speed=2.0))
    assert durs == pytest.approx([0.05, 0.2, 0.05])


def test_fit_size_never_upscales_and_keeps_aspect() -> None:
    assert F.fit_size(640, 480, 320, 0) == (320, 240)
    assert F.fit_size(640, 480, 0, 120) == (160, 120)
    assert F.fit_size(640, 480, 1000, 1000) == (640, 480)
    assert F.fit_size(640, 480, 0, 0) == (640, 480)


def test_crop_and_transform() -> None:
    frame = np.arange(40 * 60 * 3, dtype=np.uint8).reshape(40, 60, 3)
    tf, (w, h) = F.make_transform(60, 40, F.PrepOptions(crop=(10, 5, 10, 5), max_width=25))
    out = tf(frame)
    assert (w, h) == (25, 19) and out.shape == (19, 25, 3)
    with pytest.raises(ValueError):
        F.make_transform(60, 40, F.PrepOptions(crop=(30, 0, 30, 0)))


def test_resample_clip_changes_rate() -> None:
    clip = synth.gradient_clip(20, fps=20)
    slower = F.resample(clip, 10)
    assert len(slower.frames) == 10 and slower.total == pytest.approx(1.0)
    faster = F.resample(clip, 40)
    assert len(faster.frames) == 40 and faster.frames[0] is faster.frames[1]


# ------------------------------------------------------------------ de-duplication

def test_dedupe_exact_merges_identical_frames_and_keeps_total_time() -> None:
    clip = synth.static_clip(30)
    slim, dropped = F.dedupe(clip, 0.0)
    assert dropped > 20 and len(slim.frames) == 30 - dropped
    assert slim.total == pytest.approx(clip.total)
    assert len(slim.frames) == 3  # still, blink, still: byte-identical runs collapse


def test_dedupe_threshold_merges_near_duplicates_but_not_real_change() -> None:
    clip = synth.gradient_clip(10)
    noisy = F.Clip([np.clip(f.astype(np.int16) + (1 if i else 0), 0, 255).astype(np.uint8) for i, f in enumerate([clip.frames[0]] * 10)], [0.05] * 10)
    assert len(F.dedupe(noisy, 0.0)[0].frames) == 2          # off-by-one pixels are not byte-equal
    assert len(F.dedupe(noisy, 1.5)[0].frames) == 1          # but are within a 1.5 level tolerance
    assert len(F.dedupe(noisy, 0.5)[0].frames) == 2          # and not within 0.5
    moving = synth.motion_clip(12)
    assert len(F.dedupe(moving, 0.2)[0].frames) == 12        # a moving square is real change
    assert F.dedupe(moving, -1)[1] == 0                      # negative disables


def test_dedupe_does_not_swallow_slow_fades() -> None:
    frames = [np.full((32, 32, 3), v, dtype=np.uint8) for v in range(0, 40)]
    slim, _ = F.dedupe(F.Clip(frames, [0.05] * 40), 3.0)
    assert 8 <= len(slim.frames) <= 20  # drift accumulates against the last kept frame


# ------------------------------------------------------------------ metrics

def test_ssim_properties() -> None:
    a = synth.gradient_clip(1).frames[0]
    assert quality.frame_ssim(a, a) == pytest.approx(1.0)
    noisy = np.clip(a.astype(np.int16) + np.random.default_rng(1).integers(-40, 40, a.shape), 0, 255).astype(np.uint8)
    s = quality.frame_ssim(a, noisy)
    assert 0.1 < s < 0.95
    assert quality.frame_psnr(a, a) == 99.0
    assert quality.frame_psnr(a, noisy) < 40


def test_ssim_matches_scikit_image_when_available() -> None:
    skimage_metrics = pytest.importorskip("skimage.metrics")
    rng = np.random.default_rng(3)
    a = rng.integers(0, 256, (64, 80), dtype=np.uint8).astype(np.float32)
    b = np.clip(a + rng.normal(0, 12, a.shape), 0, 255).astype(np.float32)
    ref = skimage_metrics.structural_similarity(a, b, data_range=255)
    assert quality.ssim_gray(a, b) == pytest.approx(ref, abs=1e-4)


def test_compare_sequences_aligns_by_time() -> None:
    clip = synth.motion_clip(24, fps=24)
    half = F.resample(clip, 12)
    r = quality.compare_sequences(clip.frames, clip.durations, half.frames, half.durations, sample=24)
    assert 0.8 < r.ssim_mean < 1.0 and r.frames_compared == 24
    same = quality.compare_sequences(clip.frames, clip.durations, clip.frames, clip.durations)
    assert same.ssim_mean == pytest.approx(1.0) and same.psnr_mean == 99.0
    assert quality.align([0.1] * 4, [0.2, 0.2]) == [0, 0, 1, 1]


# ------------------------------------------------------------------ GIF structure

def _pillow_gif(delays_ms: list[int], loop: int | None = 0) -> bytes:
    frames = [Image.new("RGB", (16, 16), (i * 70 % 256, 255 - i * 50 % 256, 40)) for i in range(len(delays_ms))]
    buf = io.BytesIO()
    kwargs = {"loop": loop} if loop is not None else {}
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=delays_ms, disposal=1, **kwargs)
    return buf.getvalue()


def test_patch_and_read_delays_round_trip() -> None:
    data = _pillow_gif([100, 100, 100])
    assert gifio.read_delays_cs(data) == [10, 10, 10]
    patched = gifio.patch_gif_delays(data, [4, 5, 40])
    assert gifio.read_delays_cs(patched) == [4, 5, 40]
    assert Image.open(io.BytesIO(patched)).n_frames == 3
    with pytest.raises(ValueError):
        gifio.patch_gif_delays(data, [4, 5])
    with pytest.raises(ValueError):
        gifio.patch_gif_delays(data, [1, 5, 5])  # 10 ms is below the safe floor


def test_scan_reports_loop_and_rejects_garbage() -> None:
    assert gifio.scan_gif(_pillow_gif([100, 100], loop=0))[1] == 0
    assert gifio.scan_gif(_pillow_gif([100, 100], loop=None))[1] == -1
    with pytest.raises(ValueError):
        gifio.scan_gif(b"not a gif at all")


def test_read_gif_applies_browser_delay_rule() -> None:
    g = gifio.read_gif(_pillow_gif([10, 20, 100]))
    assert g.durations == pytest.approx([0.1, 0.02, 0.1])
    assert any("10 ms" in n for n in g.notes)


def test_pillow_fallback_round_trip_is_exact_for_flat_colour() -> None:
    clip = synth.flat_clip(6)
    data = gifio.encode_with_pillow(clip.frames, [10] * 6, 16, "none", 0)
    got = gifio.read_gif(data)
    assert len(got.frames) == 6
    for a, b in zip(clip.frames, got.frames):
        assert np.array_equal(a, b)
    assert not got.has_transparency
