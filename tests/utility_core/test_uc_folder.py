from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image

from utility_core.folder_batch import JWTFFolderImageBatch, load_image, save_caption
from utility_core.folder_utils import (
    SORT_ALPHA, SORT_NUMERIC, FrameSelector, caption_target, clean_path, fit_even, list_media, next_index,
    preview_name, resolve_index, sort_names,
)
from v3_helpers import legacy


def test_natural_sort() -> None:
    names = ["img10.png", "img2.png", "img001.png", "Img3.png", "img_b.png", "10.png", "a.png", "img2.jpg"]
    assert sort_names(names, SORT_NUMERIC) == [
        "10.png", "a.png", "img001.png", "img2.jpg", "img2.png", "Img3.png", "img10.png", "img_b.png",
    ]


def test_natural_sort_digits_before_text_and_ties() -> None:
    assert sort_names(["x", "1"], SORT_NUMERIC) == ["1", "x"]
    assert sort_names(["b", "B"], SORT_NUMERIC) == ["B", "b"]  # raw name breaks the casefold tie
    assert sort_names(["01", "1"], SORT_NUMERIC) == ["01", "1"]


def test_alphabetical() -> None:
    assert sort_names(["img10", "img2", "B", "a"], SORT_ALPHA) == ["a", "B", "img10", "img2"]


def test_clean_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JWTF_TEST_DIR", str(tmp_path))
    assert clean_path('  "C:\\x\\y"  ') == "C:\\x\\y"
    assert clean_path("'abc'") == "abc"
    assert clean_path("%JWTF_TEST_DIR%/a") == f"{tmp_path}/a"
    assert clean_path("$JWTF_TEST_DIR/a") == f"{tmp_path}/a"
    assert clean_path("~").startswith(os.path.expanduser("~"))
    assert clean_path("  ") == ""


def test_list_media_and_errors(tmp_path: Path) -> None:
    for n in ["b10.PNG", "b2.jpg", "notes.txt", "clip.mp4"]:
        (tmp_path / n).write_bytes(b"x")
    (tmp_path / "sub.png").mkdir()
    imgs = list_media(f'"{tmp_path}"', "image")
    assert [os.path.basename(p) for p in imgs] == ["b2.jpg", "b10.PNG"]
    assert [os.path.basename(p) for p in list_media(str(tmp_path), "video")] == ["clip.mp4"]
    with pytest.raises(ValueError):
        list_media("", "image")
    with pytest.raises(FileNotFoundError):
        list_media(str(tmp_path / "missing"), "image")


def test_indexing() -> None:
    assert resolve_index(0, 3) == 0
    assert resolve_index(4, 3) == 1  # single mode wraps
    assert resolve_index(-1, 3) == 2
    assert resolve_index(2, 3, True) == 2
    with pytest.raises(ValueError, match="set index to 0"):
        resolve_index(3, 3, True)  # folder mode never wraps
    with pytest.raises(ValueError):
        resolve_index(0, 0)
    assert next_index(0, 3, True) == 1
    assert next_index(2, 3, True) == -1
    assert next_index(0, 3, False) == -1


def test_preview_name_stable() -> None:
    a = preview_name("/x/a.png", 123)
    assert a == preview_name("/x/a.png", 123)
    assert a != preview_name("/x/a.png", 124)
    assert a.startswith("jwtf_fbl_") and a.endswith(".png") and len(a) == len("jwtf_fbl_") + 16 + 4


def test_caption_target(tmp_path: Path) -> None:
    img = str(tmp_path / "photo.final.jpg")
    assert caption_target(img, "next to image", "", "txt") == str(tmp_path / "photo.final.txt")
    assert caption_target(f'"{img}"', "next to image", "", " ..caption ") == str(tmp_path / "photo.final.caption")
    assert caption_target(img, "next to image", "", "") == str(tmp_path / "photo.final.txt")
    assert caption_target(img, "custom folder", str(tmp_path / "caps"), "txt") == str(tmp_path / "caps" / "photo.final.txt")
    with pytest.raises(ValueError):
        caption_target(img, "custom folder", " ", "txt")
    with pytest.raises(ValueError):
        caption_target("", "next to image", "", "txt")


def test_save_caption(tmp_path: Path) -> None:
    img = str(tmp_path / "a.png")
    path, written = save_caption("  hello\r\nworld \n", img, "custom folder", str(tmp_path / "out"), "txt", True)
    assert written and Path(path).read_bytes() == b"hello\nworld"
    path2, written2 = save_caption("other", img, "custom folder", str(tmp_path / "out"), "txt", False)
    assert path2 == path and not written2 and Path(path).read_bytes() == b"hello\nworld"


def test_fit_even() -> None:
    assert fit_even(1921, 1081, 0) == (1920, 1080)
    assert fit_even(1920, 1080, 960) == (960, 540)
    assert fit_even(1, 1, 0) == (2, 2)
    assert fit_even(1000, 333, 500) == (500, 166)


def test_frame_selector_rate_skip_nth_cap() -> None:
    sel = FrameSelector(src_fps=30, force_rate=15, skip_first=2, nth=1, cap=0)
    kept = [i for i in range(12) if sel.offer(i)]
    assert kept == [2, 4, 6, 8, 10]
    assert sel.out_fps == 15

    sel = FrameSelector(src_fps=24, nth=3, cap=2)
    kept = [i for i in range(20) if sel.offer(i)]
    assert kept == [0, 3]
    assert sel.done and sel.out_fps == 8
    assert sel.audio_window() == (0.0, 4 / 24)

    sel = FrameSelector(src_fps=24, force_rate=60, skip_first=24)
    kept = [i for i in range(30) if sel.offer(i)]
    assert kept == list(range(24, 30)) and sel.audio_window() == (1.0, None)


def test_image_loader_node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import utility_core.folder_batch as fb

    monkeypatch.setattr(fb, "temp_dir", lambda: str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    Image.new("RGBA", (6, 4), (255, 0, 0, 64)).save(tmp_path / "f2.png")
    Image.new("RGB", (5, 5), (0, 0, 255)).save(tmp_path / "f10.png")
    image, mask, _ = load_image(str(tmp_path / "f2.png"))
    assert image.shape == (1, 4, 6, 3) and mask.shape == (1, 4, 6)
    assert abs(float(mask[0, 0, 0]) - (1 - 64 / 255)) < 1e-6
    out = legacy(JWTFFolderImageBatch.execute(str(tmp_path), SORT_NUMERIC, 3, False))  # single mode wraps 3 -> 1
    _, _, stem, path, idx, total = out["result"]
    assert (stem, idx, total) == ("f10", 1, 2)
    assert out["ui"]["batch_info"] == [1, 2] and out["ui"]["next_index"] == [-1]
    assert out["ui"]["file_name"] == ["f10.png"]
    with pytest.raises(ValueError, match="set index to 0"):
        legacy(JWTFFolderImageBatch.execute(str(tmp_path), SORT_NUMERIC, 3, True))  # folder mode raises
    folder = legacy(JWTFFolderImageBatch.execute(str(tmp_path), SORT_NUMERIC, 0, True))
    assert folder["ui"]["next_index"] == [1] and folder["ui"]["auto_run"] == [1]
    assert isinstance(JWTFFolderImageBatch.fingerprint_inputs(str(tmp_path), SORT_NUMERIC, 0, False), str)


def test_video_loader_node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    av = pytest.importorskip("av")
    import numpy as np

    import utility_core.folder_batch as fb

    monkeypatch.setattr(fb, "temp_dir", lambda: str(tmp_path))
    vid_dir = tmp_path / "vids"
    vid_dir.mkdir()
    with av.open(str(vid_dir / "clip.mp4"), "w") as out:
        stream = out.add_stream("mpeg4", rate=24)
        stream.width, stream.height, stream.pix_fmt = 64, 48, "yuv420p"
        for i in range(24):
            frame = av.VideoFrame.from_ndarray(np.full((48, 64, 3), i * 10, dtype=np.uint8), format="rgb24")
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    res = legacy(fb.JWTFFolderVideoBatch.execute(str(vid_dir), SORT_NUMERIC, 0, False, force_rate=12, frame_load_cap=5,
                                        resize_longest_side=32))
    frames, audio, stem, _, idx, total, fps, _video = res["result"]
    assert frames.shape == (5, 24, 32, 3)
    assert fps == 12.0 and stem == "clip" and (idx, total) == (0, 1)
    assert audio["sample_rate"] == 44100 and audio["waveform"].shape == (1, 2, 4410)
    scanned = fb.scan(str(vid_dir), SORT_NUMERIC, "video", 9)
    assert scanned["ok"] and scanned["index"] == 0 and scanned["requested_index"] == 9
