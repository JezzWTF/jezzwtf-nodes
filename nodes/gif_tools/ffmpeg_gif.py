"""ffmpeg discovery, fixed-argv builders and a supervised runner (timeout, interruption, no shell)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from functools import lru_cache

from .runtime import Check, check_interrupt
from .settings import DITHERS, MAX_COLORS, MAX_DIMENSION, MIN_COLORS

DEFAULT_TIMEOUT_S = 300.0

# Everything below is interpolated into a filter string, so it is looked up in fixed tables, never formatted from user text.
_DITHER_ARGS: dict[str, str] = {
    "none": "dither=none",
    "bayer_1": "dither=bayer:bayer_scale=1",
    "bayer_2": "dither=bayer:bayer_scale=2",
    "bayer_3": "dither=bayer:bayer_scale=3",
    "bayer_4": "dither=bayer:bayer_scale=4",
    "bayer_5": "dither=bayer:bayer_scale=5",
    "sierra2_4a": "dither=sierra2_4a",
    "floyd_steinberg": "dither=floyd_steinberg",
}
_DENOISE_FILTERS: dict[str, str] = {
    "off": "",
    # hqdn3d works on planar GBR/YUV; pin the format so RGB input is not silently subsampled to 4:2:0.
    "light": "format=gbrp,hqdn3d=1.5:1.5:4:4,format=rgb24",
    "strong": "format=gbrp,hqdn3d=3:3:8:8,format=rgb24",
}
_STATS_MODES = ("full", "diff", "single")


class FfmpegError(RuntimeError):
    pass


@lru_cache(maxsize=16)
def ffmpeg_version(exe: str) -> tuple[int, int] | None:
    """(major, minor) from `ffmpeg -version`, or None when it cannot be determined (git builds, missing binary)."""
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, timeout=15, check=False,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"ffmpeg version n?(\d+)\.(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else None


@lru_cache(maxsize=1)
def find_ffmpeg() -> str | None:
    """The newest ffmpeg among: the JWTF_FFMPEG override, the one bundled with imageio-ffmpeg, and PATH.

    Version matters: imageio-ffmpeg often ships 4.x, which lacks options newer builds have, so a newer system ffmpeg wins.
    """
    candidates: list[str] = []
    override = os.environ.get("JWTF_FFMPEG", "").strip()
    if override and os.path.isfile(override):
        return override
    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            candidates.append(str(exe))
    except Exception:
        pass
    on_path = shutil.which("ffmpeg")
    if on_path and on_path not in candidates:
        candidates.append(on_path)
    if not candidates:
        return None
    return max(candidates, key=lambda c: ffmpeg_version(c) or (0, 0))


def passthrough_args(exe: str) -> list[str]:
    """Keep every input frame (no dropping or duplicating). `-fps_mode` arrived in ffmpeg 5.1; older builds use `-vsync 0`."""
    version = ffmpeg_version(exe)
    return ["-vsync", "0"] if version is not None and version < (5, 1) else ["-fps_mode", "passthrough"]


@lru_cache(maxsize=1)
def find_gifsicle() -> str | None:
    return shutil.which("gifsicle")


@contextmanager
def workdir() -> Iterator[str]:
    """A private scratch directory, removed afterwards. Windows can hold a killed process's files for a moment, so retry."""
    path = tempfile.mkdtemp(prefix="jwtf_gif_")
    try:
        yield path
    finally:
        for attempt in range(20):
            try:
                shutil.rmtree(path)
                break
            except FileNotFoundError:
                break
            except OSError:
                time.sleep(0.05 * (attempt + 1))


def _fmt_fps(fps: float) -> str:
    return f"{fps:.6f}".rstrip("0").rstrip(".")


def _check_geometry(width: int, height: int, colors: int) -> None:
    if not (isinstance(width, int) and isinstance(height, int) and 2 <= width <= MAX_DIMENSION and 2 <= height <= MAX_DIMENSION):
        raise ValueError(f"bad frame size {width}x{height}")
    if not (isinstance(colors, int) and MIN_COLORS <= colors <= MAX_COLORS):
        raise ValueError(f"bad colour count {colors}")


def _raw_input(width: int, height: int, fps: float, name: str) -> list[str]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", name):
        raise ValueError(f"unsafe file name {name!r}")
    if not 0.01 <= fps <= 1000:
        raise ValueError(f"bad fps {fps}")
    return ["-f", "rawvideo", "-pix_fmt", "rgb24", "-video_size", f"{width}x{height}", "-framerate", _fmt_fps(fps), "-i", name]


def _head(ffmpeg: str) -> list[str]:
    return [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error"]


def _pre_filter(denoise: str) -> str:
    if denoise not in _DENOISE_FILTERS:
        raise ValueError(f"unknown denoise {denoise!r}")
    return _DENOISE_FILTERS[denoise]


def _paletteuse(dither: str, transparency_opt: bool, new_palette: bool) -> str:
    if dither not in _DITHER_ARGS or dither == "auto":
        raise ValueError(f"unresolved dither {dither!r}")
    parts = [_DITHER_ARGS[dither]]
    if transparency_opt:
        parts.append("diff_mode=rectangle")
    if new_palette:
        parts.append("new=1")
    return "paletteuse=" + ":".join(parts)


def _palettegen(colors: int, stats_mode: str, transparency_opt: bool) -> str:
    if stats_mode not in _STATS_MODES:
        raise ValueError(f"unknown stats_mode {stats_mode!r}")
    return f"palettegen=max_colors={int(colors)}:stats_mode={stats_mode}:reserve_transparent={1 if transparency_opt else 0}"


def palettegen_argv(ffmpeg: str, in_name: str, out_name: str, width: int, height: int, fps: float, colors: int,
                    stats_mode: str, transparency_opt: bool, denoise: str = "off") -> list[str]:
    """Pass 1 of the global-palette encode: gather colour statistics over the whole clip into one palette image."""
    _check_geometry(width, height, colors)
    chain = ",".join(p for p in (_pre_filter(denoise), _palettegen(colors, stats_mode, transparency_opt)) if p)
    return [*_head(ffmpeg), *_raw_input(width, height, fps, in_name), "-vf", chain, "-frames:v", "1", "-update", "1", out_name]


def paletteuse_argv(ffmpeg: str, in_name: str, palette_name: str, out_name: str, width: int, height: int, fps: float,
                    colors: int, dither: str, transparency_opt: bool, loop: int, denoise: str = "off") -> list[str]:
    """Pass 2: map every frame onto the palette, with optional changed-rectangle (transparency) optimisation."""
    _check_geometry(width, height, colors)
    pre = _pre_filter(denoise)
    first = f"[0:v]{pre}[v];[v][1:v]" if pre else "[0:v][1:v]"
    graph = f"{first}{_paletteuse(dither, transparency_opt, False)}"
    return [*_head(ffmpeg), *_raw_input(width, height, fps, in_name), "-i", palette_name, "-filter_complex", graph,
            *passthrough_args(ffmpeg), "-loop", str(_check_loop(loop)), "-f", "gif", out_name]


def per_frame_argv(ffmpeg: str, in_name: str, out_name: str, width: int, height: int, fps: float, colors: int,
                   dither: str, transparency_opt: bool, loop: int, denoise: str = "off") -> list[str]:
    """Single pass with a fresh palette for every frame (local colour tables). `transparency_opt` is accepted but ignored."""
    _check_geometry(width, height, colors)
    pre = _pre_filter(denoise)
    # Local palettes and changed-rectangle (transparent) frames do not mix: the unchanged pixels would be re-read
    # through the wrong colour table. Per-frame palettes therefore always encode whole frames.
    graph = (f"[0:v]{pre}[s];[s]" if pre else "[0:v]") + (
        f"split[a][b];[a]{_palettegen(colors, 'single', False)}[p];[b][p]{_paletteuse(dither, False, True)}"
    )
    return [*_head(ffmpeg), *_raw_input(width, height, fps, in_name), "-filter_complex", graph,
            *passthrough_args(ffmpeg), "-loop", str(_check_loop(loop)), "-f", "gif", out_name]


def naive_argv(ffmpeg: str, in_name: str, out_name: str, width: int, height: int, fps: float) -> list[str]:
    """What `ffmpeg -i in out.gif` does: fixed default palette, no optimisation. The baseline for compression ratios."""
    _check_geometry(width, height, 256)
    return [*_head(ffmpeg), *_raw_input(width, height, fps, in_name), *passthrough_args(ffmpeg), "-f", "gif", out_name]


def gifsicle_argv(gifsicle: str, in_name: str, out_name: str) -> list[str]:
    return [gifsicle, "-O3", "--no-warnings", in_name, "-o", out_name]


def _check_loop(loop: int) -> int:
    if not isinstance(loop, int) or isinstance(loop, bool) or not -1 <= loop <= 65535:
        raise ValueError(f"bad loop value {loop!r}")
    return loop


def run(argv: Sequence[str], cwd: str, timeout: float = DEFAULT_TIMEOUT_S, check: Check = check_interrupt) -> None:
    """Run a fixed argv list (never a shell string) in `cwd`; polls for interruption and kills on timeout or cancel."""
    log_path = os.path.join(cwd, "tool.log")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with open(log_path, "wb") as log:
        proc = subprocess.Popen(list(argv), cwd=cwd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=flags)
        deadline = time.monotonic() + timeout
        try:
            while proc.poll() is None:
                check()
                if time.monotonic() > deadline:
                    raise FfmpegError(f"{os.path.basename(argv[0])} timed out after {timeout:g}s")
                time.sleep(0.05)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    if proc.returncode != 0:
        with open(log_path, "rb") as fh:
            tail = fh.read()[-600:].decode("utf-8", "replace").strip()
        raise FfmpegError(f"{os.path.basename(argv[0])} exited {proc.returncode}: {tail}")
