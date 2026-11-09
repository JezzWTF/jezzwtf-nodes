"""MiniMax H3 RefMod nodes: Bake, Loader, Apply and the clip-tail trio (spec section 7)."""
from __future__ import annotations

import json
import logging
import os

import torch

from ._types import CATEGORY_REFMOD, H3_REF_MODS, InputTypes, RefModError, UIPayload
from .bundle import RefMod, finite_unit, write_bundle
from .curves import DIRECTIONS, SCRAMBLE_MODES, SHAPES, Row, apply_rows, check_budget
from .extract import (
    H3_FPS, folder_change_key, load_folder, make_audio, make_visual, valid_len,
    write_sidecars,
)
from .library import (
    MOD_CACHE, combo_choices, file_stamp, library_entry, mod_output_path, normalise_name,
    resolve_path, resolve_stem, sanitise_save_name,
)

log = logging.getLogger("jezzwtf.refmod_h3")

SLOTS = 4
COMPONENTS = ("All", "Visual", "Audio")
AUDIO_TYPES = ("voice", "singing", "music_style", "sound_fx", "ambience")
INT31 = 2 ** 31 - 1
TAIL_SUBFOLDER = "_tail"

UNIT = {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}


# --------------------------------------------------------------------------- slots / collect

def slot_inputs(required: bool) -> tuple[dict[str, tuple[object, ...]], dict[str, tuple[object, ...]]]:
    """(required, optional) slot widgets. Loader keeps components/strengths optional."""
    names = combo_choices()
    req: dict[str, tuple[object, ...]] = {}
    opt: dict[str, tuple[object, ...]] = {}
    for i in range(1, SLOTS + 1):
        req[f"mod_{i}"] = (names, {"default": names[0]})
        target = req if required else opt
        target[f"visual_strength_{i}"] = ("FLOAT", dict(UNIT))
        target[f"audio_strength_{i}"] = ("FLOAT", dict(UNIT))
        req[f"strength_{i}"] = ("FLOAT", dict(UNIT))
        req[f"copies_{i}"] = ("INT", {"default": 1, "min": 1, "max": 10})
        target[f"components_{i}"] = (list(COMPONENTS), {"default": "All"})
    return req, opt


def _num(kwargs: dict[str, object], key: str, default: float) -> float:
    v = kwargs.get(key, default)
    return float(v) if isinstance(v, (int, float)) else default


def collect_slots(kwargs: dict[str, object], budget: int) -> tuple[list[Row], str, list[str]]:
    rows: list[tuple[RefMod, float, int]] = []
    for i in range(1, SLOTS + 1):
        name = normalise_name(kwargs.get(f"mod_{i}"))
        master = finite_unit(_num(kwargs, f"strength_{i}", 1.0), f"strength_{i}")
        if not name or master <= 0:
            continue
        vis = finite_unit(_num(kwargs, f"visual_strength_{i}", 1.0), f"visual_strength_{i}")
        aud = finite_unit(_num(kwargs, f"audio_strength_{i}", 1.0), f"audio_strength_{i}")
        comp = str(kwargs.get(f"components_{i}", "All") or "All")
        copies = max(1, int(_num(kwargs, f"copies_{i}", 1)))
        path = resolve_path(name)
        for mod in MOD_CACHE.load(path):
            weight = vis if mod.is_visual else aud
            if weight <= 0 or (comp == "Visual" and not mod.is_visual) or (comp == "Audio" and mod.is_visual):
                continue
            rows.append((mod, master * weight, copies))
    expanded: list[Row] = [(m, s) for m, s, c in rows for _ in range(c)]
    total = check_budget(expanded, budget)
    hint = "; ".join(f"{m.concept_type}: {m.description}" for m, _, _ in rows if m.description)
    lines = [
        f"{m.name} [{m.kind}] strength {s:.2f}{f' x{c}' if c > 1 else ''} - {m.token_count * c} tokens"
        for m, s, c in rows
    ]
    lines.append(f"total: {total} tokens" + (f" / budget {budget}" if budget > 0 else ""))
    return expanded, hint, lines


def mod_details(mod: RefMod) -> str:
    shape = "x".join(str(s) for s in mod.latent.shape)
    return (f"{mod.name}: kind={mod.kind} latent={shape} tokens={mod.token_count} source={mod.source} "
            f"[{mod.source_shape}] {mod.pool} tags={mod.tags} concept={mod.concept_type}"
            + (f" desc={mod.description!r}" if mod.description else ""))


def slots_is_changed(kwargs: dict[str, object]) -> tuple[object, ...]:
    out: list[object] = []
    for i in range(1, SLOTS + 1):
        v = kwargs.get(f"mod_{i}")
        if v is None:
            out.append(float("nan"))
            continue
        name = normalise_name(v)
        if not name:
            continue
        stem = resolve_stem(name)
        out.append(file_stamp(stem + ".safetensors") if stem else (name, "missing"))
    return tuple(out)


# --------------------------------------------------------------------------- bake

def _first_frame(t: torch.Tensor | None) -> torch.Tensor | None:
    if t is None or not isinstance(t, torch.Tensor) or t.numel() == 0:
        return None
    return t[:1] if t.dim() == 4 else t.unsqueeze(0)


def bake_bundle(dest: str, name: str, mods: list[RefMod]) -> list[RefMod]:
    write_bundle(dest, name, mods)
    MOD_CACHE.clear()
    return MOD_CACHE.load(dest)


class JWTFRefModBake:
    CATEGORY = CATEGORY_REFMOD
    RETURN_TYPES = (H3_REF_MODS, "STRING", "STRING")
    RETURN_NAMES = ("mods", "saved_path", "details")
    FUNCTION = "bake"
    OUTPUT_NODE = True
    DESCRIPTION = "Bake portrait stills, a clip and/or a voice into one reusable H3 RefMod bundle."

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {
                "name": ("STRING", {"default": "my_character"}),
                "vae": ("VAE",),
            },
            "optional": {
                "images": ("IMAGE",),
                "video_frames": ("IMAGE",),
                "folder": ("STRING", {"default": ""}),
                "audio": ("AUDIO",),
                "audio_vae": ("VAE",),
                "audio_type": (list(AUDIO_TYPES), {"default": "voice"}),
                "audio_max_seconds": ("FLOAT", {"default": 30.0, "min": 0.025, "max": 600.0, "step": 0.5}),
                "audio_max_tokens": ("INT", {"default": 5120, "min": 0, "max": INT31}),
                "ref_resolution": ("INT", {"default": 1024, "min": 256, "max": 2048, "step": 64}),
                "max_visual_tokens": ("INT", {"default": 16384, "min": 0, "max": INT31, "step": 512}),
                "visual_budget": (["error", "truncate"], {"default": "error"}),
                "folder_max_items": ("INT", {"default": 8, "min": 1, "max": 256}),
                "folder_max_edge": ("INT", {"default": 1536, "min": 256, "max": 4096, "step": 64}),
                "description": ("STRING", {"default": "", "multiline": True}),
                "subfolder": ("STRING", {"default": "characters"}),
                "overwrite": ("BOOLEAN", {"default": True}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, folder: str = "", folder_max_items: int = 8, **_: object) -> str:
        if not str(folder or "").strip():
            return ""
        return folder_change_key(folder, folder_max_items)

    def bake(self, name: str, vae: object, images: torch.Tensor | None = None,
             video_frames: torch.Tensor | None = None, folder: str = "", audio: dict[str, object] | None = None,
             audio_vae: object | None = None, audio_type: str = "voice", audio_max_seconds: float = 30.0,
             audio_max_tokens: int = 5120, ref_resolution: int = 1024, max_visual_tokens: int = 16384,
             visual_budget: str = "error", folder_max_items: int = 8, folder_max_edge: int = 1536,
             description: str = "", subfolder: str = "characters", overwrite: bool = True
             ) -> dict[str, object]:
        clean = sanitise_save_name(name)
        sub = str(subfolder or "").strip()
        image_refs: dict[str, torch.Tensor] = {}
        if isinstance(images, torch.Tensor) and images.numel():
            for i in range(images.shape[0]):
                image_refs[f"ref_image_{i + 1}"] = images[i:i + 1]
        video_refs: dict[str, torch.Tensor] = {}
        if isinstance(video_frames, torch.Tensor) and video_frames.numel():
            video_refs["ref_video_1"] = video_frames
        folder_refs: list[torch.Tensor] = []
        if str(folder or "").strip():
            folder_refs, _ = load_folder(folder, folder_max_items, folder_max_edge, max_frames=240)
        has_visual = bool(image_refs or video_refs or folder_refs)
        if not has_visual and audio is None:
            raise RefModError("RefMod Bake needs at least one source: images, video_frames, folder or audio")
        if audio is not None and audio_vae is None:
            raise RefModError("audio is connected but audio_vae is not; connect the MiniMax H3 audio VAE")
        dest = mod_output_path(clean, sub)
        if not overwrite and os.path.exists(dest):
            raise RefModError(f"{dest} already exists; enable overwrite or pick another name")
        mods: list[RefMod] = []
        if has_visual:
            mods.append(make_visual(f"{clean}_visual", vae, image_refs, video_refs, folder_refs,
                                    ref_resolution=ref_resolution, max_tokens=max_visual_tokens,
                                    budget_policy=visual_budget, description=description))
        if audio is not None:
            mods.append(make_audio(audio_vae, audio, f"{clean}_audio", audio_max_seconds, audio_max_tokens,
                                   "error", description, audio_type))
        loaded = bake_bundle(dest, clean, mods)
        thumb = _first_frame(images) if image_refs else (
            _first_frame(video_frames) if video_refs else (_first_frame(folder_refs[0]) if folder_refs else None))
        write_sidecars(dest[: -len(".safetensors")], thumb, audio, audio_max_seconds)
        lib_name = f"{sub}/{clean}" if sub else clean
        details = json.dumps({
            "name": clean, "file": dest, "total_tokens": sum(m.token_count for m in loaded),
            "members": [{"name": m.name, "kind": m.kind, "tokens": m.token_count} for m in loaded],
        }, indent=2)
        entry = library_entry(lib_name.replace("\\", "/"), dest)
        ui: UIPayload = {"text": [dest], "refmod_entry": [entry] if entry else []}
        return {"ui": ui, "result": ([(m, 1.0) for m in loaded], dest, details)}


# --------------------------------------------------------------------------- loader / apply

class JWTFRefModLoader:
    CATEGORY = CATEGORY_REFMOD
    RETURN_TYPES = (H3_REF_MODS, "STRING", "STRING")
    RETURN_NAMES = ("mods", "prompt_hint", "info")
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        req, opt = slot_inputs(required=False)
        ordered_req = {k: v for k, v in req.items()
                       if k.startswith(("mod_", "strength_", "copies_"))}
        opt = {"show_info": ("BOOLEAN", {"default": False}),
               "max_total_tokens": ("INT", {"default": 0, "min": 0, "max": 1_048_576}), **opt}
        return {"required": ordered_req, "optional": opt}

    @classmethod
    def VALIDATE_INPUTS(cls, **_: object) -> bool:
        return True

    @classmethod
    def IS_CHANGED(cls, **kwargs: object) -> tuple[object, ...]:
        return slots_is_changed(kwargs)

    def load(self, show_info: bool = False, max_total_tokens: int = 0, **kwargs: object) -> tuple[list[Row], str, str]:
        rows, hint, lines = collect_slots(kwargs, int(max_total_tokens))
        info = "\n".join(lines)
        log.info("RefMod Loader:\n%s", info)
        if show_info:
            seen: set[int] = set()
            for m, _ in rows:
                if id(m) not in seen:
                    seen.add(id(m))
                    log.info("  %s", mod_details(m))
        return rows, hint, info


class JWTFRefModApply:
    CATEGORY = CATEGORY_REFMOD
    RETURN_TYPES = ("CONDITIONING", "STRING", "STRING")
    RETURN_NAMES = ("conditioning", "prompt_hint", "info")
    FUNCTION = "apply"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        req, _ = slot_inputs(required=True)
        return {
            "required": {
                "conditioning": ("CONDITIONING",),
                **req,
                "retention": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.01}),
                "max_total_tokens": ("INT", {"default": 0, "min": 0, "max": 1_048_576}),
                "curve_direction": (list(DIRECTIONS), {"default": "constant"}),
                "curve_shape": (list(SHAPES), {"default": "linear"}),
                "curve_value": ("FLOAT", dict(UNIT)),
                "scramble_seed": ("INT", {"default": -1, "min": -1, "max": INT31}),
                "scramble_mode": (list(SCRAMBLE_MODES), {"default": "shuffle"}),
                "scramble_keep": ("INT", {"default": 1, "min": 1, "max": 80}),
            },
            "optional": {"extra_mods": (H3_REF_MODS,)},
        }

    @classmethod
    def VALIDATE_INPUTS(cls, **_: object) -> bool:
        return True

    @classmethod
    def IS_CHANGED(cls, **kwargs: object) -> tuple[object, ...]:
        return slots_is_changed(kwargs)

    def apply(self, conditioning: object, retention: float = 0.85, max_total_tokens: int = 0,
              curve_direction: str = "constant", curve_shape: str = "linear", curve_value: float = 1.0,
              scramble_seed: int = -1, scramble_mode: str = "shuffle", scramble_keep: int = 1,
              extra_mods: list[Row] | None = None, **kwargs: object) -> tuple[object, str, str]:
        budget = int(max_total_tokens)
        rows, hint, lines = collect_slots(kwargs, budget)
        if extra_mods:
            extra = [(m, float(s)) for m, s in extra_mods]
            rows = rows + extra
            total = check_budget(rows, budget)
            extra_hint = "; ".join(f"{m.concept_type}: {m.description}" for m, _ in extra if m.description)
            hint = "; ".join(h for h in (hint, extra_hint) if h)
            lines = lines[:-1] + [f"(extra) {m.name} [{m.kind}] strength {s:.2f} - {m.token_count} tokens"
                                  for m, s in extra]
            lines.append(f"total: {total} tokens" + (f" / budget {budget}" if budget > 0 else ""))
        info = "\n".join(lines)
        if not rows:
            return conditioning, hint, info
        out, n = apply_rows(conditioning, rows, retention, (curve_direction, curve_shape, float(curve_value)),
                            int(scramble_seed), scramble_mode, int(scramble_keep), budget)
        info += f"\ninjected {n} reference block(s)"
        log.info("RefMod Apply:\n%s", info)
        return out, hint, info


# --------------------------------------------------------------------------- tails

def tail_frames(images: torch.Tensor, tail_seconds: float, source_fps: float) -> torch.Tensor:
    if not isinstance(images, torch.Tensor) or images.dim() != 4 or images.shape[0] < 2:
        raise RefModError("tail needs at least 2 frames")
    total = int(images.shape[0])
    want = max(5, int(round(tail_seconds * H3_FPS)))
    length = valid_len(want)
    n_src = min(total, max(2, int(round(tail_seconds * source_fps))))
    window = images[total - n_src:]
    idx = [int(round(v)) for v in torch.linspace(0, n_src - 1, want).tolist()]
    return window[idx][-length:]


def tail_audio(audio: dict[str, object], tail_seconds: float) -> dict[str, object]:
    wave = audio.get("waveform")
    sr = audio.get("sample_rate")
    if not isinstance(wave, torch.Tensor) or not isinstance(sr, (int, float)):
        raise RefModError("invalid AUDIO input")
    n = max(1, int(round(tail_seconds * float(sr))))
    return {"waveform": wave[..., -n:], "sample_rate": sr}


def build_tail(name: str, images: torch.Tensor, vae: object, tail_seconds: float, source_fps: float,
               audio: dict[str, object] | None, audio_vae: object | None, audio_type: str,
               ref_resolution: int, max_visual_tokens: int, visual_budget: str, description: str
               ) -> tuple[list[RefMod], torch.Tensor]:
    if audio is not None and audio_vae is None:
        raise RefModError("audio is connected but audio_vae is not")
    frames = tail_frames(images, tail_seconds, source_fps)
    mods = [make_visual(f"{name}_visual", vae, {}, {"ref_video_1": frames}, [], ref_resolution=ref_resolution,
                        max_tokens=max_visual_tokens, budget_policy=visual_budget, description=description,
                        video_cap=int(frames.shape[0]))]
    if audio is not None:
        mods.append(make_audio(audio_vae, tail_audio(audio, tail_seconds), f"{name}_audio", tail_seconds + 0.5,
                               5120, "error", description, audio_type))
    return mods, frames


def _tail_optional() -> dict[str, tuple[object, ...]]:
    return {
        "audio": ("AUDIO",),
        "audio_vae": ("VAE",),
        "audio_type": (list(AUDIO_TYPES), {"default": "voice"}),
        "ref_resolution": ("INT", {"default": 512, "min": 256, "max": 2048, "step": 64}),
        "max_visual_tokens": ("INT", {"default": 16384, "min": 0, "max": INT31, "step": 512}),
        "visual_budget": (["truncate", "error"], {"default": "truncate"}),
        "description": ("STRING", {"default": "", "multiline": True}),
        "save_name": ("STRING", {"default": "tail_latest"}),
    }


def _tail_required() -> dict[str, tuple[object, ...]]:
    return {
        "images": ("IMAGE",),
        "vae": ("VAE",),
        "tail_seconds": ("FLOAT", {"default": 1.0, "min": 0.25, "max": 10.0, "step": 0.05}),
        "source_fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 0.5}),
    }


class JWTFTailRefMod:
    CATEGORY = CATEGORY_REFMOD
    RETURN_TYPES = (H3_REF_MODS, "STRING", "IMAGE")
    RETURN_NAMES = ("mods", "info", "tail_frames")
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {"required": {**_tail_required(), "strength": ("FLOAT", dict(UNIT))},
                "optional": _tail_optional()}

    def run(self, images: torch.Tensor, vae: object, tail_seconds: float, source_fps: float, strength: float,
            audio: dict[str, object] | None = None, audio_vae: object | None = None, audio_type: str = "voice",
            ref_resolution: int = 512, max_visual_tokens: int = 16384, visual_budget: str = "truncate",
            description: str = "", save_name: str = "tail_latest") -> tuple[list[Row], str, torch.Tensor]:
        name = sanitise_save_name(save_name)
        mods, frames = build_tail(name, images, vae, tail_seconds, source_fps, audio, audio_vae, audio_type,
                                  ref_resolution, max_visual_tokens, visual_budget, description)
        dest = mod_output_path(name, TAIL_SUBFOLDER)
        loaded = bake_bundle(dest, name, mods)
        info = "\n".join(f"{m.name} [{m.kind}] {m.token_count} tokens" for m in loaded) + f"\nsaved {dest}"
        return [(m, float(strength)) for m in loaded], info, frames


def _slot_paths(name: str) -> tuple[str, str]:
    return mod_output_path(f"{name}_a", TAIL_SUBFOLDER), mod_output_path(f"{name}_b", TAIL_SUBFOLDER)


def _mtime_ns(path: str) -> int:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return -1


def newest_slot(name: str) -> str | None:
    a, b = _slot_paths(name)
    ma, mb = _mtime_ns(a), _mtime_ns(b)
    if ma < 0 and mb < 0:
        return None
    return a if ma >= mb else b


def capture_target(name: str) -> str:
    """The slot that is NOT the most recently written (it may still be memory-mapped)."""
    a, b = _slot_paths(name)
    newest = newest_slot(name)
    return b if newest == a else a


class JWTFTailCapture:
    CATEGORY = CATEGORY_REFMOD
    RETURN_TYPES: tuple[str, ...] = ()
    FUNCTION = "run"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {"required": _tail_required(), "optional": _tail_optional()}

    def run(self, images: torch.Tensor, vae: object, tail_seconds: float, source_fps: float,
            audio: dict[str, object] | None = None, audio_vae: object | None = None, audio_type: str = "voice",
            ref_resolution: int = 512, max_visual_tokens: int = 16384, visual_budget: str = "truncate",
            description: str = "", save_name: str = "tail_latest") -> dict[str, object]:
        name = sanitise_save_name(save_name)
        mods, frames = build_tail(name, images, vae, tail_seconds, source_fps, audio, audio_vae, audio_type,
                                  ref_resolution, max_visual_tokens, visual_budget, description)
        dest = capture_target(name)
        write_bundle(dest, name, mods)
        MOD_CACHE.clear()
        summary = (f"tail saved: {os.path.basename(dest)} - {int(frames.shape[0])} frames, "
                   f"{sum(m.token_count for m in mods)} tokens" + (" + audio" if audio is not None else ""))
        return {"ui": {"text": [summary]}, "result": ()}


class JWTFTailLoad:
    CATEGORY = CATEGORY_REFMOD
    RETURN_TYPES = (H3_REF_MODS, "STRING")
    RETURN_NAMES = ("mods", "info")
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {"enabled": ("BOOLEAN", {"default": True}), "strength": ("FLOAT", dict(UNIT))},
            "optional": {"save_name": ("STRING", {"default": "tail_latest"})},
        }

    @classmethod
    def IS_CHANGED(cls, enabled: bool = True, strength: float = 1.0, save_name: str = "tail_latest") -> str:
        try:
            newest = newest_slot(sanitise_save_name(save_name))
        except RefModError:
            newest = None
        return f"{enabled}|{strength}|{_mtime_ns(newest) if newest else -1}"

    def run(self, enabled: bool, strength: float, save_name: str = "tail_latest") -> tuple[list[Row], str]:
        if not enabled:
            return [], "tail off"
        newest = newest_slot(sanitise_save_name(save_name))
        if newest is None:
            return [], "no tail saved yet (a Tail Capture at the end of the graph writes one)"
        mods = MOD_CACHE.load(newest)
        info = "\n".join(f"{m.name} [{m.kind}] {m.token_count} tokens" for m in mods) + f"\nfrom {newest}"
        return [(m, float(strength)) for m in mods], info


NODE_CLASS_MAPPINGS = {
    "JWTFRefModBake": JWTFRefModBake,
    "JWTFRefModLoader": JWTFRefModLoader,
    "JWTFRefModApply": JWTFRefModApply,
    "JWTFTailRefMod": JWTFTailRefMod,
    "JWTFTailCapture": JWTFTailCapture,
    "JWTFTailLoad": JWTFTailLoad,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "JWTFRefModBake": "RefMod Bake (Character)",
    "JWTFRefModLoader": "RefMod Loader",
    "JWTFRefModApply": "RefMod Apply",
    "JWTFTailRefMod": "Tail RefMod",
    "JWTFTailCapture": "Tail Capture",
    "JWTFTailLoad": "Tail Load",
}

