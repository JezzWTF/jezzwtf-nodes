"""Pure logic for Prompt Relay: options, segment lengths, token ranges, the Gaussian-shaped
cross-attention penalty and the attention override that applies it. No ComfyUI imports."""
from __future__ import annotations

import json
import math
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal, Protocol

import torch

DEFAULT_SIGMA = 0.1448
MAX_COST = 1.0e4  # a -1e4 logit is already "never attend"; keeps fp16 finite
AttnFn = Callable[..., torch.Tensor]
Override = Callable[..., torch.Tensor]
Stream = Literal["video", "audio"]
TEXT_ATTN_MODULES: dict[str, Stream] = {"attn2": "video", "audio_attn2": "audio"}


class _TextScopeState(threading.local):
    def __init__(self) -> None:
        self.stack: list[Stream] = []


_text_scope = _TextScopeState()


@contextmanager
def text_attention_scope(stream: Stream) -> Iterator[None]:
    """Marks the attention calls made inside as genuine text cross-attention for `stream`."""
    _text_scope.stack.append(stream)
    try:
        yield
    finally:
        _text_scope.stack.pop()


def current_text_scope() -> Stream | None:
    return _text_scope.stack[-1] if _text_scope.stack else None


class _Patcher(Protocol):
    def get_model_object(self, name: str) -> object: ...
    def add_object_patch(self, name: str, obj: object) -> None: ...


def install_text_scope_hooks(patcher: _Patcher, diffusion_model: torch.nn.Module,
                             prefix: str = "diffusion_model") -> int:
    """Wrap every text cross-attention module's `forward` (LTX `attn2`, `audio_attn2`) so the
    override can tell it apart from audio<->video cross-attention. Returns the number hooked."""
    count = 0
    for name, _module in diffusion_model.named_modules():
        stream = TEXT_ATTN_MODULES.get(name.rsplit(".", 1)[-1])
        if stream is None:
            continue
        key = f"{prefix}.{name}.forward"
        inner = patcher.get_model_object(key)
        if not callable(inner):
            continue

        def wrapped(*args: object, _inner: Callable[..., object] = inner, _stream: Stream = stream,
                    **kwargs: object) -> object:
            with text_attention_scope(_stream):
                return _inner(*args, **kwargs)

        patcher.add_object_patch(key, wrapped)
        count += 1
    return count


class RelayOptions:
    def __init__(self, video_strength: float = 1.0, video_window_scale: float = 1.0,
                 audio_epsilon: float | None = None, audio_strength: float = 1.0, audio_window_scale: float = 1.0,
                 per_segment_epsilon: Sequence[float] | None = None, **_ignored: object) -> None:
        for name, v, hi in (("video_strength", video_strength, 10.0), ("audio_strength", audio_strength, 10.0),
                            ("video_window_scale", video_window_scale, 4.0),
                            ("audio_window_scale", audio_window_scale, 4.0)):
            if not 0.0 <= float(v) <= hi:
                raise ValueError(f"{name} must be in [0, {hi:g}], got {v}")
        if audio_epsilon is not None and not 0.0 < float(audio_epsilon) < 1.0:
            raise ValueError(f"audio_epsilon must be in (0, 1) or unset, got {audio_epsilon}")
        self.video_strength = float(video_strength)
        self.video_window_scale = float(video_window_scale)
        self.audio_epsilon = None if audio_epsilon is None else float(audio_epsilon)
        self.audio_strength = float(audio_strength)
        self.audio_window_scale = float(audio_window_scale)
        self.per_segment_epsilon = [float(e) for e in per_segment_epsilon] if per_segment_epsilon else None

    def get(self, key: str, default: object = None) -> object:
        return getattr(self, key, default)


def sigma_from_eps(eps: float) -> float:
    return 1.0 / math.log(1.0 / eps) if 0.0 < eps < 1.0 else DEFAULT_SIGMA


def parse_prompts(local_prompts: str) -> list[str]:
    return [p.strip() for p in local_prompts.split("|") if p.strip()]


def parse_lengths(segment_lengths: str) -> list[int] | None:
    if not segment_lengths.strip():
        return None
    try:
        return [int(float(x)) for x in segment_lengths.split(",") if x.strip()]
    except ValueError as exc:
        raise ValueError(f"segment_lengths must be comma-separated integers: {segment_lengths!r}") from exc


def pixel_to_latent_lengths(pixel: Sequence[int], latent_frames: int, stride: int) -> list[int]:
    """Largest-remainder conversion of pixel-frame lengths to latent-frame lengths."""
    n = len(pixel)
    total = sum(pixel)
    if total <= 0:
        return [1] * n
    target = min(latent_frames, max(1, round(total / stride)))
    if abs(total - latent_frames * stride) <= stride:
        target = latent_frames
    exact = [p * target / total for p in pixel]
    res = [math.floor(e) for e in exact]
    order = sorted(range(n), key=lambda i: -(exact[i] - res[i]))
    rem = target - sum(res)
    k = 0
    while rem > 0:
        res[order[k % n]] += 1
        rem -= 1
        k += 1
    for i in range(n):
        if res[i] < 1:
            j = max(range(n), key=lambda t: res[t])
            if res[j] > 1:
                res[j] -= 1
            res[i] = 1
    return res


def distribute_lengths(latent_lengths: Sequence[int] | None, n: int, latent_frames: int,
                       warn: Callable[[str], None] | None = None) -> list[int]:
    if latent_lengths is not None and len(latent_lengths) != n:
        raise ValueError(f"segment_lengths has {len(latent_lengths)} values but there are {n} local prompts")
    req = list(latent_lengths) if latent_lengths is not None else [math.ceil(latent_frames / n)] * n
    cursor = 0
    eff: list[int] = []
    for i, L in enumerate(req):
        end = min(cursor + max(L, 0), latent_frames)
        eff.append(end - cursor)
        if L > 0 and end - cursor == 0 and warn:
            warn(f"segment {i + 1} starts past the last latent frame and will be dropped")
        cursor = end
    return eff


IdsFn = Callable[[str], list[int]]


def token_ranges(ids: IdsFn, global_prompt: str, locals_: Sequence[str], eos_adj: int, max_len: int,
                 decode: Callable[[list[int]], str] | None = None,
                 warn: Callable[[str], None] | None = None) -> tuple[list[tuple[int, int]], str]:
    """Incremental tokenisation: each local prompt owns the tokens it adds to the running string."""
    running = global_prompt
    prev = len(ids(global_prompt)) - eos_adj
    ranges: list[tuple[int, int]] = []
    for i, lp in enumerate(locals_):
        running = f"{running} {lp}"
        cur = len(ids(running)) - eos_adj
        if cur <= prev:
            raise ValueError(f"local prompt {i + 1} ({lp[:40]!r}) produced no new tokens")
        ranges.append((prev, cur))
        prev = cur
    if prev > max_len:
        if warn:
            warn(f"prompt is {prev} tokens, the encoder keeps {max_len}; later segments are truncated")
        ranges = [(s, min(e, max_len)) for s, e in ranges if s < max_len]
        if decode is not None:
            running = decode(ids(running)[:max_len])
    return ranges, running


@dataclass
class Segment:
    token_idx: torch.Tensor
    midpoint: float
    window: float
    sigma: float
    strength: float
    window_audio: float
    sigma_audio: float
    strength_audio: float


def build_segments(ranges: Sequence[tuple[int, int]], lengths: Sequence[int], eps: float,
                   options: RelayOptions | None = None, warn: Callable[[str], None] | None = None) -> list[Segment]:
    o = options or RelayOptions()
    cursor = 0
    out: list[Segment] = []
    for i, ((start, end), L) in enumerate(zip(ranges, lengths)):
        if L <= 0:
            if warn:
                warn(f"segment {i + 1} has no frames and is skipped")
            continue
        e = o.per_segment_epsilon[i] if o.per_segment_epsilon and i < len(o.per_segment_epsilon) else eps
        base_window = max(L / 2 - 2, 0.0)
        out.append(Segment(
            token_idx=torch.arange(start, end), midpoint=cursor + (L - 1) / 2,
            window=max(base_window * o.video_window_scale, 0.0), sigma=sigma_from_eps(e), strength=o.video_strength,
            window_audio=max(base_window * o.audio_window_scale, 0.0),
            sigma_audio=sigma_from_eps(o.audio_epsilon if o.audio_epsilon is not None else e),
            strength_audio=o.audio_strength))
        cursor += L
    return out


def segment_cost(frames: torch.Tensor, midpoint: float, window: float, sigma: float, strength: float) -> torch.Tensor:
    d = (frames - midpoint).abs()
    return strength * torch.relu(d - window) ** 2 / (2 * sigma ** 2)


def penalty_bias(segments: Sequence[Segment], lq: int, lk: int, latent_frames: int, video_tpf: int, video_mode: bool,
                 device: torch.device | str = "cpu", dtype: torch.dtype = torch.float32) -> torch.Tensor:
    """Additive logit bias `[Lq, Lk]` (≤ 0). Each segment's token columns get its cost per query."""
    q = torch.arange(lq, dtype=torch.float32)
    # Guide / keyframe tokens appended past the last frame map onto the last frame.
    frames = (torch.floor(q / max(video_tpf, 1)).clamp(max=max(latent_frames - 1, 0)) if video_mode
              else q * latent_frames / lq)
    offset = torch.zeros((lq, lk), dtype=torch.float32)
    for s in segments:
        if video_mode:
            cost = segment_cost(frames, s.midpoint, s.window, s.sigma, s.strength)
        else:
            cost = segment_cost(frames, s.midpoint, s.window_audio, s.sigma_audio, s.strength_audio)
        idx = s.token_idx[s.token_idx < lk]
        if idx.numel():
            offset[:, idx] = cost.clamp(max=MAX_COST)[:, None]
    return (-offset).to(device=device, dtype=dtype)


class RelayMask:
    """`(Lq, Lk, dtype, device, transformer_options) → bias | None`, cached per shape/mode."""

    def __init__(self, segments: Sequence[Segment], latent_frames: int, fallback_tpf: int,
                 text_only: bool = False) -> None:
        self.segments = list(segments)
        self.latent_frames = latent_frames
        self.fallback_tpf = fallback_tpf
        # True once text cross-attention modules are hooked: only calls inside a hook are biased.
        self.text_only = text_only
        self.max_token = max((int(s.token_idx.max()) for s in self.segments if s.token_idx.numel()), default=-1)
        self._cache: dict[tuple[int, int, bool, str, torch.dtype], torch.Tensor] = {}

    def video_tpf(self, transformer_options: Mapping[str, object]) -> int:
        gs = transformer_options.get("grid_sizes")
        if isinstance(gs, (tuple, list, torch.Tensor)) and len(gs) >= 3:
            return int(gs[1]) * int(gs[2])
        return self.fallback_tpf

    def _is_video_tokens(self, n: int, tpf: int) -> bool:
        """True for the video token count, including guide tokens appended after the frames."""
        video = self.latent_frames * tpf
        return n >= video and (n - video) % max(tpf, 1) == 0

    def __call__(self, lq: int, lk: int, dtype: torch.dtype, device: torch.device | str,
                 transformer_options: Mapping[str, object]) -> torch.Tensor | None:
        if not self.segments or lq == lk:
            return None
        cou = transformer_options.get("cond_or_uncond", [])
        if isinstance(cou, (list, tuple)) and 1 in cou and 0 not in cou:
            return None
        scope = current_text_scope()
        if scope is None and self.text_only:
            return None  # a hooked model: audio<->video cross-attention is never biased
        tpf = self.video_tpf(transformer_options)
        if scope is None:  # un-hookable model: fall back to inferring from the shapes
            if self._is_video_tokens(lk, tpf) or lk < self.max_token + 1:
                return None
            video_mode = self._is_video_tokens(lq, tpf)
        else:
            if lk < self.max_token + 1:
                return None
            video_mode = scope == "video"
        key = (lq, lk, video_mode, str(device), dtype)
        if key not in self._cache:
            self._cache[key] = penalty_bias(self.segments, lq, lk, self.latent_frames, tpf, video_mode, device, dtype)
        return self._cache[key]


def combine_mask(existing: torch.Tensor | None, bias: torch.Tensor) -> torch.Tensor:
    """Add a `[Lq, Lk]` bias to whatever mask the model already passes, as a 4-D additive mask."""
    b4 = bias.view(1, 1, *bias.shape)
    if existing is None:
        return b4
    m = existing
    if m.dtype == torch.bool:
        m = torch.zeros(m.shape, dtype=bias.dtype, device=bias.device).masked_fill(~m.to(bias.device),
                                                                                 torch.finfo(bias.dtype).min / 2)
    m = m.to(device=bias.device, dtype=bias.dtype)
    if m.ndim == 2:
        m = m.view(1, 1, *m.shape)
    elif m.ndim == 3:
        m = m.unsqueeze(1)
    return m + b4


MaskFn = Callable[[int, int, torch.dtype, torch.device, Mapping[str, object]], torch.Tensor | None]


def make_relay_override(mask_fn: MaskFn, prev: Override | None) -> Override:
    """`transformer_options["optimized_attention_override"]` hook (honoured by ComfyUI's
    `wrap_attn`): injects the bias into the attention call's `mask`, then defers to `prev`."""

    def override(func: AttnFn, *args: object, **kwargs: object) -> torch.Tensor:
        q, k = args[0], args[1]
        if isinstance(q, torch.Tensor) and isinstance(k, torch.Tensor):
            seq_dim = 2 if kwargs.get("skip_reshape", False) else 1
            topts = kwargs.get("transformer_options")
            bias = mask_fn(q.shape[seq_dim], k.shape[seq_dim], q.dtype, q.device,
                           topts if isinstance(topts, Mapping) else {})
            if bias is not None:
                if len(args) > 4:
                    existing = args[4]
                    args = args[:4] + (combine_mask(existing if isinstance(existing, torch.Tensor) else None, bias),) + args[5:]
                else:
                    existing_kw = kwargs.get("mask")
                    kwargs["mask"] = combine_mask(existing_kw if isinstance(existing_kw, torch.Tensor) else None, bias)
        if prev is not None:
            return prev(func, *args, **kwargs)
        return func(*args, **kwargs)

    return override


def attention_mask_arg(args: Sequence[object], kwargs: Mapping[str, object]) -> torch.Tensor | None:
    existing = args[4] if len(args) > 4 else kwargs.get("mask")
    return existing if isinstance(existing, torch.Tensor) else None


def make_backend_override(backend: AttnFn, prev: Override | None, *, supports_mask: bool = True,
                          on_masked: Callable[[], None] | None = None) -> Override:
    """Swap the attention implementation, keeping any earlier override (e.g. a relay bias) in the chain.

    A backend that cannot take a mask (FlashAttention) is bypassed for masked calls - the default
    attention runs instead - and `on_masked` is told, so the caller can warn once."""

    def override(func: AttnFn, *args: object, **kwargs: object) -> torch.Tensor:
        def guarded(*a: object, **kw: object) -> torch.Tensor:
            if attention_mask_arg(a, kw) is not None:
                if on_masked is not None:
                    on_masked()
                return func(*a, **kw)
            return backend(*a, **kw)

        chosen: AttnFn = backend if supports_mask else guarded
        if prev is not None:
            return prev(chosen, *args, **kwargs)
        return chosen(*args, **kwargs)

    return override


def install_override(model_options: dict[str, object], make: Callable[[Override | None], Override]) -> None:
    topts = model_options.get("transformer_options")
    topts = dict(topts) if isinstance(topts, dict) else {}
    prev = topts.get("optimized_attention_override")
    topts["optimized_attention_override"] = make(prev if callable(prev) else None)
    model_options["transformer_options"] = topts


def parse_timeline(raw: str | None) -> tuple[list[str], list[int]] | None:
    """Prompts and pixel-frame lengths from the Timeline editor's `timeline_data` JSON, or None
    when it is blank / not a segment list (callers then use the plain text widgets).

    `|` inside a prompt is replaced by a space so it cannot split a segment. An empty prompt
    raises: it would be dropped and shift every later segment."""
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    segs = data.get("segments") if isinstance(data, dict) else None
    if not isinstance(segs, list) or not segs:
        return None
    prompts: list[str] = []
    lengths: list[int] = []
    empty: list[int] = []
    for i, seg in enumerate(segs, start=1):
        if not isinstance(seg, dict):
            return None
        text = seg.get("prompt")
        prompt = " ".join(str(text).replace("|", " ").split()) if isinstance(text, str) else ""
        length = seg.get("length")
        if not prompt:
            empty.append(i)
        prompts.append(prompt)
        lengths.append(max(1, int(round(float(length)))) if isinstance(length, (int, float)) and
                       not isinstance(length, bool) and math.isfinite(float(length)) else 1)
    if empty:
        raise ValueError(f"Prompt Relay Timeline: segment(s) {', '.join(map(str, empty))} have no prompt; "
                         "write a prompt for every segment or delete the empty ones")
    return prompts, lengths
