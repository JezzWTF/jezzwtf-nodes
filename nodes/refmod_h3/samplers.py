"""Samplers with live preview: Ultimate KSampler and the CFG-free H3 KSampler (spec section 12).

Both are output nodes sharing execution, the preview wrapper (``preview.py``) and one frontend. They return
``(latent, denoised, image, audio)`` and ``ui.jezzwtf_source_id`` so a panel can follow the node.
"""
from __future__ import annotations

import copy
import logging
import sys

import torch

from comfy_api.latest import io

from . import _comfy
from ._types import RefModError
from .preview import attach_preview

log = logging.getLogger("jezzwtf.refmod_h3")

PHASE_EVENT = "jezzwtf.uk_phase"
SOURCE_KEY = "jezzwtf_source_id"
CLOWN_PREFIX = "clown: "
PLACEHOLDER_SCHEDULER = "beta"
SAMPLER_MODES = ("standard", "unsample", "resample")
GUIDER_MODEL_ATTRS = ("model_patcher", "model", "patcher", "_model_patcher")
INT64 = 2 ** 64 - 1

Latent = dict[str, torch.Tensor]


# --------------------------------------------------------------------------- RES4LYF (soft dependency)

def _usable(obj: object) -> bool:
    return callable(obj) and not (isinstance(obj, type) and obj.__module__.startswith("torch."))


def _find_in_modules(attr: str, module_hint: str) -> object | None:
    """Look for ``attr`` in already-imported modules whose name contains ``module_hint``."""
    for name, mod in list(sys.modules.items()):
        if mod is None or name.startswith(("torch.ops", "torch._classes")) or module_hint not in name:
            continue
        try:
            obj = getattr(mod, attr, None)
        except Exception:
            continue
        if obj is not None and _usable(obj):
            return obj
    return None


def res4lyf_sampler_class() -> type | None:
    obj = _find_in_modules("ClownsharKSampler_Beta", "samplers")
    return obj if isinstance(obj, type) else None


def res4lyf_sampler_names() -> list[str]:
    fn = _find_in_modules("get_sampler_name_list", "rk_coefficients")
    if fn is None:
        return []
    try:
        return [str(n) for n in fn()]  # type: ignore[operator]
    except Exception:
        return []


def res4lyf_scheduler_names() -> list[str]:
    fn = _find_in_modules("get_res4lyf_scheduler_list", "helper")
    if fn is None:
        return []
    try:
        return [str(n) for n in fn()]  # type: ignore[operator]
    except Exception:
        return []


# --------------------------------------------------------------------------- combos

def base_samplers() -> list[str]:
    mod = _comfy.optional_module("comfy.samplers")
    return list(mod.SAMPLER_NAMES) if mod is not None and hasattr(mod, "SAMPLER_NAMES") else ["euler"]


def base_schedulers() -> list[str]:
    mod = _comfy.optional_module("comfy.samplers")
    return list(mod.SCHEDULER_NAMES) if mod is not None and hasattr(mod, "SCHEDULER_NAMES") else ["simple", "beta"]


def sampler_choices() -> list[str]:
    return base_samplers() + [CLOWN_PREFIX + n for n in res4lyf_sampler_names()]


def tiny_vae_choices() -> list[str]:
    return ["none"] + sorted(set(n for n in _comfy.filename_list("vae_approx") if n and n != "none"), key=str.casefold)


def scheduler_choices(include_res4lyf: bool = True) -> list[str]:
    names = base_schedulers()
    extra = [n for n in res4lyf_scheduler_names() if n not in names] if include_res4lyf else []
    return ["none"] + names + extra


def default_scheduler(choices: list[str]) -> str:
    return PLACEHOLDER_SCHEDULER if PLACEHOLDER_SCHEDULER in choices else choices[-1]


def real_scheduler(name: str) -> str:
    """RES4LYF-only scheduler names (and ``none``) are not known to core; use the placeholder."""
    return name if name in base_schedulers() else PLACEHOLDER_SCHEDULER


# --------------------------------------------------------------------------- sigmas

def trim_sigmas(sigmas: torch.Tensor, steps_to_run: int) -> torch.Tensor:
    """Chainsampling: N >= 1 and N < total keeps ``sigmas[:N+1]``; -1 or N >= total keeps all."""
    total = int(sigmas.shape[-1]) - 1
    if 1 <= steps_to_run < total:
        return sigmas[: steps_to_run + 1]
    return sigmas


def widget_sigmas(model: object, scheduler: str, steps: int, denoise: float) -> torch.Tensor:
    samplers = _comfy.optional_module("comfy.samplers")
    if samplers is None:
        raise RefModError("comfy.samplers is unavailable")
    if denoise <= 0.0:
        return torch.FloatTensor([])  # core KSampler: nothing to sample, the latent passes through
    ms = model.get_model_object("model_sampling")  # type: ignore[attr-defined]
    if denoise >= 0.9999:
        return samplers.calculate_sigmas(ms, scheduler, int(steps))
    total = max(1, int(steps / max(denoise, 1e-6)))
    return samplers.calculate_sigmas(ms, scheduler, total)[-(int(steps) + 1):]


# --------------------------------------------------------------------------- events

def node_ids(unique_id: object, dynprompt: object) -> tuple[str, str]:
    raw = str(unique_id)
    getter = getattr(dynprompt, "get_display_node_id", None)
    if callable(getter):
        try:
            return str(getter(unique_id)), raw
        except Exception:
            pass
    return raw, raw


def emit_phase(unique_id: object, dynprompt: object, phase: str) -> None:
    node, raw = node_ids(unique_id, dynprompt)
    _comfy.send_sync(PHASE_EVENT, {"node": node, "node_raw": raw, "phase": phase})


# --------------------------------------------------------------------------- decode

def silent_audio() -> dict[str, object]:
    return {"waveform": torch.zeros(1, 1, 1), "sample_rate": 44100}


def placeholder_image() -> torch.Tensor:
    return torch.zeros(1, 64, 64, 3)


def decode_latent(latent: Latent, vae: object | None, audio_vae: object | None, tiled: bool
                  ) -> tuple[torch.Tensor, dict[str, object]]:
    """VAE-decode (video part of nested latents) and optionally the audio part."""
    nodes = _comfy.comfy_nodes()
    if vae is None or nodes is None:
        log.warning("sampler: decode is on but no VAE is connected; returning the latent only")
        return placeholder_image(), silent_audio()
    samples = latent["samples"]
    nested = bool(getattr(samples, "is_nested", False))
    video = samples.unbind()[0] if nested else samples
    sub: Latent = {"samples": video}
    if tiled:
        image = nodes.VAEDecodeTiled().decode(vae, sub, 512, 64, 64, 8)[0]
    else:
        image = nodes.VAEDecode().decode(vae, sub)[0]
    audio = silent_audio()
    if nested and len(samples.unbind()) > 1 and audio_vae is not None:
        try:
            audio = decode_audio_latent(latent, audio_vae)
        except Exception as exc:
            log.warning("sampler: audio decode failed (%s); returning silent audio", exc)
            audio = silent_audio()
    return image, audio


def decode_audio_latent(latent: Latent, audio_vae: object) -> dict[str, object]:
    """Decode the audio stream (last part) of a nested AV latent.

    ComfyUI 0.44 ships ``comfy_extras.nodes_audio.vae_decode_audio``, which the stock ``VAEDecodeAudio``
    node uses: it reads the VAE's own sample rate (H3: 32 kHz) and level-normalises the result. Older
    builds fall back to the LTX audio decoder.
    """
    nodes_audio = _comfy.optional_module("comfy_extras.nodes_audio")
    core_decode = getattr(nodes_audio, "vae_decode_audio", None) if nodes_audio is not None else None
    if callable(core_decode):
        return core_decode(audio_vae, latent)  # type: ignore[no-any-return]
    lt = _comfy.optional_module("comfy_extras.nodes_lt_audio")
    decoder = getattr(lt, "LTXVAudioVAEDecode")
    return _comfy.call_node(decoder, samples=latent, audio_vae=audio_vae)[0]  # type: ignore[return-value]


def finish(latent: Latent, denoised: Latent | None, do_decode: bool, vae: object | None,
           audio_vae: object | None, tiled: bool, unique_id: object, dynprompt: object
           ) -> io.NodeOutput:
    image, audio = placeholder_image(), silent_audio()
    if do_decode:
        emit_phase(unique_id, dynprompt, "decoding")
        image, audio = decode_latent(latent, vae, audio_vae, tiled)
    emit_phase(unique_id, dynprompt, "done")
    node, _ = node_ids(unique_id, dynprompt)
    return io.NodeOutput(latent, denoised if denoised is not None else latent, image, audio,
                         ui={SOURCE_KEY: [node]})


# --------------------------------------------------------------------------- shared inputs

def _maybe_preview(model: object, preview: bool, max_res: int, quality: int, frames: int, fps: int,
                   tiny: str, vae: object | None, audio_vae: object | None, unique_id: object,
                   dynprompt: object) -> object:
    if not preview:
        return model
    node, _ = node_ids(unique_id, dynprompt)
    return attach_preview(model, max_res, node, quality, frames, fps, vae, tiny, audio_vae)


def _latent_pair(outputs: tuple[object, ...]) -> tuple[Latent, Latent | None]:
    if not outputs or not isinstance(outputs[0], dict):
        raise RefModError("the sampler returned no latent")
    first: Latent = outputs[0]  # type: ignore[assignment]
    second = outputs[1] if len(outputs) > 1 and isinstance(outputs[1], dict) else None
    return first, second  # type: ignore[return-value]


def _custom_core() -> object:
    mod = _comfy.optional_module("comfy_extras.nodes_custom_sampler")
    if mod is None:
        raise RefModError("this ComfyUI has no comfy_extras.nodes_custom_sampler")
    return mod


def run_custom_advanced(noise: object, guider: object, sampler: object, sigmas: torch.Tensor,
                        latent: Latent) -> tuple[Latent, Latent | None]:
    core = _custom_core()
    out = _comfy.call_node(getattr(core, "SamplerCustomAdvanced"), noise=noise, guider=guider,
                           sampler=sampler, sigmas=sigmas, latent_image=latent)
    return _latent_pair(out)


def guider_model_slot(guider: object | None) -> tuple[str | None, object | None]:
    """Return the patcher's actual attribute so preview rebinding updates the right field."""
    if guider is not None:
        for attr in GUIDER_MODEL_ATTRS:
            candidate = getattr(guider, attr, None)
            if candidate is not None and hasattr(candidate, "clone") and hasattr(candidate, "add_wrapper_with_key"):
                return attr, candidate
    return None, None


def run_sampler(*, model: object | None, positive: object | None, latent_image: Latent | None,
                sampler_name: str, scheduler: str, steps: int, steps_to_run: int, cfg: float,
                cfg_enabled: bool, denoise: float, seed: int, decode: bool, tiled_decode: bool,
                preview_fps: int, unique_id: object, dynprompt: object, negative: object | None = None,
                noise: object | None = None, guider: object | None = None, sampler: object | None = None,
                sigmas: torch.Tensor | None = None, vae: object | None = None, audio_vae: object | None = None,
                eta: float = 0.5, sampler_mode: str = "standard", bongmath: bool = True, options: object | None = None,
                preview: bool = True, preview_max_res: int = 1024, preview_frames: int = 1,
                preview_jpeg_quality: int = 80, preview_tiny_vae: str = "none", allow_clown: bool = True) -> io.NodeOutput:
    """Shared execution for Ultimate and the stable H3 preset. Wired inputs own sampling."""
    emit_phase(unique_id, dynprompt, "sampling")
    if latent_image is None:
        raise RefModError("connect a latent_image")
    is_clown = sampler_name.startswith(CLOWN_PREFIX)
    if is_clown and not allow_clown:
        raise RefModError("H3 KSampler uses built-in samplers; use Ultimate KSampler for RES4LYF")
    if is_clown and any(value is not None for value in (noise, guider, sampler)):
        raise RefModError("RES4LYF cannot use external noise, guider or sampler inputs; disconnect them or select a built-in sampler")
    attr, guided = guider_model_slot(guider)
    base = guided if guider is not None else model
    sigma_model = model if model is not None else guided
    if guider is None:
        if model is None:
            raise RefModError("connect a model or a guider")
        if positive is None:
            raise RefModError("connect a guider or a positive conditioning")
    elif sigma_model is None and sigmas is None:
        raise RefModError("a guider without a model needs sigmas (the schedule cannot be computed)")
    if scheduler == "none" and sigmas is None:
        raise RefModError("scheduler is 'none' but no sigmas are connected")
    if not is_clown and sigmas is None and denoise <= 0:
        return finish(latent_image, latent_image, decode, vae, audio_vae, tiled_decode, unique_id, dynprompt)
    if guider is not None and base is None:
        if preview:
            log.warning("sampler: no guider model to attach the preview to; running without preview")
        preview = False
    work_model = base
    if base is not None:
        work_model = _maybe_preview(base, preview, preview_max_res, preview_jpeg_quality, preview_frames,
                                    preview_fps, preview_tiny_vae, vae, audio_vae, unique_id, dynprompt)
    run_guider = guider
    if guider is not None and attr is not None and work_model is not base:
        try:
            run_guider = copy.copy(guider)
            setattr(run_guider, attr, work_model)
        except Exception as exc:
            log.warning("sampler: could not attach the preview to the guider (%s)", exc)
            run_guider = guider
    use_cfg = bool(cfg_enabled) and negative is not None
    if negative is None:
        negative = positive
    if is_clown:
        clown = res4lyf_sampler_class()
        if clown is None:
            raise RefModError("a 'clown:' sampler needs the RES4LYF node pack, which is not loaded")
        outputs = _comfy.call_node(
            clown, model=work_model, positive=positive, negative=negative, latent_image=latent_image,
            sampler_name=sampler_name[len(CLOWN_PREFIX):],
            scheduler=PLACEHOLDER_SCHEDULER if scheduler == "none" else scheduler, steps=int(steps),
            steps_to_run=int(steps_to_run), denoise=float(denoise), cfg=float(cfg) if use_cfg else 1.0,
            seed=int(seed), eta=float(eta), sampler_mode=sampler_mode, bongmath=bool(bongmath), sigmas=sigmas,
            options_group={"options0": options} if options is not None else None)
        latent, denoised = _latent_pair(outputs)
    elif any(value is not None for value in (noise, guider, sampler, sigmas)) or not use_cfg or steps_to_run >= 1:
        core = _custom_core()
        if noise is None:
            noise = _comfy.call_node(getattr(core, "RandomNoise"), noise_seed=int(seed))[0]
        if run_guider is None:
            if use_cfg:
                run_guider = _comfy.call_node(getattr(core, "CFGGuider"), model=work_model, positive=positive,
                                              negative=negative, cfg=float(cfg))[0]
            else:
                run_guider = _comfy.call_node(getattr(core, "BasicGuider"), model=work_model, conditioning=positive)[0]
        if sampler is None:
            sampler = _comfy.call_node(getattr(core, "KSamplerSelect"), sampler_name=sampler_name)[0]
        if sigmas is None:
            sigmas = widget_sigmas(sigma_model, real_scheduler(scheduler), int(steps), float(denoise))
        latent, denoised = run_custom_advanced(noise, run_guider, sampler, trim_sigmas(sigmas, int(steps_to_run)), latent_image)
    else:
        nodes = _comfy.comfy_nodes()
        if nodes is None:
            raise RefModError("ComfyUI's nodes module is unavailable")
        outputs = nodes.common_ksampler(work_model, int(seed), int(steps), float(cfg), sampler_name,
                                        real_scheduler(scheduler), positive, negative, latent_image, denoise=float(denoise))
        latent, denoised = _latent_pair(tuple(outputs))
    return finish(latent, denoised, bool(decode), vae, audio_vae, bool(tiled_decode), unique_id, dynprompt)


# --------------------------------------------------------------------------- Ultimate KSampler

class JWTFUltimateKSampler(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFUltimateKSampler",
            display_name='Ultimate KSampler',
            category='JezzWTF/sampling',
            description='Sampler with optional guider/noise/sampler/sigmas overrides, live preview, partial step runs, RES4LYF and optional decode. Disable CFG for positive-only sampling; CFG=0 keeps its numeric meaning.',
            inputs=[
                io.Model.Input("model", optional=True, tooltip="Required without a guider. With a guider, an explicitly connected model supplies the widget-generated sigma schedule."),
                io.Conditioning.Input("positive", optional=True, tooltip="Required without a guider. A wired guider carries its own conditioning."),
                io.Latent.Input("latent_image", tooltip="Starting image, video or audio-video latent to denoise."),
                io.Combo.Input("sampler_name", options=sampler_choices(), default='euler', tooltip="Sampling algorithm, with clown-prefixed choices delegated to RES4LYF when installed."),
                io.Combo.Input("scheduler", options=scheduler_choices(), default='beta', tooltip="Noise schedule used when no custom sigmas are connected."),
                io.Int.Input("steps", default=30, min=1, max=10000, tooltip="Number of steps used to build the noise schedule."),
                io.Int.Input("steps_to_run", default=-1, min=-1, max=10000, tooltip="Limits how many initial schedule steps run, with -1 running the full schedule."),
                io.Float.Input("cfg", default=5.5, min=-100.0, max=100.0, step=0.01, round=False, tooltip="Classifier-free guidance scale used when guidance and negative conditioning are both available."),
                io.Boolean.Input("cfg_enabled", default=True, tooltip="Enables classifier-free guidance when negative conditioning is connected."),
                io.Float.Input("denoise", default=1.0, min=0.0, max=1.0, step=0.01, tooltip="Fraction of the generated schedule used for denoising."),
                io.Int.Input("seed", default=0, min=0, max=18446744073709551615, tooltip="Seed used to generate sampling noise."),
                io.Float.Input("eta", default=0.5, min=-100.0, max=100.0, step=0.01, tooltip="Noise parameter passed to the RES4LYF sampler for clown-prefixed algorithms."),
                io.Combo.Input("sampler_mode", options=list(SAMPLER_MODES), default='standard', tooltip="Sampling mode forwarded to the RES4LYF sampler for clown-prefixed algorithms."),
                io.Boolean.Input("bongmath", default=True, tooltip="Enables the bongmath option on the RES4LYF sampler for clown-prefixed algorithms."),
                io.Boolean.Input("decode", default=True, tooltip="Decodes the sampled result through the connected VAEs when enabled."),
                io.Boolean.Input("tiled_decode", default=False, tooltip="Uses tiled decoding for the visual VAE when supported."),
                io.Int.Input("preview_fps", default=12, min=1, max=60, tooltip="Playback speed in frames per second for animated sampling previews."),
                io.Conditioning.Input("negative", optional=True, tooltip="Negative conditioning required to use classifier-free guidance."),
                io.Vae.Input("vae", optional=True, tooltip="Optional VAE for visual decoding and sampling previews."),
                io.Vae.Input("audio_vae", optional=True, tooltip="Optional audio VAE for decoding the audio stream of an audio-video latent."),
                io.Sigmas.Input("sigmas", optional=True, tooltip="Optional explicit noise schedule, required when the scheduler is None."),
                io.Custom("OPTIONS").Input("options", optional=True, tooltip="Optional RES4LYF options forwarded to the sampler for clown-prefixed algorithms."),
                io.Boolean.Input("preview", default=True, optional=True, tooltip="Enables intermediate image or video previews during sampling."),
                io.Int.Input("preview_max_res", default=1024, min=0, max=8192, step=8, optional=True, tooltip="Maximum preview edge in pixels, with 0 disabling the resolution limit."),
                io.Int.Input("preview_frames", default=1, min=1, max=1024, optional=True, tooltip="Maximum number of frames in each preview update, with 1 showing a still image."),
                io.Int.Input("preview_jpeg_quality", default=80, min=30, max=100, optional=True, tooltip="JPEG compression quality for live preview frames on a scale from 30 to 100."),
                io.Combo.Input("preview_tiny_vae", options=tiny_vae_choices(), default='none', optional=True, tooltip="Installed decoder from models/vae_approx; none uses the normal preview fallback. Match the decoder to the model family."),
                io.Noise.Input("noise", optional=True, tooltip="Built-in samplers: overrides the seed widget. Not supported by RES4LYF clown samplers."),
                io.Guider.Input("guider", optional=True, tooltip="Built-in samplers: carries model and conditioning, overriding positive, negative and CFG widgets. Not supported by RES4LYF."),
                io.Sampler.Input("sampler", optional=True, tooltip="Built-in samplers: overrides the sampler picker. Not supported by RES4LYF."),
            ],
            outputs=[
                io.Latent.Output("latent", tooltip="Sampled latent at the end of the executed schedule."),
                io.Latent.Output("denoised", tooltip="Denoised latent when the sampler provides one, otherwise the sampled latent."),
                io.Image.Output("image", tooltip="Decoded image or frame batch, with a placeholder when visual decoding is unavailable or disabled."),
                io.Audio.Output("audio", tooltip="Decoded audio stream, with silence when audio decoding is unavailable or disabled."),
            ],
            hidden=[io.Hidden.unique_id, io.Hidden.dynprompt],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, model: object | None = None, positive: object | None = None, latent_image: Latent | None = None,
               sampler_name: str = "euler", scheduler: str = "beta", steps: int = 30, steps_to_run: int = -1,
               cfg: float = 5.5, cfg_enabled: bool = True, denoise: float = 1.0, seed: int = 0,
               eta: float = 0.5, sampler_mode: str = "standard", bongmath: bool = True, decode: bool = True,
               tiled_decode: bool = False, preview_fps: int = 12, negative: object | None = None, vae: object | None = None,
               audio_vae: object | None = None, sigmas: torch.Tensor | None = None,
               options: object | None = None, preview: bool = True, preview_max_res: int = 1024,
               preview_frames: int = 1, preview_jpeg_quality: int = 80, preview_tiny_vae: str = "none",
               noise: object | None = None, guider: object | None = None, sampler: object | None = None) -> io.NodeOutput:
        return run_sampler(
            model=model, positive=positive, negative=negative, latent_image=latent_image,
            sampler_name=sampler_name, scheduler=scheduler, steps=steps, steps_to_run=steps_to_run,
            cfg=cfg, cfg_enabled=cfg_enabled, denoise=denoise, seed=seed, eta=eta,
            sampler_mode=sampler_mode, bongmath=bongmath, options=options, decode=decode,
            tiled_decode=tiled_decode, preview_fps=preview_fps, vae=vae, audio_vae=audio_vae,
            sigmas=sigmas, noise=noise, guider=guider, sampler=sampler, preview=preview,
            preview_max_res=preview_max_res, preview_frames=preview_frames,
            preview_jpeg_quality=preview_jpeg_quality, preview_tiny_vae=preview_tiny_vae,
            unique_id=cls.hidden.unique_id, dynprompt=cls.hidden.dynprompt)


# --------------------------------------------------------------------------- H3 KSampler

def guider_model(guider: object | None) -> object | None:
    return guider_model_slot(guider)[1]


class JWTFH3KSampler(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFH3KSampler",
            display_name='H3 KSampler',
            category='JezzWTF/sampling',
            description='H3 compatibility preset using the shared sampler backend: eight steps by default and positive-only guidance unless an external guider is supplied. Existing sockets and widget order are preserved.',
            inputs=[
                io.Latent.Input("latent_image", tooltip="Starting image, video or audio-video latent to denoise."),
                io.Combo.Input("sampler_name", options=base_samplers(), default='euler', tooltip="Sampling algorithm used when no external sampler is connected."),
                io.Combo.Input("scheduler", options=scheduler_choices(include_res4lyf=False), default='beta', tooltip="Noise schedule used when no external sigmas are connected."),
                io.Int.Input("steps", default=8, min=1, max=10000, tooltip="Number of steps used to build the noise schedule from the widgets."),
                io.Int.Input("steps_to_run", default=-1, min=-1, max=10000, tooltip="Limits how many initial schedule steps run, with -1 running the full schedule."),
                io.Float.Input("denoise", default=1.0, min=0.0, max=1.0, step=0.01, tooltip="Fraction of the widget-generated schedule used for denoising."),
                io.Int.Input("seed", default=0, min=0, max=18446744073709551615, tooltip="Seed used to create noise when no external noise generator is connected."),
                io.Boolean.Input("decode", default=True, tooltip="Decodes the sampled result through the connected VAEs when enabled."),
                io.Boolean.Input("tiled_decode", default=False, tooltip="Uses tiled decoding for the visual VAE when supported."),
                io.Int.Input("preview_fps", default=12, min=1, max=60, tooltip="Playback speed in frames per second for animated sampling previews."),
                io.Noise.Input("noise", optional=True, tooltip="Optional noise generator that overrides seeded noise from this node."),
                io.Guider.Input("guider", optional=True, tooltip="Optional external guider that replaces the node's basic positive-only guider."),
                io.Sampler.Input("sampler", optional=True, tooltip="Optional external sampler that overrides the sampler picker."),
                io.Sigmas.Input("sigmas", optional=True, tooltip="Optional explicit noise schedule, required when the scheduler is None."),
                io.Model.Input("model", optional=True, tooltip="Model used to build the basic guider and preferred for generating the noise schedule when connected."),
                io.Conditioning.Input("positive", optional=True, tooltip="Positive conditioning used to build the basic guider when no external guider is connected."),
                io.Vae.Input("vae", optional=True, tooltip="Optional VAE for visual decoding and sampling previews."),
                io.Vae.Input("audio_vae", optional=True, tooltip="Optional audio VAE for decoding the audio stream of an audio-video latent."),
                io.Boolean.Input("preview", default=True, optional=True, tooltip="Enables intermediate image or video previews during sampling."),
                io.Int.Input("preview_max_res", default=1024, min=0, max=8192, step=8, optional=True, tooltip="Maximum preview edge in pixels, with 0 disabling the resolution limit."),
                io.Int.Input("preview_frames", default=1, min=1, max=1024, optional=True, tooltip="Maximum number of frames in each preview update, with 1 showing a still image."),
                io.Int.Input("preview_jpeg_quality", default=80, min=30, max=100, optional=True, tooltip="JPEG compression quality for live preview frames on a scale from 30 to 100."),
                io.Combo.Input("preview_tiny_vae", options=tiny_vae_choices(), default='none', optional=True, tooltip="Installed decoder from models/vae_approx; none uses the normal preview fallback. Match the decoder to the model family."),
            ],
            outputs=[
                io.Latent.Output("latent", tooltip="Sampled latent at the end of the executed schedule."),
                io.Latent.Output("denoised", tooltip="Denoised latent when the sampler provides one, otherwise the sampled latent."),
                io.Image.Output("image", tooltip="Decoded image or frame batch, with a placeholder when visual decoding is unavailable or disabled."),
                io.Audio.Output("audio", tooltip="Decoded audio stream, with silence when audio decoding is unavailable or disabled."),
            ],
            hidden=[io.Hidden.unique_id, io.Hidden.dynprompt],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, latent_image: Latent, sampler_name: str, scheduler: str, steps: int, steps_to_run: int,
               denoise: float, seed: int, decode: bool, tiled_decode: bool, preview_fps: int,
               noise: object | None = None, guider: object | None = None, sampler: object | None = None,
               sigmas: torch.Tensor | None = None, model: object | None = None,
               positive: object | None = None, vae: object | None = None, audio_vae: object | None = None,
               preview: bool = True, preview_max_res: int = 1024, preview_frames: int = 1,
               preview_jpeg_quality: int = 80, preview_tiny_vae: str = "none") -> io.NodeOutput:
        return run_sampler(
            model=model, positive=positive, latent_image=latent_image, sampler_name=sampler_name,
            scheduler=scheduler, steps=steps, steps_to_run=steps_to_run, cfg=1.0, cfg_enabled=False,
            denoise=denoise, seed=seed, decode=decode, tiled_decode=tiled_decode,
            preview_fps=preview_fps, noise=noise, guider=guider, sampler=sampler, sigmas=sigmas,
            vae=vae, audio_vae=audio_vae, preview=preview, preview_max_res=preview_max_res,
            preview_frames=preview_frames, preview_jpeg_quality=preview_jpeg_quality,
            preview_tiny_vae=preview_tiny_vae, unique_id=cls.hidden.unique_id,
            dynprompt=cls.hidden.dynprompt, allow_clown=False)


NODES = [JWTFUltimateKSampler, JWTFH3KSampler]
