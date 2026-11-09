"""Live sampling preview: an OUTER_SAMPLE model wrapper that replaces the step callback,
streams its own previews over the websocket and suppresses ComfyUI's default preview.

Wire protocol (load-bearing, shared with KJNodes' "Model Preview Override" and preview
mirror nodes): wrapper key and websocket event ``kj_preview_override``.
"""
from __future__ import annotations

import base64
import io
import logging
import math
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import torch
from PIL import Image

from . import _comfy

log = logging.getLogger("jezzwtf.refmod_h3")

WRAPPER_KEY = "kj_preview_override"
EVENT = "kj_preview_override"
VIDEO_TAE_PREFIXES = ("taehv", "lighttaew", "lighttaehy", "taeltx", "taew", "taeh3")
H264_ATTEMPTS: tuple[tuple[str, dict[str, str]], ...] = (
    ("libx264", {"preset": "ultrafast", "tune": "zerolatency", "crf": "28"}),
    ("h264_nvenc", {"preset": "p1", "rc": "vbr", "cq": "23"}),
    ("h264_nvenc", {"preset": "p1"}),
)

Payload = dict[str, object]


# --------------------------------------------------------------------------- media encoding (pure)

def fit_size(w: int, h: int, max_res: int) -> tuple[int, int]:
    if max_res <= 0 or max(w, h) <= max_res:
        return w, h
    s = max_res / max(w, h)
    return max(1, int(round(w * s))), max(1, int(round(h * s)))


def _resize(img: Image.Image, max_res: int) -> Image.Image:
    size = fit_size(img.width, img.height, max_res)
    return img if size == img.size else img.resize(size, Image.LANCZOS)


def encode_jpeg(img: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=int(quality))
    return buf.getvalue()


def encode_webp(frames: list[Image.Image], fps: float, quality: int) -> bytes:
    buf = io.BytesIO()
    frames[0].save(buf, format="WEBP", save_all=True, append_images=frames[1:], loop=0,
                   duration=max(1, int(round(1000 / max(fps, 0.1)))), quality=int(quality))
    return buf.getvalue()


def encode_mp4(frames: list[Image.Image], fps: float, audio: np.ndarray | None = None,
               sample_rate: int = 0) -> bytes | None:
    """Fragmented H.264 MP4 via PyAV, or None when no encoder works."""
    av = _comfy.optional_module("av")
    if av is None:
        return None
    from fractions import Fraction
    w, h = frames[0].size
    w, h = w - (w % 2), h - (h % 2)
    rate = Fraction(fps).limit_denominator(1000) if fps > 0 else Fraction(12)
    for codec, opts in H264_ATTEMPTS:
        buf = io.BytesIO()
        try:
            container = av.open(buf, mode="w", format="mp4",
                                options={"movflags": "frag_keyframe+empty_moov+default_base_moof"})
            stream = container.add_stream(codec, rate=rate, options=opts)
            stream.width, stream.height, stream.pix_fmt = w, h, "yuv420p"
            astream = None
            if audio is not None and sample_rate > 0:
                astream = container.add_stream("aac", rate=sample_rate, layout="stereo")
            for img in frames:
                frame = av.VideoFrame.from_image(img.convert("RGB").crop((0, 0, w, h)))
                for pkt in stream.encode(frame):
                    container.mux(pkt)
            for pkt in stream.encode():
                container.mux(pkt)
            if astream is not None and audio is not None:
                stereo = audio if audio.shape[0] == 2 else np.repeat(audio[:1], 2, axis=0)
                aframe = av.AudioFrame.from_ndarray(np.ascontiguousarray(stereo.astype(np.float32)),
                                                    format="fltp", layout="stereo")
                aframe.sample_rate = sample_rate
                for pkt in astream.encode(aframe):
                    container.mux(pkt)
                for pkt in astream.encode():
                    container.mux(pkt)
            container.close()
            return buf.getvalue()
        except Exception as exc:
            log.debug("preview mp4 encoder %s failed: %s", codec, exc)
            continue
    return None


def api_nodes_disabled() -> bool:
    cli = _comfy.optional_module("comfy.cli_args")
    return bool(getattr(getattr(cli, "args", None), "disable_api_nodes", False))


def tensor_to_images(frames: torch.Tensor) -> list[Image.Image]:
    """[T,H,W,3] float 0..1 or uint8 -> PIL images."""
    arr = frames.detach().float().cpu()
    if arr.max() > 1.5:
        arr = arr / 255.0
    u8 = (arr.clamp(0, 1) * 255.0).round().to(torch.uint8).numpy()
    return [Image.fromarray(f) for f in u8]


def spectrogram_png(audio: np.ndarray, width: int = 512, height: int = 64) -> str:
    """Log-magnitude spectrogram strip (custom warm colour map) as base64 PNG."""
    mono = audio.mean(axis=0) if audio.ndim > 1 else audio
    n_fft = 256
    if mono.size < n_fft:
        mono = np.pad(mono, (0, n_fft - mono.size))
    hop = max(1, (mono.size - n_fft) // max(1, width - 1))
    cols = []
    win = np.hanning(n_fft)
    for i in range(width):
        s = min(i * hop, mono.size - n_fft)
        cols.append(np.abs(np.fft.rfft(mono[s:s + n_fft] * win))[: n_fft // 2])
    spec = np.log1p(np.stack(cols, axis=1) * 10.0)
    spec = spec / (spec.max() or 1.0)
    idx = np.linspace(0, spec.shape[0] - 1, height).astype(int)[::-1]
    v = spec[idx]
    rgb = np.stack([np.clip(v * 2.2, 0, 1), np.clip(v * 1.6 - 0.25, 0, 1), np.clip(0.25 + v * 0.9 - v * v, 0, 1)],
                   axis=-1)
    im = Image.fromarray((rgb * 255).astype(np.uint8))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


# --------------------------------------------------------------------------- metrics (pure)

@dataclass
class StepMetrics:
    prev: torch.Tensor | None = None
    last_time: float = 0.0
    times: list[float] = field(default_factory=list)

    def delta(self, x0: torch.Tensor) -> float:
        cur = x0.detach().float().cpu()
        d = 0.0
        if self.prev is not None and self.prev.shape == cur.shape:
            d = float(torch.linalg.vector_norm(cur - self.prev) / math.sqrt(max(1, cur.numel())))
        self.prev = cur
        return d

    def tick(self) -> tuple[float, float]:
        now = time.perf_counter()
        ms = (now - self.last_time) * 1000.0 if self.last_time else 0.0
        self.last_time = now
        if ms > 0:
            self.times.append(ms)
            self.times = self.times[-8:]
        avg = sum(self.times) / len(self.times) if self.times else 0.0
        return ms, avg


# --------------------------------------------------------------------------- encoder thread

@dataclass
class _Job:
    images: list[Image.Image]
    meta: Payload
    fps: float
    audio: np.ndarray | None
    audio_rate: int


class PreviewEncoder:
    """Background encoder with a bounded queue: frames are dropped, sampling never blocks."""

    def __init__(self, node_id: str, max_res: int, quality: int) -> None:
        self.node_id = node_id
        self.max_res = max_res
        self.quality = quality
        self.q: queue.Queue[_Job | None] = queue.Queue(maxsize=2)
        self._stop = threading.Event()
        self.webp_only = api_nodes_disabled()
        self.thread = threading.Thread(target=self._run, name="jwtf-preview", daemon=True)
        self.thread.start()

    def submit(self, job: _Job) -> None:
        try:
            self.q.put_nowait(job)
        except queue.Full:
            pass

    def stop(self, timeout: float = 5.0) -> None:
        """Ask the thread to finish queued jobs and exit; works even when the queue stays full."""
        self._stop.set()
        try:
            self.q.put(None, timeout=timeout)
        except queue.Full:
            pass
        self.thread.join(timeout)

    def _run(self) -> None:
        while True:
            try:
                job = self.q.get(timeout=0.25)
            except queue.Empty:
                if self._stop.is_set():
                    return
                continue
            if job is None:
                return
            try:
                self._send(job)
            except Exception as exc:  # pragma: no cover - runtime only
                log.debug("preview encode failed: %s", exc)

    def _send(self, job: _Job) -> None:
        imgs = [_resize(i, self.max_res) for i in job.images]
        w, h = imgs[0].size
        payload: Payload = dict(job.meta)
        if len(imgs) > 1:
            data = None if self.webp_only else encode_mp4(imgs, job.fps, job.audio, job.audio_rate)
            if data is not None:
                mime = "video/mp4"
            else:
                data, mime = encode_webp(imgs, job.fps, self.quality), "image/webp"
            payload["fps"] = job.fps
        else:
            data, mime = encode_jpeg(imgs[0], self.quality), "image/jpeg"
        payload.update({"node_id": self.node_id, "image": base64.b64encode(data).decode("ascii"),
                        "mime": mime, "w": w, "h": h})
        _comfy.send_sync(EVENT, payload)


# --------------------------------------------------------------------------- latent -> frames

def pick_even(n: int, k: int) -> list[int]:
    if k >= n:
        return list(range(n))
    if k <= 1:
        return [0]
    return [int(round(i * (n - 1) / (k - 1))) for i in range(k)]


class Latent2RGB:
    def __init__(self, factors: list[list[float]], bias: list[float] | None) -> None:
        self.factors = torch.tensor(factors, dtype=torch.float32).transpose(0, 1)  # [3, C]
        self.bias = torch.tensor(bias, dtype=torch.float32) if bias is not None else None

    def frames(self, x: torch.Tensor, count: int) -> torch.Tensor:
        """[B,C,T,H,W] or [B,C,H,W] -> uint8 [T,H,W,3]."""
        lat = x[0].float().cpu()
        if lat.dim() == 3:
            lat = lat.unsqueeze(1)
        idx = pick_even(int(lat.shape[1]), count)
        out = []
        for t in idx:
            rgb = torch.nn.functional.linear(lat[:, t].movedim(0, -1), self.factors, self.bias)
            out.append(((rgb + 1.0) * 127.5).clamp(0, 255).to(torch.uint8))
        return torch.stack(out)


def is_video_tae(name: str) -> bool:
    """Video tiny VAEs decode whole clips as a ``comfy.sd.VAE``; the list lives in core's ``latent_preview``."""
    lower = name.lower()
    lp = _comfy.optional_module("latent_preview")
    core = tuple(str(n).lower() for n in getattr(lp, "VIDEO_TAES", ()) or ())
    return any(lower.startswith(p) for p in VIDEO_TAE_PREFIXES + core)


def load_tiny_vae(name: str, latent_channels: int) -> object | None:
    if not name or name == "none":
        return None
    path = _comfy.full_path("vae_approx", name)
    if path is None:
        log.warning("preview: tiny VAE %s not found", name)
        return None
    try:
        utils = _comfy.optional_module("comfy.utils")
        if is_video_tae(name):
            sd_mod = _comfy.optional_module("comfy.sd")
            vae = sd_mod.VAE(sd=utils.load_torch_file(path))  # type: ignore[union-attr]
            fsm = getattr(vae, "first_stage_model", None)
            if fsm is not None and hasattr(fsm, "show_progress_bar"):
                fsm.show_progress_bar = False
            ch = getattr(vae, "latent_channels", latent_channels)
            if ch != latent_channels:
                log.warning("preview: tiny VAE %s has %s channels, model has %s; ignored", name, ch, latent_channels)
                return None
            return vae
        taesd_mod = _comfy.optional_module("comfy.taesd.taesd")
        mm = _comfy.optional_module("comfy.model_management")
        dec = taesd_mod.TAESD(None, path, latent_channels=latent_channels)  # type: ignore[union-attr]
        return dec.to(mm.get_torch_device()) if mm is not None else dec
    except Exception as exc:
        log.warning("preview: tiny VAE %s failed to load (%s); ignored", name, exc)
        return None


def tiny_decode(tiny: object, x: torch.Tensor, count: int) -> torch.Tensor:
    """Tiny VAE decode of the first ``count`` evenly-picked frames -> float [T,H,W,3] in 0..1."""
    if x.dim() == 5:
        idx = pick_even(int(x.shape[2]), max(1, count))
        if hasattr(tiny, "first_stage_model"):  # video TAE wrapped as a VAE: decode the clip
            out = tiny.decode(x[:1])  # type: ignore[attr-defined]
            out = out.reshape(-1, *out.shape[-3:])
            return out[pick_even(int(out.shape[0]), max(1, count))].float().cpu()
        frames = [tiny.decode(x[:1, :, t].to(_device_of(tiny)))[0] for t in idx]  # type: ignore[attr-defined]
        return torch.stack(frames).movedim(1, -1).add(1).div(2).clamp(0, 1).float().cpu()
    dec = tiny.decode(x[:1].to(_device_of(tiny)))  # type: ignore[attr-defined]
    return dec.movedim(1, -1).add(1).div(2).clamp(0, 1).float().cpu()


def _device_of(module: object) -> torch.device:
    try:
        return next(module.parameters()).device  # type: ignore[attr-defined]
    except Exception:
        return torch.device("cpu")


def unpack_parts(x: torch.Tensor, shapes: list[torch.Size]) -> list[torch.Tensor]:
    """Split a latent packed by ``CFGGuider.sample`` ([B,1,N]) into its parts; empty when it is not packed."""
    if len(shapes) <= 1:
        return []
    if getattr(x, "is_nested", False):
        return list(x.unbind())
    utils = _comfy.optional_module("comfy.utils")
    if utils is not None and hasattr(utils, "unpack_latents"):
        return list(utils.unpack_latents(x, shapes))
    return []


# --------------------------------------------------------------------------- default-preview suppression

def _all_subclasses(cls: type) -> list[type]:
    out = [cls]
    for sub in cls.__subclasses__():
        out.extend(_all_subclasses(sub))
    return out


class SuppressDefaultPreview:
    def __init__(self) -> None:
        self.saved: list[tuple[type, Callable[..., object]]] = []

    def __enter__(self) -> "SuppressDefaultPreview":
        lp = _comfy.optional_module("latent_preview")
        base = getattr(lp, "LatentPreviewer", None) if lp is not None else None
        if isinstance(base, type):
            for cls in _all_subclasses(base):
                fn = cls.__dict__.get("decode_latent_to_preview_image")
                if fn is not None:
                    self.saved.append((cls, fn))
                    setattr(cls, "decode_latent_to_preview_image", lambda self, fmt, x0: None)
        return self

    def __exit__(self, *_: object) -> None:
        for cls, fn in self.saved:
            setattr(cls, "decode_latent_to_preview_image", fn)
        self.saved.clear()


# --------------------------------------------------------------------------- wrapper

class PreviewWrapper:
    """OUTER_SAMPLE wrapper. ``node_id`` is read by preview mirror nodes."""

    def __init__(self, max_res: int, node_id: str, quality: int = 80, suppress_default: bool = True,
                 frames: int = 1, fps: int = 12, vae: object | None = None, tiny_vae: str = "none",
                 audio_vae: object | None = None) -> None:
        self.max_res = int(max_res)
        self.node_id = str(node_id)
        self.quality = int(quality)
        self.suppress_default = suppress_default
        self.frames = max(1, int(frames))
        self.fps = max(1, int(fps))
        self.vae = vae
        self.tiny_vae_name = tiny_vae
        self.audio_vae = audio_vae

    # -- helpers
    def _model_info(self, mp: object) -> tuple[object, bool, int]:
        model = getattr(mp, "model", None)
        fmt = getattr(model, "latent_format", None)
        is_ltx = "LTX" in type(fmt).__name__ if fmt is not None else False
        channels = int(getattr(fmt, "latent_channels", 4) or 4)
        return fmt, is_ltx, channels

    def _keyframes(self, guider: object) -> int:
        try:
            conds = getattr(guider, "original_conds", {}) or {}
            pos = conds.get("positive") if isinstance(conds, dict) else None
            idxs = pos[0].get("keyframe_idxs") if pos else None  # type: ignore[index, union-attr]
            if isinstance(idxs, torch.Tensor):
                return int(torch.unique(idxs[0, 0, :, 0]).numel())
        except Exception:
            pass
        return 0

    def _db_curve(self, sampler: object, sigmas: torch.Tensor, ms: object) -> list[float | None] | None:
        extra = getattr(sampler, "extra_options", None)
        if not isinstance(extra, dict):
            return None
        for v in extra.values():
            xs, ys = getattr(v, "db_curve_xs", None), getattr(v, "db_curve_ys", None)
            if not xs or not ys:
                continue
            try:
                s0 = float(ms.percent_to_sigma(float(getattr(v, "start_percent", 0.0))))  # type: ignore[attr-defined]
                s1 = float(ms.percent_to_sigma(float(getattr(v, "end_percent", 1.0))))  # type: ignore[attr-defined]
            except Exception:
                s0, s1 = float(sigmas[0]), float(sigmas[-1])
            out: list[float | None] = []
            for s in sigmas.tolist():
                if not (min(s0, s1) <= s <= max(s0, s1)) or s0 == s1:
                    out.append(None)
                    continue
                out.append(float(np.interp((s0 - s) / (s0 - s1), list(xs), list(ys))))
            return out
        return None

    def __call__(self, executor: Callable[..., torch.Tensor], noise: torch.Tensor, latent_image: torch.Tensor,
                 sampler: object, sigmas: torch.Tensor, denoise_mask: torch.Tensor | None,
                 callback: Callable[..., object] | None, disable_pbar: bool, seed: int | None,
                 latent_shapes: list[torch.Size] | None = None, **kwargs: object) -> torch.Tensor:
        encoder = PreviewEncoder(self.node_id, self.max_res, self.quality)
        suppress: SuppressDefaultPreview | None = None
        try:
            try:
                cb = self._build_callback(encoder, executor, noise, sampler, sigmas, callback, latent_shapes)
                previewing = True
            except Exception as exc:
                log.warning("preview: setup failed (%s); sampling without preview", exc)
                cb, previewing = callback, False
            if previewing and self.suppress_default:
                suppress = SuppressDefaultPreview()
                suppress.__enter__()
            return executor(noise, latent_image, sampler, sigmas, denoise_mask, cb, disable_pbar, seed,
                            latent_shapes=latent_shapes, **kwargs)
        finally:
            try:
                if suppress is not None:
                    suppress.__exit__()
            finally:
                encoder.stop(5.0)
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

    def _build_callback(self, encoder: "PreviewEncoder", executor: Callable[..., torch.Tensor], noise: torch.Tensor,
                        sampler: object, sigmas: torch.Tensor, callback: Callable[..., object] | None,
                        latent_shapes: list[torch.Size] | None) -> Callable[..., object]:
        guider = getattr(executor, "class_obj", None)
        mp = getattr(guider, "model_patcher", None)
        fmt, is_ltx, channels = self._model_info(mp)
        if latent_shapes is not None and len(latent_shapes) > 1 and len(latent_shapes[0]) >= 2:
            # audio-video latents: the format reports the widest stream (H3: 32), the picture stream is [B, C, ...]
            channels = int(latent_shapes[0][1])
        keyframes = self._keyframes(guider) if is_ltx else 0
        tiny = load_tiny_vae(self.tiny_vae_name, channels)
        rgb: Latent2RGB | None = None
        factors = getattr(fmt, "latent_rgb_factors", None)
        if factors is not None:
            rgb = Latent2RGB(factors, getattr(fmt, "latent_rgb_factors_bias", None))
        core_previewer = None
        lp = _comfy.optional_module("latent_preview")
        if lp is not None and mp is not None and fmt is not None:
            try:
                getter = getattr(lp.get_previewer, "__wrapped__", lp.get_previewer)
                core_previewer = getter(mp.load_device, fmt)  # type: ignore[attr-defined]
            except Exception:
                core_previewer = None
        metrics = StepMetrics()
        total = int(sigmas.shape[-1]) - 1
        sig_list = [float(s) for s in sigmas.tolist()]
        ms = mp.get_model_object("model_sampling") if mp is not None else None  # type: ignore[attr-defined]
        audio_dec = self._audio_setup(mp, ms, latent_shapes)
        shapes = latent_shapes

        def view(x: torch.Tensor) -> torch.Tensor:
            v = x
            if shapes is not None and len(shapes) > 1:
                v = unpack_parts(v, shapes)[0]
            if keyframes and v.dim() == 5 and v.shape[2] > keyframes:
                v = v[:, :, : v.shape[2] - keyframes]
            return v

        def frames_of(x: torch.Tensor) -> list[Image.Image]:
            nonlocal tiny
            v = view(x)
            animated = self.frames > 1 and v.dim() == 5
            if tiny is not None:
                try:
                    return tensor_to_images(tiny_decode(tiny, v, self.frames if animated else 1))
                except Exception as exc:
                    log.warning("preview: tiny VAE decode failed (%s); disabled for this run", exc)
                    tiny = None
            if is_ltx and self.vae is not None:
                try:
                    dec = self.vae.decode(v[:1])  # type: ignore[attr-defined]
                    dec = dec.reshape(-1, *dec.shape[-3:])
                    return tensor_to_images(dec[pick_even(int(dec.shape[0]), self.frames if animated else 1)])
                except Exception as exc:
                    log.debug("preview: LTX vae decode failed: %s", exc)
            if animated and rgb is not None:
                return tensor_to_images(rgb.frames(v, self.frames))
            if core_previewer is not None:
                try:
                    img = core_previewer.decode_latent_to_preview(v)  # type: ignore[attr-defined]
                    if isinstance(img, Image.Image):
                        return [img]
                except Exception:
                    pass
            if rgb is not None:
                return tensor_to_images(rgb.frames(v, 1))
            return []

        # step 0
        start: Payload = {"node_id": self.node_id, "step": 0, "total": total, "sigma": sig_list[0] if sig_list else 0.0,
                          "sigmas": sig_list}
        if ms is not None:
            db = self._db_curve(sampler, sigmas, ms)
            if db is not None:
                start["db_curve"] = db
        try:
            first = frames_of(noise * (sigmas[0] if sig_list else 1.0))
            if first:
                img = _resize(first[0], self.max_res)
                start.update({"image": base64.b64encode(encode_jpeg(img, self.quality)).decode("ascii"),
                              "w": img.width, "h": img.height})
        except Exception as exc:
            log.debug("preview step-0 image failed: %s", exc)
        _comfy.send_sync(EVENT, start)
        metrics.delta(view(noise))
        metrics.tick()

        def new_callback(step: int, x0: torch.Tensor, x: torch.Tensor, total_steps: int) -> object:
            try:
                imgs = frames_of(x0)
                if imgs:
                    d = metrics.delta(view(x0))
                    step_ms, avg = metrics.tick()
                    audio, rate, spec, out_fps = None, 0, None, float(self.fps)
                    if audio_dec is not None and len(imgs) > 1:
                        audio, rate = audio_dec(x0, len(imgs))
                        if audio is not None:
                            spec = spectrogram_png(audio)
                            out_fps = len(imgs) * rate / max(1, audio.shape[-1])
                    meta: Payload = {"step": step + 1, "total": total_steps, "sigma": sig_list[min(step, len(sig_list) - 1)],
                                     "sigmas": None, "delta": d, "step_ms": step_ms, "avg_step_ms": avg,
                                     "audio": audio is not None, "audio_spec": spec}
                    encoder.submit(_Job(imgs, meta, out_fps, audio, rate))
            except Exception as exc:
                log.debug("preview step failed: %s", exc)
            return callback(step, x0, x, total_steps) if callback is not None else None

        return new_callback

    def _audio_setup(self, mp: object, ms: object, shapes: list[torch.Size] | None = None) -> Callable[[torch.Tensor, int], tuple[np.ndarray | None, int]] | None:
        """Audio preview for audio-video models; None when unsupported."""
        mb = _comfy.optional_module("comfy.model_base")
        flow_av = getattr(getattr(mb, "ModelType", None), "FLOW_AV", None) if mb is not None else None
        model = getattr(mp, "model", None)
        if flow_av is None or getattr(model, "model_type", None) != flow_av or self.frames <= 1:
            return None
        avae = self.audio_vae
        rate = audio_vae_rate(avae)
        scale = getattr(ms, "audio_scale", None)
        if avae is None or rate <= 0 or scale is None:
            return None
        mm = _comfy.optional_module("comfy.model_management")
        loaded = False

        def decode(x0: torch.Tensor, n_frames: int) -> tuple[np.ndarray | None, int]:
            nonlocal loaded
            try:
                if not loaded and mm is not None:
                    mm.load_models_gpu([avae.patcher])  # type: ignore[union-attr]
                    loaded = True
                parts = unpack_parts(x0, shapes) if shapes is not None else []
                if not parts and getattr(x0, "is_nested", False):
                    parts = list(x0.unbind())
                lat = parts[-1] if len(parts) > 1 else None
                if lat is None:
                    return None, 0
                fsm = avae.first_stage_model  # type: ignore[union-attr]
                wav = fsm.decode((lat / float(scale)).to(getattr(avae, "device", lat.device)))  # type: ignore[arg-type]
                proc = getattr(avae, "process_output", None)
                if callable(proc):
                    wav = proc(wav)
                wav = wav[0].float().cpu()
                wav = (wav / max(1.0, 5.0 * float(wav.std()))).clamp(-1, 1)
                return wav.reshape(-1, wav.shape[-1]).numpy(), rate
            except Exception as exc:
                log.debug("preview audio decode failed: %s", exc)
                return None, 0

        return decode


def audio_vae_rate(avae: object | None) -> int:
    """Sample rate of a ``comfy.sd.VAE`` audio VAE: ``audio_sample_rate_output`` (LTX), ``audio_sample_rate``
    (H3: 32 kHz), else the first-stage model's ``output_sample_rate`` / ``sample_rate``."""
    if avae is None:
        return 0
    fsm = getattr(avae, "first_stage_model", None)
    for owner, attr in ((avae, "audio_sample_rate_output"), (avae, "audio_sample_rate"), (avae, "output_sample_rate"),
                        (fsm, "output_sample_rate"), (fsm, "sample_rate"), (avae, "sample_rate")):
        value = getattr(owner, attr, None) if owner is not None else None
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return 0


def attach_preview(model: object, max_res: int, node_id: str, quality: int, frames: int, fps: int,
                   vae: object | None, tiny_vae: str, audio_vae: object | None) -> object:
    """Clone ``model`` and attach the preview wrapper; returns the original when unsupported."""
    ext = _comfy.optional_module("comfy.patcher_extension")
    if ext is None or not hasattr(model, "clone"):
        return model
    m = model.clone()  # type: ignore[attr-defined]
    if not hasattr(m, "add_wrapper_with_key"):
        log.warning("preview: this ComfyUI has no model wrappers; preview disabled")
        return model
    wrapper = PreviewWrapper(max_res, node_id, quality, True, frames, fps, vae, tiny_vae, audio_vae)
    m.add_wrapper_with_key(ext.WrappersMP.OUTER_SAMPLE, WRAPPER_KEY, wrapper)
    return m
