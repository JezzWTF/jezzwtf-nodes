"""Samplers with live preview: Ultimate KSampler and the CFG-free H3 KSampler (spec section 12).

Both are output nodes sharing the preview wrapper (``preview.py``) and one frontend. They return
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


# --------------------------------------------------------------------------- Ultimate KSampler

class JWTFUltimateKSampler(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFUltimateKSampler",
            display_name='Ultimate KSampler',
            category='JezzWTF/sampling',
            description='KSampler with live preview, chained step runs, RES4LYF dispatch and optional decode.',
            inputs=[
                io.Model.Input("model"),
                io.Conditioning.Input("positive"),
                io.Latent.Input("latent_image"),
                io.Combo.Input("sampler_name", options=sampler_choices(), default='euler'),
                io.Combo.Input("scheduler", options=scheduler_choices(), default='beta'),
                io.Int.Input("steps", default=30, min=1, max=10000),
                io.Int.Input("steps_to_run", default=-1, min=-1, max=10000),
                io.Float.Input("cfg", default=5.5, min=-100.0, max=100.0, step=0.01, round=False),
                io.Boolean.Input("cfg_enabled", default=True),
                io.Float.Input("denoise", default=1.0, min=0.0, max=1.0, step=0.01),
                io.Int.Input("seed", default=0, min=0, max=18446744073709551615),
                io.Float.Input("eta", default=0.5, min=-100.0, max=100.0, step=0.01),
                io.Combo.Input("sampler_mode", options=list(SAMPLER_MODES), default='standard'),
                io.Boolean.Input("bongmath", default=True),
                io.Boolean.Input("decode", default=True),
                io.Boolean.Input("tiled_decode", default=False),
                io.Int.Input("preview_fps", default=12, min=1, max=60),
                io.Conditioning.Input("negative", optional=True),
                io.Vae.Input("vae", optional=True),
                io.Vae.Input("audio_vae", optional=True),
                io.Sigmas.Input("sigmas", optional=True),
                io.Custom("OPTIONS").Input("options", optional=True),
                io.Boolean.Input("preview", default=True, optional=True),
                io.Int.Input("preview_max_res", default=1024, min=0, max=8192, step=8, optional=True),
                io.Int.Input("preview_frames", default=1, min=1, max=1024, optional=True),
                io.Int.Input("preview_jpeg_quality", default=80, min=30, max=100, optional=True),
                io.Combo.Input("preview_tiny_vae", options=['none'], default='none', optional=True),
            ],
            outputs=[
                io.Latent.Output("latent"),
                io.Latent.Output("denoised"),
                io.Image.Output("image"),
                io.Audio.Output("audio"),
            ],
            hidden=[io.Hidden.unique_id, io.Hidden.dynprompt],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, model: object, positive: object, latent_image: Latent, sampler_name: str, scheduler: str,
               steps: int, steps_to_run: int, cfg: float, cfg_enabled: bool, denoise: float, seed: int,
               eta: float, sampler_mode: str, bongmath: bool, decode: bool, tiled_decode: bool,
               preview_fps: int, negative: object | None = None, vae: object | None = None,
               audio_vae: object | None = None, sigmas: torch.Tensor | None = None,
               options: object | None = None, preview: bool = True, preview_max_res: int = 1024,
               preview_frames: int = 1, preview_jpeg_quality: int = 80, preview_tiny_vae: str = "none") -> io.NodeOutput:
        unique_id = cls.hidden.unique_id
        dynprompt = cls.hidden.dynprompt
        emit_phase(unique_id, dynprompt, "sampling")
        use_cfg = bool(cfg_enabled)
        if negative is None:
            negative = positive
            use_cfg = False
        model = _maybe_preview(model, preview, preview_max_res, preview_jpeg_quality, preview_frames,
                               preview_fps, preview_tiny_vae, vae, audio_vae, unique_id, dynprompt)
        if scheduler == "none" and sigmas is None:
            raise RefModError("scheduler is 'none' but no sigmas are connected")
        latent, denoised = cls._dispatch(model, positive, negative, latent_image, sampler_name, scheduler,
                                          int(steps), int(steps_to_run), float(cfg), use_cfg, float(denoise),
                                          int(seed), float(eta), sampler_mode, bool(bongmath), sigmas, options)
        return finish(latent, denoised, bool(decode), vae, audio_vae, bool(tiled_decode), unique_id, dynprompt)

    @staticmethod
    def _dispatch(model: object, positive: object, negative: object, latent_image: Latent, sampler_name: str,
                  scheduler: str, steps: int, steps_to_run: int, cfg: float, use_cfg: bool, denoise: float,
                  seed: int, eta: float, sampler_mode: str, bongmath: bool, sigmas: torch.Tensor | None,
                  options: object | None) -> tuple[Latent, Latent | None]:
        sched = real_scheduler(scheduler)
        if sampler_name.startswith(CLOWN_PREFIX):
            cls = res4lyf_sampler_class()
            if cls is None:
                raise RefModError("a 'clown:' sampler needs the RES4LYF node pack, which is not loaded")
            out = _comfy.call_node(
                cls, model=model, positive=positive, negative=negative, latent_image=latent_image,
                sampler_name=sampler_name[len(CLOWN_PREFIX):],
                scheduler=PLACEHOLDER_SCHEDULER if scheduler == "none" else scheduler, steps=steps,
                steps_to_run=steps_to_run, denoise=denoise, cfg=cfg if use_cfg else 1.0, seed=seed, eta=eta,
                sampler_mode=sampler_mode, bongmath=bongmath, sigmas=sigmas,
                options_group={"options0": options} if options is not None else None)
            return _latent_pair(out)
        if sigmas is not None or not use_cfg or steps_to_run >= 1:
            core = _custom_core()
            noise = _comfy.call_node(getattr(core, "RandomNoise"), noise_seed=seed)[0]
            if use_cfg:
                guider = _comfy.call_node(getattr(core, "CFGGuider"), model=model, positive=positive,
                                          negative=negative, cfg=cfg)[0]
            else:
                guider = _comfy.call_node(getattr(core, "BasicGuider"), model=model, conditioning=positive)[0]
            sampler = _comfy.call_node(getattr(core, "KSamplerSelect"), sampler_name=sampler_name)[0]
            run_sigmas = sigmas if sigmas is not None else widget_sigmas(model, sched, steps, denoise)
            return run_custom_advanced(noise, guider, sampler, trim_sigmas(run_sigmas, steps_to_run), latent_image)
        nodes = _comfy.comfy_nodes()
        if nodes is None:
            raise RefModError("ComfyUI's nodes module is unavailable")
        out = nodes.common_ksampler(model, seed, steps, cfg, sampler_name, sched, positive, negative,
                                    latent_image, denoise=denoise)
        return _latent_pair(tuple(out))


# --------------------------------------------------------------------------- H3 KSampler

def guider_model(guider: object | None) -> object | None:
    """The model patcher inside a guider: first attribute that can be cloned and wrapped."""
    if guider is None:
        return None
    for attr in GUIDER_MODEL_ATTRS:
        cand = getattr(guider, attr, None)
        if cand is not None and hasattr(cand, "clone") and hasattr(cand, "add_wrapper_with_key"):
            return cand
    return None


class JWTFH3KSampler(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFH3KSampler",
            display_name='H3 KSampler',
            category='JezzWTF/sampling',
            description='CFG-free SamplerCustomAdvanced-shaped sampler for MiniMax H3 with live preview.',
            inputs=[
                io.Latent.Input("latent_image"),
                io.Combo.Input("sampler_name", options=base_samplers(), default='euler'),
                io.Combo.Input("scheduler", options=scheduler_choices(include_res4lyf=False), default='beta'),
                io.Int.Input("steps", default=8, min=1, max=10000),
                io.Int.Input("steps_to_run", default=-1, min=-1, max=10000),
                io.Float.Input("denoise", default=1.0, min=0.0, max=1.0, step=0.01),
                io.Int.Input("seed", default=0, min=0, max=18446744073709551615),
                io.Boolean.Input("decode", default=True),
                io.Boolean.Input("tiled_decode", default=False),
                io.Int.Input("preview_fps", default=12, min=1, max=60),
                io.Noise.Input("noise", optional=True),
                io.Guider.Input("guider", optional=True),
                io.Sampler.Input("sampler", optional=True),
                io.Sigmas.Input("sigmas", optional=True),
                io.Model.Input("model", optional=True),
                io.Conditioning.Input("positive", optional=True),
                io.Vae.Input("vae", optional=True),
                io.Vae.Input("audio_vae", optional=True),
                io.Boolean.Input("preview", default=True, optional=True),
                io.Int.Input("preview_max_res", default=1024, min=0, max=8192, step=8, optional=True),
                io.Int.Input("preview_frames", default=1, min=1, max=1024, optional=True),
                io.Int.Input("preview_jpeg_quality", default=80, min=30, max=100, optional=True),
                io.Combo.Input("preview_tiny_vae", options=['none'], default='none', optional=True),
            ],
            outputs=[
                io.Latent.Output("latent"),
                io.Latent.Output("denoised"),
                io.Image.Output("image"),
                io.Audio.Output("audio"),
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
        unique_id = cls.hidden.unique_id
        dynprompt = cls.hidden.dynprompt
        emit_phase(unique_id, dynprompt, "sampling")
        # The preview must wrap the model the guider actually samples (it carries its LoRA/refmod patches);
        # the ``model`` input is only a fallback and the source of the sigma schedule.
        guided = guider_model(guider)
        base = guided if guided is not None else (model if guider is None else None)
        sigma_model = model if model is not None else guided
        do_preview = bool(preview)
        if guider is None and model is None:
            raise RefModError("connect a model or a guider")
        if base is None:
            if sigmas is None and sigma_model is None:
                raise RefModError("a guider without a model needs sigmas (the schedule cannot be computed)")
            log.warning("H3 KSampler: no guider model to attach the preview to; running without preview")
            do_preview = False
        if guider is None and positive is None:
            raise RefModError("connect a guider or a positive conditioning")
        preview_model: object | None = None
        if base is not None and do_preview:
            preview_model = _maybe_preview(base, do_preview, preview_max_res, preview_jpeg_quality,
                                           preview_frames, preview_fps, preview_tiny_vae, vae, audio_vae,
                                           unique_id, dynprompt)
        core = _custom_core()
        run_guider = guider
        if guider is not None and preview_model is not None and preview_model is not base:
            try:
                run_guider = copy.copy(guider)
                setattr(run_guider, "model_patcher", preview_model)
            except Exception as exc:
                log.warning("H3 KSampler: could not attach the preview to the guider (%s)", exc)
                run_guider = guider
        if noise is None:
            noise = _comfy.call_node(getattr(core, "RandomNoise"), noise_seed=int(seed))[0]
        if run_guider is None:
            run_guider = _comfy.call_node(getattr(core, "BasicGuider"), model=preview_model or base,
                                          conditioning=positive)[0]
        if sampler is None:
            sampler = _comfy.call_node(getattr(core, "KSamplerSelect"), sampler_name=sampler_name)[0]
        if sigmas is None:
            if scheduler == "none":
                raise RefModError("scheduler is 'none' but no sigmas are connected")
            assert sigma_model is not None
            sigmas = widget_sigmas(sigma_model, real_scheduler(scheduler), int(steps), float(denoise))
        latent, denoised = run_custom_advanced(noise, run_guider, sampler, trim_sigmas(sigmas, int(steps_to_run)),
                                               latent_image)
        return finish(latent, denoised, bool(decode), vae, audio_vae, bool(tiled_decode), unique_id, dynprompt)


NODES = [JWTFUltimateKSampler, JWTFH3KSampler]
