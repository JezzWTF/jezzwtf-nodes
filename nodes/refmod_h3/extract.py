"""Visual and audio extraction for H3 RefMods (VAE-encode only, no training),
plus the folder media loader and the cosmetic sidecars (thumbnail, waveform peaks).
"""
from __future__ import annotations

import io
import json
import logging
import math
import os
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import torch
from PIL import Image

from . import _comfy
from ._types import RefModError
from .bundle import (
    AUDIO_CHANNELS, AUDIO_FRAMES_PER_SECOND, AUDIO_SAMPLE_RATE, AUDIO_SAMPLES_PER_FRAME,
    VISUAL_CHANNELS, RefMod,
)

log = logging.getLogger("jezzwtf.refmod_h3")

H3_FPS = 24
VIDEO_FRAME_CAP = 16          # Bake's per-clip cap; snaps to 5 frames on the 17k+5 grid
MIN_ENCODE_SIDE = 320         # the H3 VAE's tiled encode fails on tiny inputs
TEMPORAL_DEDUP_THRESHOLD = 0.02
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v")
AUDIO_CHUNK_SAMPLES = max(AUDIO_SAMPLES_PER_FRAME, round(10 * AUDIO_FRAMES_PER_SECOND) * AUDIO_SAMPLES_PER_FRAME)


def valid_len(n: int) -> int:
    """Largest valid H3 frame count (17k + 5) not above ``n``; 5 below that."""
    return 5 if n < 5 else ((n - 5) // 17) * 17 + 5


def snap_h3(n: int) -> int:
    """Grid snap for reference clips: below 5 frames a clip is a single frame."""
    return 1 if n < 5 else ((n - 5) // 17) * 17 + 5


def round32(v: float) -> int:
    return max(32, int(round(v / 32.0)) * 32)


# --------------------------------------------------------------------------- frames

def normalise_frames(x: torch.Tensor, label: str) -> torch.Tensor:
    """Accept [H,W,C], [B,H,W,C], [B,T,H,W,C], channel-first [B,3,H,W]; return [T,H,W,3] float."""
    t = x.detach()
    if t.dim() == 3:
        t = t.unsqueeze(0)
    elif t.dim() == 5:
        t = t.reshape(-1, *t.shape[2:])
    if t.dim() != 4:
        raise RefModError(f"{label}: expected an IMAGE tensor, got shape {list(x.shape)}")
    if t.shape[-1] not in (1, 3, 4) and t.shape[1] in (1, 3, 4):
        t = t.movedim(1, -1)
    if t.shape[0] == 0 or t.shape[1] == 0 or t.shape[2] == 0:
        raise RefModError(f"{label}: empty frames")
    c = t.shape[-1]
    if c == 1:
        t = t.expand(-1, -1, -1, 3)
    elif c == 4:
        t = t[..., :3]
    elif c != 3:
        raise RefModError(f"{label}: unsupported channel count {c}")
    return t.float().clamp(0.0, 1.0)


def resize_frames(frames: torch.Tensor, width: int, height: int, crop: str = "disabled",
                  method: str = "lanczos") -> torch.Tensor:
    if frames.shape[1] == height and frames.shape[2] == width:
        return frames
    bchw = frames.movedim(-1, 1)
    out = _comfy.common_upscale(bchw, width, height, method, crop)
    return out.movedim(1, -1).clamp(0.0, 1.0)


def shared_canvas(h: int, w: int, ref_resolution: int) -> tuple[int, int]:
    """(width, height) of the shared canvas derived from the first source."""
    s = min(1.0, ref_resolution / max(1, min(h, w)))
    return round32(w * s), round32(h * s)


def down_only_size(h: int, w: int, ref_resolution: int) -> tuple[int, int]:
    s = min(1.0, ref_resolution / max(1, min(h, w)))
    return round32(w * s), round32(h * s)


def min_size(w: int, h: int, minimum: int = MIN_ENCODE_SIDE) -> tuple[int, int]:
    if w >= minimum and h >= minimum:
        return w, h
    s = minimum / max(1, min(w, h))
    return max(minimum, int(math.ceil(w * s / 32.0)) * 32), max(minimum, int(math.ceil(h * s / 32.0)) * 32)


def sample_indices(total: int, count: int) -> list[int]:
    if count >= total:
        return list(range(total))
    if count <= 1:
        return [0]
    return [int(round(v)) for v in np.linspace(0, total - 1, count)]


def sample_clip(frames: torch.Tensor, cap: int) -> torch.Tensor:
    n = snap_h3(min(int(frames.shape[0]), max(1, cap)))
    return frames[sample_indices(int(frames.shape[0]), n)]


# --------------------------------------------------------------------------- visual

@dataclass
class VisualSource:
    kind: str  # "image" | "video"
    frames: torch.Tensor  # [T,H,W,3]


def order_sources(image_refs: dict[str, torch.Tensor], video_refs: dict[str, torch.Tensor],
                  folder_refs: Sequence[torch.Tensor]) -> list[VisualSource]:
    def suffix(k: str) -> int:
        tail = k.rsplit("_", 1)[-1]
        return int(tail) if tail.isdigit() else 0

    out: list[VisualSource] = []
    for k in sorted(image_refs, key=suffix):
        out.append(VisualSource("image", normalise_frames(image_refs[k], k)[:1]))
    for k in sorted(video_refs, key=suffix):
        out.append(VisualSource("video", normalise_frames(video_refs[k], k)))
    for i, item in enumerate(folder_refs):
        fr = normalise_frames(item, f"folder item {i + 1}")
        out.append(VisualSource("video" if fr.shape[0] > 1 else "image", fr))
    return out


def temporal_dedup(latent: torch.Tensor, threshold: float = TEMPORAL_DEDUP_THRESHOLD) -> torch.Tensor:
    keep = [0]
    for i in range(1, latent.shape[2]):
        cur = latent[:, :, i].float()
        prev = latent[:, :, keep[-1]].float()
        diff = (cur - prev).abs().mean() / (((cur.abs().mean() + prev.abs().mean()) / 2.0) + 1e-6)
        if float(diff) >= threshold:
            keep.append(i)
    return latent[:, :, keep]


def fit_to_budget(latent: torch.Tensor, budget: int) -> torch.Tensor:
    """Fit ``[1,24,T,H,W]`` to ``budget`` tokens: dedup then uniform resample; spatial dims kept."""
    _, _, t, h, w = latent.shape
    per_frame = (h // 2) * (w // 2)
    if per_frame > budget:
        raise RefModError(f"one reference frame needs {per_frame} tokens, over the visual budget of {budget}; "
                          "lower ref_resolution or raise max_visual_tokens")
    if t * per_frame <= budget:
        return latent
    out = temporal_dedup(latent)
    if out.shape[2] * per_frame > budget:
        out = out[:, :, sample_indices(int(out.shape[2]), budget // per_frame)]
    return out


def encode_visual(vae: object, frames: torch.Tensor) -> torch.Tensor:
    z = vae.encode(frames)  # type: ignore[attr-defined]
    if not isinstance(z, torch.Tensor) or z.dim() != 5 or z.shape[0] != 1 or z.shape[1] != VISUAL_CHANNELS:
        shape = list(z.shape) if isinstance(z, torch.Tensor) else type(z).__name__
        raise RefModError(f"VAE returned {shape}; expected [1, {VISUAL_CHANNELS}, T, H, W]. "
                          "Connect the MiniMax H3 video VAE.")
    return z.detach().to("cpu", torch.float16).contiguous()


def make_visual(name: str, vae: object, image_refs: dict[str, torch.Tensor],
                video_refs: dict[str, torch.Tensor], folder_refs: Sequence[torch.Tensor],
                ref_resolution: int = 1024, max_tokens: int = 0, budget_policy: str = "error",
                description: str = "", video_cap: int = VIDEO_FRAME_CAP) -> RefMod:
    """Extract a visual mod (``identity_encode``: plain encode, no refinement)."""
    sources = order_sources(image_refs, video_refs, folder_refs)
    if not sources:
        raise RefModError("no visual sources")
    canvas: tuple[int, int] | None = None
    if len(sources) > 1:
        _, h0, w0, _ = sources[0].frames.shape
        canvas = shared_canvas(int(h0), int(w0), ref_resolution)
    latents: list[torch.Tensor] = []
    shapes: list[str] = []
    n_img = n_vid = 0
    for src in sources:
        fr = src.frames
        if src.kind == "video":
            fr = sample_clip(fr, video_cap)
            n_vid += 1
        else:
            n_img += 1
        if canvas is not None:
            tw, th = canvas
            fr = resize_frames(fr, tw, th, crop="center")
        else:
            tw, th = down_only_size(int(fr.shape[1]), int(fr.shape[2]), ref_resolution)
            fr = resize_frames(fr, tw, th)
        mw, mh = min_size(int(fr.shape[2]), int(fr.shape[1]))
        if (mw, mh) != (fr.shape[2], fr.shape[1]):
            fr = resize_frames(fr, mw, mh, crop="center")
        if src.kind == "video" and snap_h3(int(fr.shape[0])) != fr.shape[0]:
            fr = fr[sample_indices(int(fr.shape[0]), snap_h3(int(fr.shape[0])))]
        z = encode_visual(vae, fr)
        if latents and tuple(z.shape[3:]) != tuple(latents[0].shape[3:]):
            raise RefModError("reference sources encoded to different latent sizes")
        latents.append(z)
        shapes.append(f"{fr.shape[0]}x{fr.shape[1]}x{fr.shape[2]}")
    latent = torch.cat(latents, dim=2)
    if max_tokens > 0:
        _, _, t, h, w = latent.shape
        tokens = int(t) * (int(h) // 2) * (int(w) // 2)
        if tokens > max_tokens:
            if budget_policy == "error":
                raise RefModError(f"visual reference needs {tokens} tokens, over max_visual_tokens={max_tokens}; "
                                  "nothing was saved. Use 'truncate' or raise the cap.")
            latent = fit_to_budget(latent, max_tokens)
    _, _, t, h, w = latent.shape
    kind = "video" if t > 1 else "image"
    source = "stack" if len(sources) > 1 else sources[0].kind
    return RefMod(
        name=name, kind=kind, latent=latent.contiguous(), mode="encode", source=source,
        source_shape=" +".join(shapes),
        pool=f"full-res encode {int(w) * 16}x{int(h) * 16}px, short edge <= {ref_resolution}",
        optimize_steps=0, tags=[f"{n_img} img, {n_vid} vid"], description=description.strip(),
        concept_type="identity",
    )


# --------------------------------------------------------------------------- audio

def resample_audio(wave: torch.Tensor, sr: int, target: int) -> torch.Tensor:
    if sr == target:
        return wave
    audio_mod = _comfy.optional_module("comfy.audio")
    fn = getattr(audio_mod, "resample", None) if audio_mod is not None else None
    if callable(fn):
        return fn(wave, sr, target)
    ta = _comfy.optional_module("torchaudio.functional")
    if ta is not None:
        return ta.resample(wave, sr, target)
    log.warning("refmod: no resampler available, using linear interpolation")
    n = max(1, int(round(wave.shape[-1] * target / sr)))
    flat = wave.reshape(-1, 1, wave.shape[-1]).float()
    return torch.nn.functional.interpolate(flat, size=n, mode="linear", align_corners=False).reshape(*wave.shape[:-1], n)


def prepare_waveform(audio: dict[str, object], max_seconds: float) -> torch.Tensor:
    """Validate, truncate, stereo-ise and resample to 32 kHz. Returns [1, 2, L]."""
    wave = audio.get("waveform")
    sr = audio.get("sample_rate")
    if not isinstance(wave, torch.Tensor) or wave.dim() != 3 or wave.shape[0] != 1 \
            or wave.shape[1] not in (1, 2) or wave.shape[2] < 1:
        shape = list(wave.shape) if isinstance(wave, torch.Tensor) else None
        raise RefModError(f"audio waveform must be [1, C, L] with C in (1, 2); got {shape}")
    if not isinstance(sr, (int, float)) or sr <= 0:
        raise RefModError(f"invalid audio sample rate {sr!r}")
    n = max(1, int(round(max_seconds * float(sr))))
    w = wave[:, :, :n].float()
    if w.shape[1] == 1:
        w = w.repeat(1, 2, 1)
    return resample_audio(w, int(sr), AUDIO_SAMPLE_RATE)


def _is_h3_audio_vae(vae: object) -> bool:
    fsm = getattr(vae, "first_stage_model", None)
    return fsm is not None and type(fsm).__name__ == "MiniMaxH3AudioVAE"


def _is_core_vae(vae: object) -> bool:
    """A real ``comfy.sd.VAE`` for the H3 audio VAE: its public ``encode`` takes ``[B, L, C]`` waveforms,
    manages VRAM and the tiled fallback itself (``latent_dim`` 2 = ``[B, 32, 2, T]`` latents)."""
    return callable(getattr(vae, "encode", None)) and getattr(vae, "latent_dim", None) == 2         and hasattr(vae, "patcher")


def _check_audio_latent(z: object) -> torch.Tensor:
    if not isinstance(z, torch.Tensor) or z.dim() != 4 or z.shape[0] != 1             or z.shape[1] != AUDIO_CHANNELS or z.shape[2] != 2:
        raise RefModError(f"audio VAE returned {list(z.shape) if isinstance(z, torch.Tensor) else z!r}; "
                          f"expected [1, {AUDIO_CHANNELS}, 2, t]")
    return z.detach().to("cpu", torch.float32)


def _encode_audio_core(vae: object, wave: torch.Tensor) -> torch.Tensor:
    """ComfyUI 0.44+ path: the same ``vae.encode(waveform.movedim(1, -1))`` call core's H3 reference nodes make."""
    parts: list[torch.Tensor] = []
    with torch.inference_mode():
        for start in range(0, wave.shape[-1], AUDIO_CHUNK_SAMPLES):
            chunk = wave[:, :, start:start + AUDIO_CHUNK_SAMPLES]
            parts.append(_check_audio_latent(vae.encode(chunk.movedim(1, -1))))  # type: ignore[attr-defined]
    return torch.cat(parts, dim=-1).contiguous()


def _encode_audio_direct(vae: object, wave: torch.Tensor) -> torch.Tensor:
    """Fallback for builds whose VAE wrapper cannot take the waveform: drive the first-stage model directly."""
    mm = _comfy.optional_module("comfy.model_management")
    if mm is not None:
        mm.load_models_gpu([vae.patcher], memory_required=0, force_full_load=True)  # type: ignore[attr-defined]
    device = getattr(vae, "device", torch.device("cpu"))
    dtype = getattr(vae, "vae_dtype", torch.float32)
    model = vae.first_stage_model  # type: ignore[attr-defined]
    ctx_fn = getattr(mm, "cuda_device_context", None) if mm is not None else None
    parts: list[torch.Tensor] = []
    with torch.inference_mode():
        for start in range(0, wave.shape[-1], AUDIO_CHUNK_SAMPLES):
            chunk = wave[:, :, start:start + AUDIO_CHUNK_SAMPLES].to(device=device, dtype=dtype)
            if callable(ctx_fn):
                with ctx_fn(device):
                    z = model.encode(chunk)
            else:
                z = model.encode(chunk)
            parts.append(_check_audio_latent(z))
    return torch.cat(parts, dim=-1).contiguous()


def encode_audio(vae: object, wave: torch.Tensor) -> torch.Tensor:
    if not _is_h3_audio_vae(vae):
        raise RefModError("audio_vae is not the MiniMax H3 audio VAE (MiniMaxH3AudioVAE); connect the H3 audio VAE")
    if _is_core_vae(vae):
        try:
            return _encode_audio_core(vae, wave)
        except RefModError:
            raise
        except Exception as exc:
            log.warning("refmod: core audio VAE encode failed (%s); retrying on the first-stage model", exc)
    return _encode_audio_direct(vae, wave)


def truncate_audio_latent(latent: torch.Tensor, max_tokens: int, policy: str) -> torch.Tensor:
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 0:
        raise RefModError(f"audio max_tokens must be a non-negative integer, got {max_tokens!r}")
    t = int(latent.shape[-1])
    if max_tokens > 0 and 2 * t > max_tokens:
        if policy == "error" or max_tokens < 2:
            raise RefModError(f"audio reference needs {2 * t} tokens, over audio_max_tokens={max_tokens}; "
                              "shorten the clip or raise the cap")
        latent = latent[..., : max_tokens // 2]
    return latent


def make_audio(vae: object, audio: dict[str, object], name: str, max_seconds: float, max_tokens: int,
               policy: str, description: str, concept_type: str) -> RefMod:
    wave = prepare_waveform(audio, max_seconds)
    latent = truncate_audio_latent(encode_audio(vae, wave), max_tokens, policy)
    return RefMod(name=name, kind="audio", latent=latent, mode="encode", source="audio",
                  source_shape=f"{latent.shape[-1]}", pool=f"{AUDIO_SAMPLE_RATE} Hz stereo",
                  description=description.strip(), concept_type=concept_type, sample_rate=AUDIO_SAMPLE_RATE)


# --------------------------------------------------------------------------- folder loader

def resolve_folder(folder: str) -> str:
    f = str(folder or "").strip().strip('"').strip("'")
    if not f:
        path = _comfy.input_dir()
    elif os.path.isabs(f):
        path = os.path.normpath(f)
    else:
        path = os.path.join(_comfy.input_dir(), f)
    if not os.path.isdir(path):
        raise RefModError(f"folder not found: {path}")
    return path


def folder_media(path: str, max_items: int) -> list[str]:
    names = sorted(os.listdir(path))
    imgs = [n for n in names if n.lower().endswith(IMAGE_EXTS) and os.path.isfile(os.path.join(path, n))]
    vids = [n for n in names if n.lower().endswith(VIDEO_EXTS) and os.path.isfile(os.path.join(path, n))]
    return [os.path.join(path, n) for n in (imgs + vids)[: max(1, max_items)]]


def folder_change_key(folder: str, max_items: int) -> str:
    try:
        files = folder_media(resolve_folder(folder), max_items)
    except RefModError:
        return "missing"
    parts = []
    for f in files:
        st = os.stat(f)
        parts.append(f"{os.path.basename(f)}:{st.st_size}:{int(st.st_mtime)}")
    return "|".join(parts)


def _down_to_edge(w: int, h: int, max_edge: int) -> tuple[int, int]:
    long = max(w, h)
    if long <= max_edge:
        return w, h
    s = max_edge / long
    return max(1, int(round(w * s))), max(1, int(round(h * s)))


def load_image_file(path: str, max_edge: int) -> torch.Tensor:
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = _down_to_edge(im.width, im.height, max_edge)
        if (w, h) != im.size:
            im = im.resize((w, h), Image.LANCZOS)
        arr = np.asarray(im, dtype=np.float32) / 255.0
    return torch.from_numpy(arr.copy()).unsqueeze(0)


def _pick_frames(total: int, max_frames: int) -> list[int] | None:
    if total <= 0 or total <= max_frames:
        return None
    if max_frames <= 1:
        return [0]
    return sorted({int(round(i * (total - 1) / (max_frames - 1))) for i in range(max_frames)})


def _shrink_frame(fr: np.ndarray, max_edge: int) -> np.ndarray:
    """uint8 RGB frame downscaled so its long edge is at most ``max_edge``."""
    h, w = fr.shape[:2]
    tw, th = _down_to_edge(w, h, max_edge)
    if (tw, th) != (w, h):
        fr = np.asarray(Image.fromarray(fr).resize((tw, th), Image.BILINEAR))
    return np.ascontiguousarray(fr, dtype=np.uint8)


def _frames_to_tensor(frames: list[np.ndarray], max_edge: int) -> torch.Tensor:
    """Float [T,H,W,3] in 0..1; frames stay uint8 until this final conversion."""
    if not frames:
        raise RefModError("video has no frames")
    return torch.from_numpy(np.stack([_shrink_frame(fr, max_edge) for fr in frames]).astype(np.float32) / 255.0)


def _reservoir(frames_iter: object, max_frames: int, prepare: Callable[[np.ndarray], np.ndarray] | None = None
               ) -> list[np.ndarray]:
    """Uniform sample of ``max_frames`` items; ``prepare`` (downscale) runs only on frames that are kept."""
    rng = random.Random(0)
    keep: list[tuple[int, np.ndarray]] = []
    for i, fr in enumerate(frames_iter):  # type: ignore[call-overload]
        if len(keep) < max_frames:
            keep.append((i, prepare(fr) if prepare else fr))
        else:
            j = rng.randint(0, i)
            if j < max_frames:
                keep[j] = (i, prepare(fr) if prepare else fr)
    keep.sort(key=lambda p: p[0])
    return [f for _, f in keep]


def _read_cv2_frames(cv2: object, path: str, max_edge: int, max_frames: int) -> tuple[list[np.ndarray], int]:
    """Sequential read that only decodes/converts the frames it keeps; returns (frames, frames actually seen)."""
    cap = cv2.VideoCapture(path)  # type: ignore[attr-defined]
    try:
        if not cap.isOpened():
            raise RefModError(f"cannot open video {path}")
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)  # type: ignore[attr-defined]
        pick = _pick_frames(total, max_frames) if total > 0 else None
        wanted = set(pick) if pick is not None else None

        def retrieve() -> np.ndarray | None:
            ok, fr = cap.retrieve()
            if not ok or fr is None:
                return None
            return _shrink_frame(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB), max_edge)  # type: ignore[attr-defined]

        if total <= 0:  # unknown length: reservoir over the stream, shrinking only what is kept
            def stream() -> object:
                while cap.grab():
                    fr = retrieve()
                    if fr is not None:
                        yield fr
            frames = _reservoir(stream(), max_frames)
            return frames, -1
        frames: list[np.ndarray] = []
        seen = 0
        while cap.grab():
            if (wanted is None or seen in wanted) and len(frames) < max_frames:
                fr = retrieve()
                if fr is not None:
                    frames.append(fr)
            seen += 1
            if wanted is not None and frames and len(frames) >= max_frames:
                break  # stop at max_frames; the rest is never decoded
        return frames, seen
    finally:
        cap.release()


def load_video_file(path: str, max_edge: int, max_frames: int) -> torch.Tensor:
    cv2 = _comfy.optional_module("cv2")
    if cv2 is not None:
        frames, seen = _read_cv2_frames(cv2, path, max_edge, max_frames)
        if not frames:
            raise RefModError("video has no frames")
        if seen > max_frames and len(frames) < max_frames:
            # the container reported the wrong frame count (picks fell past the real end, or the real
            # stream is longer): sample again with a reservoir, which does not depend on the count
            cap = cv2.VideoCapture(path)

            def stream() -> object:
                try:
                    while cap.grab():
                        ok, fr = cap.retrieve()
                        if ok and fr is not None:
                            yield cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
                finally:
                    cap.release()
            frames = _reservoir(stream(), max_frames, lambda f: _shrink_frame(f, max_edge))
        return _frames_to_tensor(frames, max_edge)
    imageio = _comfy.optional_module("imageio.v3")
    if imageio is None:
        raise RefModError("reading videos needs opencv-python or imageio")
    frames = _reservoir((np.asarray(f)[..., :3] for f in imageio.imiter(path)), max_frames,
                        lambda f: _shrink_frame(np.asarray(f, dtype=np.uint8), max_edge))
    return _frames_to_tensor(frames, max_edge)


def load_folder(folder: str, max_items: int, max_edge: int, max_frames: int = 240) -> tuple[list[torch.Tensor], list[str]]:
    path = resolve_folder(folder)
    files = folder_media(path, max_items)
    items: list[torch.Tensor] = []
    skipped: list[str] = []
    bar = _comfy.progress_bar(len(files))
    for i, f in enumerate(files):
        try:
            if f.lower().endswith(IMAGE_EXTS):
                items.append(load_image_file(f, max_edge))
            else:
                items.append(load_video_file(f, max_edge, max_frames))
        except Exception as exc:
            skipped.append(f"{os.path.basename(f)} ({exc})")
        _comfy.progress_update(bar, i + 1, len(files))
    if skipped:
        log.warning("refmod folder: skipped unreadable files: %s", "; ".join(skipped))
    if not items:
        raise RefModError(f"no readable images or videos in {path}")
    return items, skipped


# --------------------------------------------------------------------------- sidecars

def face_thumbnail(frame: torch.Tensor, size: int = 256) -> bytes:
    """Square crop (vertically offset 20 % of the excess: faces sit high), JPEG q88."""
    arr = (normalise_frames(frame, "thumb")[0].numpy() * 255.0).round().astype(np.uint8)
    h, w = arr.shape[:2]
    side = min(h, w)
    x0 = (w - side) // 2
    y0 = int(round((h - side) * 0.2))
    im = Image.fromarray(arr[y0:y0 + side, x0:x0 + side]).resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def waveform_peaks(audio: dict[str, object], max_seconds: float, bins: int = 64) -> tuple[list[float], float]:
    wave = audio.get("waveform")
    sr = audio.get("sample_rate")
    if not isinstance(wave, torch.Tensor) or not isinstance(sr, (int, float)) or sr <= 0:
        return [], 0.0
    mono = wave.float().abs().mean(dim=1).reshape(-1)
    mono = mono[: max(1, int(round(max_seconds * float(sr))))]
    seconds = float(mono.shape[0]) / float(sr)
    if mono.numel() == 0:
        return [0.0] * bins, seconds
    edges = np.linspace(0, mono.numel(), bins + 1).astype(int)
    vals: list[float] = []
    for a, b in zip(edges[:-1], edges[1:]):
        seg = mono[a:max(b, a + 1)]
        vals.append(float(torch.sqrt((seg * seg).mean())) if seg.numel() else 0.0)
    peak = max(vals) or 1.0
    return [round(v / peak, 3) for v in vals], seconds


def write_sidecars(stem: str, thumb_frame: torch.Tensor | None, audio: dict[str, object] | None,
                   audio_max_seconds: float) -> None:
    from .library import sidecar_path, thumb_path
    try:
        if thumb_frame is not None:
            with open(thumb_path(stem), "wb") as fh:
                fh.write(face_thumbnail(thumb_frame))
        else:
            if os.path.isfile(thumb_path(stem)):
                os.remove(thumb_path(stem))
    except Exception as exc:
        log.warning("refmod: thumbnail sidecar failed: %s", exc)
    try:
        data: dict[str, object] = {"created": int(time.time())}
        if audio is not None:
            peaks, seconds = waveform_peaks(audio, audio_max_seconds)
            data["peaks"] = peaks
            data["seconds"] = round(seconds, 3)
        with open(sidecar_path(stem), "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception as exc:
        log.warning("refmod: json sidecar failed: %s", exc)
