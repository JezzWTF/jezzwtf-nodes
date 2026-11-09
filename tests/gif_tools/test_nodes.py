"""Node-level behaviour: tensors in, files out, validation, video sources and the Load GIF round trip."""
from __future__ import annotations

import json
import os
from fractions import Fraction

import numpy as np
import pytest
import torch

from gif_tools import frames as F
from gif_tools import gifio, nodes
from gif_tools.nodes import JWTFFramesToAnimated, JWTFGifCompare, JWTFGifOptimise, JWTFLoadGif, JWTFVideoToGif

import synth
from synth import needs_ffmpeg


@pytest.fixture
def dirs(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    d = {"input": str(tmp_path / "in put"), "output": str(tmp_path / "out"), "temp": str(tmp_path / "tmp")}
    for p in d.values():
        os.makedirs(p)
    monkeypatch.setattr(nodes, "input_dir", lambda: d["input"])
    monkeypatch.setattr(nodes, "temp_dir", lambda: d["temp"])
    monkeypatch.setattr(nodes, "output_dir", lambda: d["output"])
    return d


def as_tensor(clip: F.Clip) -> torch.Tensor:
    return nodes.frames_to_tensor(clip.frames)


def test_node_registration_and_schema() -> None:
    assert set(nodes.NODE_CLASS_MAPPINGS) == {"JWTFVideoToGif", "JWTFGifOptimise", "JWTFGifCompare", "JWTFLoadGif", "JWTFFramesToAnimated"}
    for cls in nodes.NODE_CLASS_MAPPINGS.values():
        assert cls.CATEGORY == "JezzWTF/gif"
        spec = cls.INPUT_TYPES()
        assert "required" in spec
        assert len(cls.RETURN_TYPES) == len(cls.RETURN_NAMES)
    opt = JWTFVideoToGif.INPUT_TYPES()["optional"]
    assert {"images", "video", "mode"} <= set(opt) | set(JWTFVideoToGif.INPUT_TYPES()["required"])
    assert nodes.NODE_DISPLAY_NAME_MAPPINGS["JWTFVideoToGif"] == "Video to GIF (Optimised)"


def test_tensor_frame_round_trip_and_channel_handling() -> None:
    t = torch.rand(3, 8, 10, 3)
    frames = nodes.tensor_to_frames(t)
    assert len(frames) == 3 and frames[0].dtype == np.uint8
    assert np.abs(nodes.frames_to_tensor(frames) - t).max() <= 1 / 255 + 1e-6
    assert nodes.tensor_to_frames(torch.rand(2, 8, 10, 4))[0].shape == (8, 10, 3)
    assert nodes.tensor_to_frames(torch.rand(2, 8, 10, 1))[0].shape == (8, 10, 3)
    with pytest.raises(ValueError):
        nodes.tensor_to_frames(torch.rand(8, 10))


def test_loop_count_mapping() -> None:
    assert [nodes.loop_value(n) for n in (0, 1, 2, 5)] == [0, -1, 1, 4]


@needs_ffmpeg
def test_video_to_gif_from_images_saves_into_output_gifs(dirs: dict[str, str]) -> None:
    clip = synth.motion_clip(12)
    out = JWTFVideoToGif().run("balanced", "my clip/ünï", images=as_tensor(clip), source_fps=20.0, fps=10.0, max_width=96, compare_naive=True)
    path, preview, report = out["result"]
    assert path.startswith(os.path.realpath(dirs["output"])) or path.startswith(dirs["output"])
    assert os.path.basename(path) == "ünï_00001.gif" and os.path.dirname(path).endswith(os.path.join("gifs", "my clip"))
    assert os.path.getsize(path) > 0
    g = gifio.read_gif(path)
    assert len(g.frames) == preview.shape[0] and preview.shape[2] == 96
    assert "SSIM" in report and "naive" in report
    entry = out["ui"]["jwtf_gif"][0]
    assert entry["subfolder"] == "gifs/my clip" and entry["filename"] == "ünï_00001.gif" and entry["stats"]["bytes"] == os.path.getsize(path)
    again = JWTFVideoToGif().run("balanced", "my clip/ünï", images=as_tensor(clip), fps=10.0, max_width=96, compare_naive=False)
    assert os.path.basename(again["result"][0]) == "ünï_00002.gif"


@needs_ffmpeg
def test_video_to_gif_warns_about_uneven_cadence_and_clamps(dirs: dict[str, str]) -> None:
    clip = synth.motion_clip(10, fps=60)
    out = JWTFVideoToGif().run("quality", "cad", images=as_tensor(clip), source_fps=60.0, fps=30.0, dither="none", palette="global_full", compare_naive=False)
    assert "not a whole number of 10 ms" in out["result"][2]
    out = JWTFVideoToGif().run("quality", "cad", images=as_tensor(clip), source_fps=60.0, fps=0.0, dither="none", palette="global_full", compare_naive=False)
    assert "50 fps" in out["result"][2]
    delays = gifio.read_delays_cs(open(out["result"][0], "rb").read())
    assert min(delays) >= 2


def test_video_to_gif_input_and_validation_errors(dirs: dict[str, str]) -> None:
    node = JWTFVideoToGif()
    with pytest.raises(ValueError, match="IMAGE batch or a VIDEO"):
        node.run("balanced", "x")
    imgs = torch.rand(3, 16, 16, 3)
    for bad in ({"fps": float("nan")}, {"speed": 0.0}, {"colors": 7}, {"dither": "x; y"}, {"crop_left": -1}, {"trim_start": float("inf")}, {"mode": "nope"}):
        kwargs = {"mode": "balanced", "filename_prefix": "x", "images": imgs, **bad}
        mode = kwargs.pop("mode")
        prefix = kwargs.pop("filename_prefix")
        with pytest.raises(ValueError):
            node.run(mode, prefix, **kwargs)
    with pytest.raises(ValueError):
        node.run("balanced", "../../escape", images=imgs)
    assert not os.path.exists(os.path.join(dirs["output"], "..", "escape_00001.gif"))


@needs_ffmpeg
def test_gif_optimise_round_trip_and_load_gif(dirs: dict[str, str]) -> None:
    clip = synth.motion_clip(30)
    src = gifio.encode_with_pillow(clip.frames, [5] * 30, 256, "none", 0)
    with open(os.path.join(dirs["input"], "ünï src.gif"), "wb") as fh:
        fh.write(src)
    out = JWTFGifOptimise().run("ünï src.gif", "smallest", "opt", palette="global_full", dither="sierra2_4a", compare_naive=False)
    path, preview, report = out["result"]
    assert "source GIF" in report and "% saved" in report
    loaded = JWTFLoadGif().run("ünï src.gif")
    assert loaded[3] == 30 and loaded[0].shape[0] == 30 and loaded[1].shape[0] == 30
    assert loaded[2] == pytest.approx(20.0, rel=0.01)
    assert json.loads(loaded[4]) == [50] * 30
    assert float(loaded[1].max()) == 0.0  # opaque GIF: mask is all 0
    # the optimised GIF is loadable by path (outside the input folder, inside output)
    again = JWTFLoadGif().run("", path=path)
    assert again[3] == preview.shape[0]
    with pytest.raises(ValueError):
        JWTFLoadGif().run("", path=os.path.join(dirs["input"], "..", "..", "windows", "x.gif"))


def test_load_gif_mask_from_transparency(dirs: dict[str, str]) -> None:
    from PIL import Image

    rgba = np.zeros((20, 30, 4), dtype=np.uint8)
    rgba[:, 15:] = (200, 30, 30, 255)
    other = rgba.copy()
    other[5:10, 20:25] = (30, 200, 30, 255)
    path = os.path.join(dirs["input"], "t.gif")
    Image.fromarray(rgba, "RGBA").save(path, save_all=True, append_images=[Image.fromarray(other, "RGBA")], duration=[100, 100], loop=0, disposal=2)
    images, mask, fps, count, delays = JWTFLoadGif().run("t.gif")
    assert count == 2 and mask.shape == (2, 20, 30)
    assert float(mask[0, 0, 0]) == 1.0 and float(mask[0, 0, 29]) == 0.0
    assert fps == pytest.approx(10.0)


def test_compare_node_reports_and_composes(dirs: dict[str, str]) -> None:
    clip = synth.motion_clip(10)
    good = F.Clip([np.clip(f.astype(np.int16) + 3, 0, 255).astype(np.uint8) for f in clip.frames], clip.durations)
    bad = synth.noise_clip(10, w=160, h=120)
    node = JWTFGifCompare()
    img_a, img_good, img_bad = as_tensor(clip), as_tensor(good), as_tensor(bad)
    for layout, width in (("side_by_side", 320), ("split", 160), ("difference", 160)):
        tensor, text = node.run(layout, images_a=img_a, images_b=img_good, output_frames=5)["result"]
        assert tensor.shape == (5, 120, width, 3)
    _, text_good = node.run("split", images_a=img_a, images_b=img_good)["result"]
    _, text_bad = node.run("split", images_a=img_a, images_b=img_bad)["result"]

    def mean(text: str) -> float:
        return float(text.split("SSIM mean ")[1].split(",")[0])

    assert mean(text_good) > 0.9 > mean(text_bad)
    with pytest.raises(ValueError):
        node.run("split", images_a=img_a)
    with pytest.raises(ValueError):
        node.run("diagonal", images_a=img_a, images_b=img_a)


def test_compare_node_reads_gifs_and_sizes(dirs: dict[str, str]) -> None:
    clip = synth.motion_clip(6)
    a = gifio.encode_with_pillow(clip.frames, [5] * 6, 256, "none", 0)
    b = gifio.encode_with_pillow(clip.frames, [5] * 6, 16, "none", 0)
    for name, blob in (("a.gif", a), ("b.gif", b)):
        with open(os.path.join(dirs["input"], name), "wb") as fh:
            fh.write(blob)
    _, text = JWTFGifCompare().run("side_by_side", gif_a="a.gif", gif_b="b.gif")["result"]
    assert f"{len(a):,} bytes" in text and "size B/A" in text


def test_frames_to_animated_webp_and_apng(dirs: dict[str, str]) -> None:
    imgs = as_tensor(synth.motion_clip(8))
    node = JWTFFramesToAnimated()
    out = node.run(imgs, 10.0, "webp", "w", quality=70)
    assert out["result"][0].endswith("w_00001.webp") and os.path.getsize(out["result"][0]) > 0
    assert "lossy q70" in out["result"][1]
    sized = node.run(imgs, 10.0, "webp", "w", target_size_mb=0.02)
    stats = sized["ui"]["jwtf_gif"][0]["stats"]
    assert stats["fits"] is True and stats["bytes"] <= 0.02 * 1024 * 1024
    png = node.run(imgs, 10.0, "apng", "a")
    assert png["result"][0].endswith("a_00001.png")
    from PIL import Image

    assert getattr(Image.open(png["result"][0]), "n_frames", 1) == 8
    with pytest.raises(ValueError):
        node.run(imgs, 10.0, "gif", "bad")


# ------------------------------------------------------------------ video input

def _write_video(path: str, frames: list[np.ndarray], fps: int) -> None:
    import av

    with av.open(path, "w") as container:
        stream = container.add_stream("mpeg4", rate=fps)
        stream.width, stream.height, stream.pix_fmt = frames[0].shape[1], frames[0].shape[0], "yuv420p"
        for f in frames:
            for packet in stream.encode(av.VideoFrame.from_ndarray(f, format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


@pytest.fixture
def video_file(tmp_path: pytest.TempPathFactory) -> str:
    pytest.importorskip("av")
    path = str(tmp_path / "ünï clip.mp4")
    _write_video(path, synth.motion_clip(30, w=160, h=120).frames, 10)  # 3 s at 10 fps
    return path


def test_video_source_times_and_fetch(video_file: str) -> None:
    src = F.source_from_video_file(video_file)
    assert len(src.starts) == 30 and src.end == pytest.approx(3.0, abs=0.05) and (src.width, src.height) == (160, 120)
    assert src.native_fps == pytest.approx(10.0, rel=0.05)
    clip = F.make_clip(src, F.PrepOptions(fps=5, max_width=80))
    assert len(clip.frames) == 15 and clip.size == (80, 60)
    trimmed = F.make_clip(src, F.PrepOptions(fps=10, start=1.0, end=2.0, speed=2.0))
    assert len(trimmed.frames) == 5


def test_video_input_object_with_pretrim_window(video_file: str) -> None:
    class FakeVideo:
        def get_stream_source(self) -> str:
            return video_file

        def get_active_trim_window(self) -> tuple[float, float]:
            return 1.0, 1.0

    src = nodes.video_source(FakeVideo())
    assert len(src.starts) == 10 and src.end == pytest.approx(1.0, abs=0.05)


def test_video_input_falls_back_to_components() -> None:
    class Comps:
        images = torch.rand(6, 16, 16, 3)
        frame_rate = Fraction(12)

    class FakeVideo:
        def get_stream_source(self) -> object:
            return object()  # BytesIO-like, not a path

        def get_components(self) -> Comps:
            return Comps()

    src = nodes.video_source(FakeVideo())
    assert len(src.starts) == 6 and src.native_fps == pytest.approx(12)


@needs_ffmpeg
def test_video_to_gif_node_accepts_video(dirs: dict[str, str], video_file: str) -> None:
    class FakeVideo:
        def get_stream_source(self) -> str:
            return video_file

    out = JWTFVideoToGif().run("balanced", "vid", video=FakeVideo(), fps=10.0, max_width=64, dither="none", palette="global_full", compare_naive=False)
    assert gifio.read_gif(out["result"][0]).frames[0].shape[1] == 64
