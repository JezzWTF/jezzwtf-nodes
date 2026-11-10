"""Ultimate Model Loader: diffusion model + attention backend + sparse attention + 2 CLIPs + 2 VAEs
(spec section 14).

Every recent/experimental ComfyUI API (``get_attention_function``, ``QUANT_ALGOS``,
``quantization_metadata``, ``set_model_optimized_attention``, ``apply_block_sparse_attention``)
is probed and degrades with a warning instead of breaking the node.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

from comfy_api.latest import io

from . import _comfy
from ._types import RefModError

log = logging.getLogger("jezzwtf.refmod_h3")

STATUS_EVENT = "jezzwtf.uml_status"
MODEL_TYPES = ("default", "minimax_h3", "flux3", "moss")
QUANT_BASE = ("auto", "bf16")
CLIP_DEVICES = ("default", "cpu")
PREFERRED_CLIP_TYPES = ("stable_diffusion", "sd3", "flux", "minimax", "hunyuan_video", "wan", "ltxv")
# Names this node (and saved workflows) used for CLIP types that core spells differently.
CLIP_TYPE_ALIASES = {"minimax_h3": "minimax", "moss": "moss_image"}
STATIC_CLIP_TYPES = ("stable_diffusion", "stable_cascade", "sd3", "stable_audio", "hunyuan_dit", "flux", "mochi",
                     "ltxv", "hunyuan_video", "pixart", "cosmos", "lumina2", "wan", "hidream", "chroma", "ace",
                     "omnigen2", "qwen_image", "hunyuan_image", "flux2", "minimax", "flux3", "moss_image")
# First existing CLIPType per model type. ComfyUI 0.44 has MINIMAX (MiniMax H3 and p-h3-image text
# encoders), FLUX3 and MOSS_IMAGE; the older names stay as fallbacks for builds without them.
CLIP_FALLBACKS: dict[str, tuple[str, ...]] = {
    "minimax_h3": ("MINIMAX", "MINIMAX_H3", "HUNYUAN_VIDEO"),
    "flux3": ("FLUX3", "FLUX2", "FLUX"),
    "moss": ("MOSS_IMAGE", "STABLE_DIFFUSION"),
    "default": ("STABLE_DIFFUSION",),
}
DEFAULT_HEADINGS = {"heading_model": "Model", "heading_engine": "Efficiencies",
                    "heading_clips": "Text Encoders", "heading_vaes": "VAEs"}
DEFAULT_SECTION_ORDER = "model,engine,clips,vaes"
SECTIONS = ("model", "engine", "clips", "vaes")
KNOWN_QUANT_NAMES = ("float8_e4m3fn", "float8_e5m2", "nvfp4", "mxfp8", "int8_tensorwise", "convrot_w4a4",
                     "asym_w4a8_int8", "w6a8_int8", "int8", "fp8", "gguf")

# (switch, registry names probed in order); the first enabled switch that resolves wins.
ATTENTION_PRIORITY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("sage3", ("sage3", "sageattn3", "sage_attention3")),
    ("sage2", ("sage", "sage2", "sageattn", "sage_attention")),
    ("flash2", ("flash", "flash2", "flash_attention", "flash_attn", "flash_attention2")),
    ("kitchen", ("comfy_kitchen_int8", "comfy_kitchen", "kitchen_int8")),
    ("pytorch", ("pytorch", "pytorch_attention", "sdpa")),
)

AttentionFn = Callable[..., object]


# --------------------------------------------------------------------------- choices

def clip_type_names() -> list[str]:
    """``auto`` + preferred types that exist + the rest, sorted (lower-case enum names)."""
    sd = _comfy.optional_module("comfy.sd")
    enum = getattr(sd, "CLIPType", None) if sd is not None else None
    try:
        names = sorted(str(m.name).lower() for m in enum) if enum is not None else []  # type: ignore[attr-defined]
    except TypeError:
        names = []
    if not names:
        names = list(STATIC_CLIP_TYPES)
    preferred = [n for n in PREFERRED_CLIP_TYPES if n in names]
    return ["auto"] + preferred + sorted(n for n in names if n not in preferred)


def quant_algo_names() -> list[str]:
    qo = _comfy.optional_module("comfy.quant_ops")
    algos = getattr(qo, "QUANT_ALGOS", None) if qo is not None else None
    return sorted(str(k) for k in algos) if isinstance(algos, dict) else []


def quant_choices() -> list[str]:
    return list(QUANT_BASE) + quant_algo_names()


# --------------------------------------------------------------------------- quantisation check (log only)

@dataclass(frozen=True)
class QuantReport:
    detected: list[str]
    level: str        # "info" | "warning"
    message: str


def quant_report(requested: str, metadata: object | None, known: list[str] | None = None) -> QuantReport:
    names = list(known) if known else list(KNOWN_QUANT_NAMES)
    present = metadata is not None and metadata != {} and metadata != ""
    text = ""
    if present:
        try:
            text = json.dumps(metadata, default=str)
        except (TypeError, ValueError):
            text = str(metadata)
    detected = [n for n in names if n in text]
    if requested == "bf16":
        if present:
            return QuantReport(detected, "warning", "quant_format is bf16 but the model carries quantisation metadata")
        return QuantReport(detected, "info", "bf16 model, no quantisation metadata")
    if requested != "auto":
        if not present:
            return QuantReport(detected, "warning", f"quant_format {requested} requested but the model has no quantisation metadata")
        if not detected:
            return QuantReport(detected, "info", f"quant_format {requested} requested; the model is quantised but ComfyUI does not report which format")
        if requested not in detected:
            return QuantReport(detected, "warning", f"quant_format {requested} not found in the model metadata (found: {', '.join(detected) or 'unknown'})")
        return QuantReport(detected, "info", f"quantisation {requested} confirmed")
    if present:
        return QuantReport(detected, "info", f"quantised model ({', '.join(detected) or 'metadata present'})")
    return QuantReport(detected, "info", "no quantisation metadata (bf16/fp16)")


def model_quant_config(model: object) -> object | None:
    """The quantisation config ComfyUI detected for ``model`` (``model.model.model_config.quant_config``)."""
    inner = getattr(model, "model", None)
    config = getattr(inner, "model_config", None)
    quant = getattr(config, "quant_config", None)
    return quant if quant else None


# --------------------------------------------------------------------------- attention backend

def resolve_backend(flags: dict[str, bool], getter: Callable[[str], AttentionFn | None]
                    ) -> tuple[str | None, AttentionFn | None, list[str]]:
    """First enabled switch (priority order) whose registry name resolves.

    Returns ``(registry name, function, warnings)``; an enabled switch with no registered name warns.
    """
    warnings: list[str] = []
    for switch, names in ATTENTION_PRIORITY:
        if not flags.get(switch):
            continue
        for name in names:
            try:
                fn = getter(name)
            except Exception:
                fn = None
            if fn is not None:
                return name, fn, warnings
        warnings.append(f"{switch} is enabled but no attention function is registered for it "
                        f"(tried {', '.join(names)})")
    return None, None, warnings


def registry_getter() -> Callable[[str], AttentionFn | None]:
    mod = _comfy.optional_module("comfy.ldm.modules.attention")
    get = getattr(mod, "get_attention_function", None) if mod is not None else None

    def getter(name: str) -> AttentionFn | None:
        if get is None:
            return None
        try:
            return get(name, None)  # type: ignore[no-any-return]
        except TypeError:
            return None
    return getter


def set_attention(model: object, fn: AttentionFn) -> object:
    """Clone ``model`` and route its attention through ``fn``; returns the original if unsupported."""
    if not hasattr(model, "clone"):
        return model
    clone = model.clone()  # type: ignore[attr-defined]
    setter = getattr(clone, "set_model_optimized_attention", None)
    if callable(setter):
        setter(fn)
        return clone
    opts = getattr(clone, "model_options", None)
    if isinstance(opts, dict):
        topts = opts.setdefault("transformer_options", {})
        if isinstance(topts, dict):
            def override(_func: AttentionFn, *args: object, **kwargs: object) -> object:
                # Registered attention functions are wrapped by comfy's ``wrap_attn``; keep the
                # ``_inside_attn_wrapper`` marker so the wrapper runs the raw function instead of
                # dispatching back into this override.
                return fn(*args, **kwargs)
            topts["optimized_attention_override"] = override
            return clone
    log.warning("Ultimate Loader: this ComfyUI cannot override model attention; backend not applied")
    return model


# --------------------------------------------------------------------------- CLIP

def auto_clip_type(model_type: str) -> str | None:
    """First existing CLIPType (lower-case name) from the model type's fallback list."""
    sd = _comfy.optional_module("comfy.sd")
    enum = getattr(sd, "CLIPType", None) if sd is not None else None
    for name in CLIP_FALLBACKS.get(model_type, CLIP_FALLBACKS["default"]):
        if enum is None or hasattr(enum, name):
            return name.lower()
    return None


def clip_type_value(choice: str, model_type: str) -> object:
    sd = _comfy.optional_module("comfy.sd")
    if sd is None:
        raise RefModError("comfy.sd is unavailable")
    enum = sd.CLIPType
    if choice == "auto":
        name = auto_clip_type(model_type)
    elif hasattr(enum, choice.upper()):
        name = choice
    else:
        name = CLIP_TYPE_ALIASES.get(choice, choice)
    if name is None or not hasattr(enum, name.upper()):
        raise RefModError(f"unknown CLIP type {choice!r}; available: {', '.join(clip_type_names()[1:])}")
    return getattr(enum, name.upper())


def _embedding_dir() -> str | None:
    paths = _comfy.folder_paths_for("embeddings")
    return paths[0] if paths else None


def _model_path(folder: str, fallback: str, name: str) -> str:
    path = _comfy.full_path(folder, name) or _comfy.full_path(fallback, name)
    if not path:
        raise RefModError(f"{name!r} not found in models/{folder}")
    return path


def load_clip(name: str, type_choice: str, device: str, model_type: str) -> object:
    sd = _comfy.optional_module("comfy.sd")
    if sd is None:
        raise RefModError("comfy.sd is unavailable")
    path = _model_path("text_encoders", "clip", name)
    options: dict[str, object] = {}
    if device == "cpu":
        import torch
        options = {"load_device": torch.device("cpu"), "offload_device": torch.device("cpu")}
    return sd.load_clip(ckpt_paths=[path], embedding_directory=_embedding_dir(),
                        clip_type=clip_type_value(type_choice, model_type), model_options=options)


def load_vae(name: str) -> object:
    sd = _comfy.optional_module("comfy.sd")
    utils = _comfy.optional_module("comfy.utils")
    if sd is None or utils is None:
        raise RefModError("comfy.sd is unavailable")
    state, metadata = utils.load_torch_file(_model_path("vae", "vae", name), return_metadata=True)
    vae = sd.VAE(sd=state, metadata=metadata)
    check = getattr(vae, "throw_exception_if_invalid", None)
    if callable(check):
        check()
    return vae


# --------------------------------------------------------------------------- sparse attention

def is_h3_model(model: object) -> bool:
    """True when the patcher holds the MiniMax H3 diffusion model (``MiniMaxH3Model``)."""
    getter = getattr(model, "get_model_object", None)
    if not callable(getter):
        return True  # cannot tell; let core decide
    try:
        dm = getter("diffusion_model")
    except Exception:
        return True
    return type(dm).__name__ == "MiniMaxH3Model"


def apply_sparse(model: object, vsa: bool, model_type: str) -> object:
    mod = _comfy.optional_module("comfy_extras.nodes_sparse_attention")
    fn = getattr(mod, "apply_block_sparse_attention", None) if mod is not None else None
    if fn is None:
        raise RefModError("sparse / VSA attention needs comfy_extras.nodes_sparse_attention, which this "
                          "ComfyUI build does not have; update ComfyUI or turn sparse and vsa off")
    if vsa and model_type != "minimax_h3":
        log.warning("Ultimate Loader: vsa is meant for minimax_h3 models (model_type is %s)", model_type)
    if vsa and not is_h3_model(model):
        # core's apply_block_sparse_attention raises a bare ValueError for this; fail with a readable message
        raise RefModError("vsa (video sparse attention) only works on MiniMax H3 models; "
                          "load an H3 diffusion model or switch vsa off")
    out = fn(model, tau=1.3, topk_ratio=0.0, vsa=vsa, start_percent=0.2, end_percent=1.0, min_tokens=12288,
             dense_blocks=set(), sink_conditioning="exact_kv_and_rows", extra_tokens=0 if vsa else 256,
             verbose=False)
    return out[0] if isinstance(out, tuple) else out


def apply_triton_flag() -> bool:
    """Set ComfyUI's triton flag; warns when it cannot take effect (the backend registry is read once at import)."""
    cli = _comfy.optional_module("comfy.cli_args")
    args = getattr(cli, "args", None)
    if args is None:
        log.warning("Ultimate Loader: comfy.cli_args unavailable; triton flag not set")
        return False
    already = bool(getattr(args, "enable_triton_backend", False))
    setattr(args, "enable_triton_backend", True)
    if already:
        return True
    qo = _comfy.optional_module("comfy.quant_ops")
    if qo is not None:
        log.warning("Ultimate Loader: triton has no effect now; ComfyUI read --enable-triton-backend when it "
                    "started and already disabled the triton backend. Launch ComfyUI with --enable-triton-backend")
    return False


# --------------------------------------------------------------------------- section helpers

def normalise_section_order(value: str) -> list[str]:
    """Unknown keys dropped, duplicates ignored, missing sections appended."""
    seen: list[str] = []
    for part in str(value or "").split(","):
        key = part.strip()
        if key in SECTIONS and key not in seen:
            seen.append(key)
    return seen + [s for s in SECTIONS if s not in seen]


def switch(text: str, default: bool = False) -> tuple[str, dict[str, object]]:
    """Boolean whose on/off labels are the same text (the frontend draws its own switch)."""
    return "BOOLEAN", {"default": default, "label_on": text, "label_off": text}


# --------------------------------------------------------------------------- node

class JWTFUltimateModelLoader(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFUltimateModelLoader",
            display_name='Ultimate Model Loader',
            category='JezzWTF/loaders',
            description='Diffusion model, attention backend, block-sparse attention, two text encoders and two VAEs.',
            inputs=[
                io.Combo.Input("model_name", options=_comfy.filename_list("diffusion_models") or _comfy.filename_list("unet"), tooltip="Diffusion weights to load from ComfyUI's configured diffusion model folders."),
                io.Combo.Input("quant_format", options=quant_choices(), default='auto', tooltip="Expected weight quantisation for diagnostics, with auto reporting the metadata detected in the loaded model."),
                io.Combo.Input("model_type", options=list(MODEL_TYPES), default='default', tooltip="Model family hint used for automatic text encoder selection and sparse attention diagnostics."),
                io.Boolean.Input("kitchen", default=True, label_on='kitchen', label_off='kitchen', tooltip="Allows the registered Comfy Kitchen INT8 attention backend to be selected."),
                io.Boolean.Input("sage2", default=False, label_on='sage2', label_off='sage2', tooltip="Allows the registered SageAttention 2 backend to be selected."),
                io.Boolean.Input("sage3", default=False, label_on='sage3', label_off='sage3', tooltip="Allows the registered SageAttention 3 backend to be selected with highest priority."),
                io.Boolean.Input("triton", default=False, label_on='triton', label_off='triton', tooltip="Sets the Triton backend flag, which only takes effect if ComfyUI has enabled the backend at startup."),
                io.Boolean.Input("flash2", default=False, label_on='flash2', label_off='flash2', tooltip="Allows the registered FlashAttention 2 backend to be selected."),
                io.Boolean.Input("pytorch", default=False, label_on='pytorch', label_off='pytorch', tooltip="Allows registered PyTorch attention as the last fallback among enabled backends."),
                io.Boolean.Input("sparse", default=False, label_on='sparse', label_off='sparse', tooltip="Enables block-sparse attention on supported builds, mutually exclusive with VSA."),
                io.Boolean.Input("vsa", default=False, label_on='vsa', label_off='vsa', tooltip="Enables video sparse attention on MiniMax H3, mutually exclusive with block-sparse attention."),
                io.Combo.Input("clip1_name", options=_comfy.filename_list("text_encoders") or _comfy.filename_list("clip"), tooltip="Weights file for the primary text encoder."),
                io.Combo.Input("clip1_type", options=clip_type_names(), default='auto', tooltip="Primary text encoder architecture, with auto using the model family hint."),
                io.Combo.Input("clip1_device", options=list(CLIP_DEVICES), default='default', tooltip="Device placement for the primary text encoder, with default using ComfyUI's normal placement."),
                io.Boolean.Input("clip2_enabled", default=False, label_on='clip2_enabled', label_off='clip2_enabled', tooltip="Loads a separate second text encoder when enabled."),
                io.Combo.Input("clip2_name", options=_comfy.filename_list("text_encoders") or _comfy.filename_list("clip"), tooltip="Weights file for the optional second text encoder."),
                io.Combo.Input("clip2_type", options=clip_type_names(), default='auto', tooltip="Second text encoder architecture, with auto using the model family hint."),
                io.Combo.Input("clip2_device", options=list(CLIP_DEVICES), default='default', tooltip="Device placement for the second text encoder, with default using ComfyUI's normal placement."),
                io.Combo.Input("vae_name", options=_comfy.filename_list("vae"), tooltip="Weights file for the primary image or video VAE."),
                io.Boolean.Input("audio_vae_enabled", default=False, label_on='audio_vae_enabled', label_off='audio_vae_enabled', tooltip="Loads a separate audio VAE when enabled."),
                io.Combo.Input("audio_vae_name", options=_comfy.filename_list("vae"), tooltip="Weights file for the optional audio VAE."),
                io.String.Input("heading_model", default='Model', tooltip="Editable label for the model section, saved by the loader panel."),
                io.String.Input("heading_engine", default='Efficiencies', tooltip="Editable label for the efficiency settings section, saved by the loader panel."),
                io.String.Input("heading_clips", default='Text Encoders', tooltip="Editable label for the text encoder section, saved by the loader panel."),
                io.String.Input("heading_vaes", default='VAEs', tooltip="Editable label for the VAE section, saved by the loader panel."),
                io.String.Input("section_order", default='model,engine,clips,vaes', tooltip="Comma-separated section IDs written by the loader panel when sections are reordered."),
            ],
            outputs=[
                io.Model.Output("MODEL", tooltip="Loaded diffusion model with any selected attention patches."),
                io.Clip.Output("CLIP (main)", tooltip="Primary text encoder loaded for conditioning."),
                io.Clip.Output("CLIP (enhancer)", tooltip="Second text encoder for optional prompt enhancement, or empty when disabled."),
                io.Vae.Output("VAE (video/default)", tooltip="Primary image or video VAE."),
                io.Vae.Output("VAE (audio)", tooltip="Separate audio VAE, or empty when disabled."),
            ],
            hidden=[io.Hidden.unique_id],
        )

    @classmethod
    def validate_inputs(cls, **_: object) -> bool:
        return True

    @classmethod
    def execute(cls, model_name: str, quant_format: str, model_type: str, kitchen: bool, sage2: bool, sage3: bool,
             triton: bool, flash2: bool, pytorch: bool, sparse: bool, vsa: bool, clip1_name: str,
             clip1_type: str, clip1_device: str, clip2_enabled: bool, clip2_name: str, clip2_type: str,
             clip2_device: str, vae_name: str, audio_vae_enabled: bool, audio_vae_name: str,
             heading_model: str = "", heading_engine: str = "", heading_clips: str = "",
             heading_vaes: str = "", section_order: str = DEFAULT_SECTION_ORDER
             ) -> io.NodeOutput:
        unique_id = cls.hidden.unique_id
        if sparse and vsa:
            raise RefModError("sparse and vsa cannot both be on; pick one")
        if triton:
            apply_triton_flag()
        sd = _comfy.optional_module("comfy.sd")
        if sd is None:
            raise RefModError("comfy.sd is unavailable; this node only runs inside ComfyUI")
        model = sd.load_diffusion_model(_model_path("diffusion_models", "unet", model_name), model_options={})

        meta = model_quant_config(model)
        report = quant_report(quant_format, meta, quant_algo_names() or None)
        getattr(log, report.level)("Ultimate Loader: %s", report.message)

        flags = {"kitchen": kitchen, "sage2": sage2, "sage3": sage3, "flash2": flash2, "pytorch": pytorch}
        backend, fn, warnings = resolve_backend(flags, registry_getter())
        for w in warnings:
            log.warning("Ultimate Loader: %s", w)
        if fn is not None:
            model = set_attention(model, fn)

        if sparse or vsa:
            model = apply_sparse(model, bool(vsa), model_type)

        clip_main = load_clip(clip1_name, clip1_type, clip1_device, model_type)
        clip_extra = load_clip(clip2_name, clip2_type, clip2_device, model_type) if clip2_enabled else None
        vae = load_vae(vae_name)
        audio_vae = load_vae(audio_vae_name) if audio_vae_enabled else None

        _comfy.send_sync(STATUS_EVENT, {
            "node": str(unique_id), "model": model_name,
            "quant_detected": report.detected or (["metadata present"] if meta else []),
            "backend": backend, "sparse": bool(sparse), "vsa": bool(vsa),
            "clip2": bool(clip2_enabled), "audio_vae": bool(audio_vae_enabled),
        })
        return io.NodeOutput(model, clip_main, clip_extra, vae, audio_vae)


NODES = [JWTFUltimateModelLoader]
