"""argv construction (no ffmpeg needed) and real ffmpeg encodes (skipped when ffmpeg is missing)."""
from __future__ import annotations

import tempfile

import numpy as np
import pytest

from gif_tools import encoder, ffmpeg_gif as ff, gifio, optimise
from gif_tools.frames import Clip, dedupe
from gif_tools.timing import quantise_delays

import synth
from synth import needs_ffmpeg

FF = "ffmpeg"


# ------------------------------------------------------------------ argv building

def test_argv_is_a_list_of_plain_strings_with_fixed_structure() -> None:
    argv = ff.paletteuse_argv(FF, "in.rgb", "pal.png", "out.gif", 320, 200, 25.0, 128, "bayer_3", True, 0)
    assert all(isinstance(a, str) for a in argv)
    assert argv[0] == FF and "-filter_complex" in argv
    graph = argv[argv.index("-filter_complex") + 1]
    assert graph == "[0:v][1:v]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle"
    assert argv[argv.index("-video_size") + 1] == "320x200"


@pytest.mark.parametrize("bad_name", ["a b.rgb", "x;rm -rf.rgb", "../in.rgb", "in$(x).rgb", "ünï.rgb", "in\n.rgb", "", "a" * 60])
def test_unsafe_file_names_are_refused(bad_name: str) -> None:
    with pytest.raises(ValueError):
        ff.palettegen_argv(FF, bad_name, "pal.png", 64, 64, 25.0, 256, "full", True)


@pytest.mark.parametrize("dither", ["auto", "none; calc", "bayer_9", "", "sierra2_4a,x"])
def test_unknown_dither_never_reaches_the_filter_string(dither: str) -> None:
    with pytest.raises(ValueError):
        ff.paletteuse_argv(FF, "in.rgb", "pal.png", "out.gif", 64, 64, 25.0, 256, dither, True, 0)


def test_numeric_inputs_are_validated() -> None:
    with pytest.raises(ValueError):
        ff.palettegen_argv(FF, "in.rgb", "p.png", 64, 64, 25.0, 300, "full", True)
    with pytest.raises(ValueError):
        ff.palettegen_argv(FF, "in.rgb", "p.png", 64, 64, 25.0, 8, "full", True)
    with pytest.raises(ValueError):
        ff.palettegen_argv(FF, "in.rgb", "p.png", 1, 64, 25.0, 256, "full", True)
    with pytest.raises(ValueError):
        ff.palettegen_argv(FF, "in.rgb", "p.png", 64, 64, float("nan"), 256, "full", True)
    with pytest.raises(ValueError):
        ff.palettegen_argv(FF, "in.rgb", "p.png", 64, 64, 25.0, 256, "full; x", True)
    with pytest.raises(ValueError):
        ff.paletteuse_argv(FF, "in.rgb", "p.png", "o.gif", 64, 64, 25.0, 256, "none", True, -5)
    with pytest.raises(ValueError):
        ff.per_frame_argv(FF, "in.rgb", "o.gif", 64, 64, 25.0, 256, "none", True, 0, denoise="strong; x")


def test_per_frame_and_naive_argv_shapes() -> None:
    pf = ff.per_frame_argv(FF, "in.rgb", "out.gif", 64, 48, 25.0, 200, "sierra2_4a", False, 0, denoise="light")
    graph = pf[pf.index("-filter_complex") + 1]
    assert "stats_mode=single" in graph and "reserve_transparent=0" in graph and "new=1" in graph and "hqdn3d" in graph
    naive = ff.naive_argv(FF, "in.rgb", "out.gif", 64, 48, 25.0)
    assert "-filter_complex" not in naive and "-vf" not in naive


# ------------------------------------------------------------------ real encodes

@needs_ffmpeg
def test_two_pass_global_palette_beats_default_palette_at_equal_colours() -> None:
    clip = synth.gradient_clip(12)
    smart = encoder.encode_gif(clip, encoder.EncodeParams(256, "sierra2_4a", "global_full"))
    naive = encoder.naive_gif_bytes(clip)
    assert naive is not None
    frames, durs = encoder.decode_result(naive)
    from gif_tools.quality import compare_sequences

    naive_q = compare_sequences(clip.frames, clip.durations, frames, durs, sample=0, with_psnr=False).ssim_mean
    smart_q = encoder.measure(clip, smart, sample=12)
    assert smart_q > naive_q + 0.02, (smart_q, naive_q)


@needs_ffmpeg
def test_delays_are_patched_to_the_quantised_timeline() -> None:
    clip = Clip(synth.gradient_clip(9).frames, [1 / 30] * 9)
    res = encoder.encode_gif(clip, encoder.EncodeParams(64, "none", "global_full"))
    assert res.delays_cs == quantise_delays(clip.durations)
    assert gifio.read_delays_cs(res.data) == res.delays_cs
    assert min(res.delays_cs) >= 2
    assert gifio.scan_gif(res.data)[1] == 0  # loops forever by default


@needs_ffmpeg
def test_loop_values_reach_the_file() -> None:
    clip = synth.gradient_clip(4)
    assert gifio.scan_gif(encoder.encode_gif(clip, encoder.EncodeParams(32, "none", "global_full", loop=-1)).data)[1] == -1
    assert gifio.scan_gif(encoder.encode_gif(clip, encoder.EncodeParams(32, "none", "global_full", loop=3)).data)[1] == 3


@needs_ffmpeg
def test_dedupe_shrinks_a_noisy_static_clip_and_keeps_its_duration() -> None:
    clip = synth.noisy_static_clip(40)
    params = encoder.EncodeParams(128, "sierra2_4a", "global_full", transparency_opt=True)
    full = encoder.encode_gif(clip, params)
    slim, dropped = dedupe(clip, 3.0)
    small = encoder.encode_gif(slim, params)
    assert dropped >= 38 and len(slim.frames) <= 2
    assert len(small.data) < len(full.data) * 0.2
    assert sum(small.delays_cs) == pytest.approx(sum(full.delays_cs), abs=2)
    assert encoder.measure(clip, small) >= encoder.measure(clip, full) - 0.05  # merging costs no visible fidelity


@needs_ffmpeg
def test_dedupe_of_exact_copies_never_grows_the_file() -> None:
    clip = synth.static_clip(40)
    params = encoder.EncodeParams(128, "sierra2_4a", "global_full")
    full = encoder.encode_gif(clip, params)
    slim, dropped = dedupe(clip, 0.0)
    small = encoder.encode_gif(slim, params)
    assert dropped > 30 and len(small.data) <= len(full.data)
    assert sum(small.delays_cs) == pytest.approx(sum(full.delays_cs), abs=2)


@needs_ffmpeg
def test_transparency_optimisation_shrinks_localised_motion() -> None:
    clip = synth.motion_clip(24)
    on = encoder.encode_gif(clip, encoder.EncodeParams(128, "none", "global_full", transparency_opt=True))
    off = encoder.encode_gif(clip, encoder.EncodeParams(128, "none", "global_full", transparency_opt=False))
    assert len(on.data) < len(off.data)


@needs_ffmpeg
@pytest.mark.parametrize("palette", ["global_full", "global_diff", "per_frame"])
def test_every_palette_strategy_encodes_and_decodes(palette: str) -> None:
    clip = synth.motion_clip(8)
    res = encoder.encode_gif(clip, encoder.EncodeParams(64, "bayer_3", palette))
    frames, _ = encoder.decode_result(res)
    assert len(frames) == 8 and frames[0].shape == clip.frames[0].shape
    assert encoder.measure(clip, res) > 0.65  # 64 colours over a smooth multi-hue gradient: coarse but sane


@needs_ffmpeg
def test_per_frame_palettes_ignore_transparency_optimisation() -> None:
    clip = synth.motion_clip(8)
    on = encoder.encode_gif(clip, encoder.EncodeParams(64, "none", "per_frame", transparency_opt=True))
    off = encoder.encode_gif(clip, encoder.EncodeParams(64, "none", "per_frame", transparency_opt=False))
    assert encoder.measure(clip, on) > 0.65 and encoder.measure(clip, on) == pytest.approx(encoder.measure(clip, off), abs=0.01)
    assert gifio.scan_gif(on.data)[2] == 8  # one local colour table per frame


@needs_ffmpeg
def test_flat_artwork_round_trips_exactly() -> None:
    clip = synth.flat_clip(6)
    res = encoder.encode_gif(clip, encoder.EncodeParams(32, "none", "global_full"))
    frames, _ = encoder.decode_result(res)
    for a, b in zip(clip.frames, frames):
        assert np.array_equal(a, b)


@needs_ffmpeg
def test_denoise_filters_run() -> None:
    res = encoder.encode_gif(synth.noise_clip(6), encoder.EncodeParams(64, "bayer_3", "global_full", denoise="light"))
    assert res.frames == 6


@needs_ffmpeg
def test_works_from_a_temp_dir_with_spaces_and_non_ascii(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    odd = tmp_path / "ünï cödé dir 日本"
    odd.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(odd))
    res = encoder.encode_gif(synth.motion_clip(5), encoder.EncodeParams(64, "none", "global_full"))
    assert res.frames == 5
    assert not any(p.name.startswith("jwtf_gif_") for p in odd.iterdir())  # temp dir cleaned up


@needs_ffmpeg
def test_temp_dir_is_cleaned_after_a_failed_run(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with pytest.raises(ff.FfmpegError):
        encoder.encode_gif(synth.motion_clip(3), encoder.EncodeParams(64, "none", "global_full"), timeout=0.0)
    assert list(tmp_path.iterdir()) == []


@needs_ffmpeg
def test_cancellation_stops_ffmpeg_and_cleans_up(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    class Cancelled(Exception):
        pass

    def boom() -> None:
        raise Cancelled

    with pytest.raises(Cancelled):
        encoder.encode_gif(synth.motion_clip(3), encoder.EncodeParams(64, "none", "global_full"), check=boom)
    assert list(tmp_path.iterdir()) == []


def test_pillow_fallback_when_ffmpeg_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ff, "find_ffmpeg", lambda: None)
    res = encoder.encode_gif(synth.motion_clip(6), encoder.EncodeParams(64, "floyd_steinberg", "global_full"))
    assert res.backend == "pillow" and any("ffmpeg not found" in n for n in res.notes)
    frames, _ = encoder.decode_result(res)
    assert len(frames) >= 1
    out = optimise.optimise(synth.motion_clip(6), optimise.OptimiseRequest(mode="balanced", dither="floyd_steinberg", palette="global_full"))
    assert out.encode.backend == "pillow" and any("ffmpeg not found" in w for w in out.warnings)


# ------------------------------------------------------------------ modes and target size

@needs_ffmpeg
def test_modes_order_by_size_and_report_a_naive_baseline() -> None:
    clip = synth.motion_clip(24)
    sizes = {}
    for mode in ("quality", "balanced", "smallest"):
        res = optimise.optimise(clip, optimise.OptimiseRequest(mode=mode, dither="sierra2_4a", palette="global_full"))
        sizes[mode] = len(res.data)
        assert res.naive_bytes and res.naive_ssim is not None
        assert "naive single-pass" in res.report()
    assert sizes["smallest"] <= sizes["balanced"] <= sizes["quality"]


@needs_ffmpeg
def test_target_size_fits_the_budget() -> None:
    clip = synth.gradient_clip(16, w=192, h=144)
    unconstrained = optimise.optimise(clip, optimise.OptimiseRequest(mode="quality", dither="sierra2_4a", compare_naive=False))
    budget_mb = len(unconstrained.data) * 0.45 / optimise.MB
    res = optimise.optimise(clip, optimise.OptimiseRequest(mode="target_size", target_size_mb=budget_mb, max_trials=8, compare_naive=False))
    assert res.fits is True
    assert len(res.data) <= budget_mb * optimise.MB
    assert res.trials and res.quality.ssim_mean > 0.5
    assert "target" in res.report() and "fits" in res.report()


@needs_ffmpeg
def test_target_size_returns_the_closest_with_a_warning_when_impossible() -> None:
    clip = synth.noise_clip(12, w=160, h=120)
    res = optimise.optimise(clip, optimise.OptimiseRequest(mode="target_size", target_size_mb=0.002, max_trials=4, compare_naive=False))
    assert res.fits is False
    assert any("no trial fit" in w for w in res.warnings)
    assert len(res.data) == min(t.bytes for t in res.trials)


def test_target_size_needs_a_budget() -> None:
    with pytest.raises(ValueError):
        optimise.optimise(synth.motion_clip(4), optimise.OptimiseRequest(mode="target_size", target_size_mb=0.0))


@needs_ffmpeg
def test_target_search_respects_trial_and_time_limits() -> None:
    clip = synth.noise_clip(8, w=128, h=96)
    res = optimise.optimise(clip, optimise.OptimiseRequest(mode="target_size", target_size_mb=0.01, max_trials=3, compare_naive=False))
    assert len(res.trials) <= 3
    res = optimise.optimise(clip, optimise.OptimiseRequest(mode="target_size", target_size_mb=0.01, max_trials=30, time_budget_s=0.0, compare_naive=False))
    assert len(res.trials) == 1 and any("time budget" in w for w in res.warnings)
