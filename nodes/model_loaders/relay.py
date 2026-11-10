"""Prompt Relay nodes: per-segment temporal prompts for LTX-style video models.

The penalty is applied through `transformer_options["optimized_attention_override"]`, which
ComfyUI's `wrap_attn` decorator consults on every `optimized_attention(_masked)` call, so the
bias really reaches the softmax (the LTX cross-attention never reads attn2 patches)."""
from __future__ import annotations

from dataclasses import dataclass

import torch

from comfy_api.latest import io

from ._comfy import log
from .relay_logic import (
    RelayMask,
    RelayOptions,
    build_segments,
    distribute_lengths,
    install_override,
    install_text_scope_hooks,
    make_relay_override,
    parse_lengths,
    parse_prompts,
    parse_timeline,
    pixel_to_latent_lengths,
    token_ranges,
)

RELAY_OPTIONS = "RELAY_OPTIONS"
TOKENIZER_ATTRS = ("t5xxl", "clip_t5xxl", "gemma3_12b", "clip_l", "clip_g", "llama", "clip_h")
UNLIMITED = 1_000_000


@dataclass
class ArchInfo:
    arch: str
    patch: tuple[int, int, int]  # (t, h, w) in latent space
    temporal_stride: int


def detect_arch(diffusion_model: object) -> ArchInfo:
    name = type(diffusion_model).__name__.upper()
    arch = "ltxav" if "LTXAV" in name else "ltx2" if "LTX2" in name else (
        "ltx" if "LTXVIDEO" in name or "LTXV" in name else "")
    if arch:
        # LTX patchifies the *latent* with patch 1 (SymmetricPatchifier(1)); the 32x32 is the VAE's.
        patchifier = getattr(diffusion_model, "patchifier", None)
        ps = getattr(patchifier, "patch_size", (1, 1, 1))
        patch = tuple(int(v) for v in ps) if isinstance(ps, (tuple, list)) and len(ps) == 3 else (1, 1, 1)
        return ArchInfo(arch, (patch[0], patch[1], patch[2]), 8)
    ps = getattr(diffusion_model, "patch_size", None)
    if isinstance(ps, int):
        return ArchInfo("generic", (1, ps, ps), int(getattr(diffusion_model, "temporal_stride", 8)))
    if isinstance(ps, (tuple, list)) and len(ps) in (2, 3):
        p = tuple(int(v) for v in ps)
        p3 = (1, p[0], p[1]) if len(p) == 2 else (p[0], p[1], p[2])
        return ArchInfo("generic", p3, int(getattr(diffusion_model, "temporal_stride", 8)))
    raise ValueError(f"Prompt Relay does not know how to patchify {type(diffusion_model).__name__}; "
                     "it supports LTX-Video / LTX-2 / LTX-AV and models exposing `patch_size`.")


def _latent_tensor(latent: dict[str, object]) -> torch.Tensor:
    s = latent.get("samples")
    tensors = getattr(s, "tensors", None)
    if isinstance(tensors, list) and tensors:
        s = tensors[0]  # nested audio/video latent: video first
    if not isinstance(s, torch.Tensor) or s.ndim != 5:
        raise ValueError("Prompt Relay needs a video latent shaped [B, C, T, H, W] (e.g. an empty LTX video latent)")
    return s


class _RawTokenizer:
    def __init__(self, clip: object) -> None:
        tok = getattr(clip, "tokenizer", None)
        sub = next((getattr(tok, a) for a in TOKENIZER_ATTRS if hasattr(getattr(tok, a, None), "tokenizer")), None)
        if sub is None:
            sub = next((getattr(tok, a) for a in dir(tok) if not a.startswith("_")
                        and hasattr(getattr(tok, a, None), "tokenizer")), None)
        if sub is None:
            raise ValueError(f"Could not find a text tokenizer on this CLIP; attributes: "
                             f"{[a for a in dir(tok) if not a.startswith('_')]}")
        self.sd_tokenizer = sub
        self.raw = getattr(sub, "tokenizer")

    def ids(self, text: str) -> list[int]:
        return [int(i) for i in self.raw(text)["input_ids"]]

    def decode(self, ids: list[int]) -> str:
        return str(self.raw.decode(ids, skip_special_tokens=True))

    def eos_adj(self) -> int:
        if getattr(self.raw, "add_eos", False):
            return 1
        eos = getattr(self.raw, "eos_token_id", None)
        probe = self.ids("x")
        return 1 if eos is not None and probe and probe[-1] == eos else 0

    def max_len(self) -> int:
        for v in (getattr(self.sd_tokenizer, "max_length", None), getattr(self.raw, "model_max_length", None)):
            if isinstance(v, int) and 0 < v < UNLIMITED:
                return v
        return UNLIMITED


def relay_encode(model: object, clip: object, latent: dict[str, object], global_prompt: str | None,
                 local_prompts: str | None, segment_lengths: str | None, epsilon: float,
                 relay_options: RelayOptions | None = None, max_frames: int | None = None) -> tuple[object, list[list[object]]]:
    for field_name, v in (("global_prompt", global_prompt), ("local_prompts", local_prompts),
                          ("segment_lengths", segment_lengths)):
        if v is None:
            raise ValueError(f"Prompt Relay: `{field_name}` is None - the input is probably linked to a node "
                             "that returned nothing, or the workflow predates this widget.")
    assert global_prompt is not None and local_prompts is not None and segment_lengths is not None
    locals_ = parse_prompts(local_prompts)
    if not locals_:
        raise ValueError("Prompt Relay needs at least one local prompt (separate segments with |)")

    dm = model.model.diffusion_model  # type: ignore[attr-defined]
    info = detect_arch(dm)
    lat = _latent_tensor(latent)
    latent_frames = int(lat.shape[2])
    fallback_tpf = (int(lat.shape[3]) // info.patch[1]) * (int(lat.shape[4]) // info.patch[2])
    if max_frames is not None:
        expect = (latent_frames - 1) * info.temporal_stride + 1
        if max_frames != expect:
            log.info("Prompt Relay: timeline max_frames=%d but the latent covers %d frames", max_frames, expect)

    pixel = parse_lengths(segment_lengths)
    if pixel is not None and len(pixel) != len(locals_):
        raise ValueError(f"segment_lengths has {len(pixel)} values but there are {len(locals_)} local prompts")
    latent_lengths = pixel_to_latent_lengths(pixel, latent_frames, info.temporal_stride) if pixel else None
    lengths = distribute_lengths(latent_lengths, len(locals_), latent_frames, log.warning)

    tk = _RawTokenizer(clip)
    eos_adj = tk.eos_adj()
    ranges, full_prompt = token_ranges(tk.ids, global_prompt, locals_, eos_adj, tk.max_len() - eos_adj,
                                       tk.decode, log.warning)
    cond = clip.encode_from_tokens_scheduled(clip.tokenize(full_prompt))  # type: ignore[attr-defined]

    segments = build_segments(ranges, lengths, float(epsilon), relay_options, log.warning)
    mask = RelayMask(segments, latent_frames, fallback_tpf)
    patched = model.clone()  # type: ignore[attr-defined]
    hooked = install_text_scope_hooks(patched, dm) if isinstance(dm, torch.nn.Module) else 0
    mask.text_only = hooked > 0
    install_override(patched.model_options, lambda prev: make_relay_override(mask, prev))
    log.info("Prompt Relay (%s): %d segments over %d latent frames, lengths %s, token ranges %s",
             info.arch, len(segments), latent_frames, lengths, ranges)
    return patched, cond


class JWTFPromptRelayEncode(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFPromptRelayEncode",
            display_name='Prompt Relay Encode',
            category='JezzWTF/video',
            description="Global prompt plus time-segmented local prompts; each segment's text dominates its own frames.",
            inputs=[
                io.Model.Input("model", tooltip="Diffusion model to patch for time-segmented attention."),
                io.Clip.Input("clip", tooltip="Text encoder used to tokenize and encode the combined prompts."),
                io.Latent.Input("latent", tooltip='Empty video latent; its shape sets the frame count.'),
                io.String.Input("global_prompt", default='', multiline=True, tooltip="Prompt applied across all frames alongside the segment prompts."),
                io.String.Input("local_prompts", default='', multiline=True, tooltip='Segments separated by |'),
                io.String.Input("segment_lengths", default='', tooltip='Comma-separated pixel-frame lengths; blank = equal'),
                io.Float.Input("epsilon", default=0.001, min=1e-06, max=0.99, step=0.0001, tooltip="Controls how quickly a segment's influence falls off outside its time window, with smaller values reducing spillover."),
                io.Custom("RELAY_OPTIONS").Input("relay_options", optional=True, tooltip="Optional settings for attention strength and time windows in the video and audio streams."),
            ],
            outputs=[
                io.Model.Output("model", tooltip="Model patched so segment tokens have less influence outside their assigned time windows."),
                io.Conditioning.Output("positive", tooltip="Positive conditioning encoded from the global and segment prompts."),
            ],
        )

    @classmethod
    def execute(cls, model: object, clip: object, latent: dict[str, object], global_prompt: str, local_prompts: str,
               segment_lengths: str, epsilon: float, relay_options: RelayOptions | None = None
               ) -> io.NodeOutput:
        return io.NodeOutput(*relay_encode(model, clip, latent, global_prompt, local_prompts, segment_lengths, epsilon, relay_options))


class JWTFPromptRelayTimeline(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFPromptRelayTimeline",
            display_name='Prompt Relay Timeline',
            category='JezzWTF/video',
            description='Prompt Relay with a drag-and-drop timeline editor for the segments.',
            inputs=[
                io.Model.Input("model", tooltip="Diffusion model to patch for time-segmented attention."),
                io.Clip.Input("clip", tooltip="Text encoder used to tokenize and encode the combined prompts."),
                io.Latent.Input("latent", tooltip='Empty video latent; its shape sets the frame count.'),
                io.String.Input("global_prompt", default='', multiline=True, tooltip="Prompt applied across all frames alongside the segment prompts."),
                io.Int.Input("max_frames", default=129, min=1, max=10000, tooltip="Timeline length in video frames for the editor, compared against the latent's frame count during encoding."),
                io.String.Input("timeline_data", default='', tooltip="JSON of segment prompts and frame lengths written by the timeline editor, taking precedence over the separate text fields when valid."),
                io.String.Input("local_prompts", default='', multiline=True, tooltip="Pipe-separated segment prompts maintained by the editor and used as a fallback when timeline JSON is unavailable."),
                io.String.Input("segment_lengths", default='', tooltip="Comma-separated segment lengths in video frames maintained by the editor, with blank dividing the latent into equal parts."),
                io.Float.Input("epsilon", default=0.001, min=1e-06, max=0.99, step=0.0001, tooltip="Controls how quickly a segment's influence falls off outside its time window, with smaller values reducing spillover."),
                io.Float.Input("fps", default=24.0, min=0.1, max=240.0, step=0.1, optional=True, tooltip="Playback rate in frames per second used by the editor to convert frame positions to displayed seconds."),
                io.Combo.Input("time_units", options=['frames', 'seconds'], default='frames', optional=True, tooltip="Displays timeline positions in frames or seconds while retaining frame-based segment lengths."),
                io.Custom("RELAY_OPTIONS").Input("relay_options", optional=True, tooltip="Optional settings for attention strength and time windows in the video and audio streams."),
            ],
            outputs=[
                io.Model.Output("model", tooltip="Model patched so segment tokens have less influence outside their assigned time windows."),
                io.Conditioning.Output("positive", tooltip="Positive conditioning encoded from the global and segment prompts."),
            ],
        )

    @classmethod
    def execute(cls, model: object, clip: object, latent: dict[str, object], global_prompt: str, max_frames: int,
               timeline_data: str, local_prompts: str, segment_lengths: str, epsilon: float, fps: float = 24.0,
               time_units: str = "frames", relay_options: RelayOptions | None = None
               ) -> io.NodeOutput:
        parsed = parse_timeline(timeline_data)  # the editor's JSON is the source of truth when present
        if parsed is not None:
            local_prompts = " | ".join(parsed[0])
            segment_lengths = ", ".join(str(n) for n in parsed[1])
        return io.NodeOutput(*relay_encode(model, clip, latent, global_prompt, local_prompts, segment_lengths, epsilon,
                                           relay_options, max_frames=int(max_frames)))


class JWTFPromptRelayOptions(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFPromptRelayOptions",
            display_name='Prompt Relay Options',
            category='JezzWTF/video',
            description='Experimental strength / window controls for Prompt Relay (video and audio streams).',
            inputs=[
                io.Float.Input("video_strength", default=1.0, min=0.0, max=10.0, step=0.05, tooltip="Multiplier for the out-of-window attention penalty in the video stream, with 0 disabling it."),
                io.Float.Input("video_window_scale", default=1.0, min=0.0, max=4.0, step=0.05, tooltip="Scales the video window around each segment midpoint in which no attention penalty is applied."),
                io.Float.Input("audio_epsilon", default=0.0, min=0.0, max=0.99, step=0.0001, tooltip="Sets the falloff for audio attention outside each segment's window, with 0 inheriting the video setting."),
                io.Float.Input("audio_strength", default=1.0, min=0.0, max=10.0, step=0.05, tooltip="Multiplier for the out-of-window attention penalty in the audio stream, with 0 disabling it."),
                io.Float.Input("audio_window_scale", default=1.0, min=0.0, max=4.0, step=0.05, tooltip="Scales the audio window around each segment midpoint in which no attention penalty is applied."),
            ],
            outputs=[
                io.Custom("RELAY_OPTIONS").Output("relay_options", tooltip="Video and audio attention settings to connect to Prompt Relay Encode or Timeline."),
            ],
        )

    @classmethod
    def execute(cls, video_strength: float, video_window_scale: float, audio_epsilon: float, audio_strength: float,
              audio_window_scale: float) -> io.NodeOutput:
        return io.NodeOutput(RelayOptions(video_strength=video_strength, video_window_scale=video_window_scale,
                             audio_epsilon=None if audio_epsilon <= 0 else audio_epsilon,
                             audio_strength=audio_strength, audio_window_scale=audio_window_scale))


NODES = [JWTFPromptRelayEncode, JWTFPromptRelayTimeline, JWTFPromptRelayOptions]
