"""`JWTFRegionalLoRA`: two LoRAs, each applied at forward time only to the image tokens inside
its own region, plus regional text conditioning."""
from __future__ import annotations

from collections.abc import Callable, Mapping

import torch

from comfy_api.latest import io

from ._comfy import log, lora_full_path, lora_names
from .regional_logic import (
    KeyMapValue,
    LoraPair,
    Region,
    RegionalSession,
    Target,
    cond_box_mask,
    extract_lora_pairs,
    latent_grid,
    parse_regions,
    resolve_targets,
)

WRAPPER_KEY = "jezzwtf_regional_lora"
CondEntry = list[object]  # [tensor, dict]


def _load_pairs(name: str, strength: float) -> dict[str, LoraPair]:
    from safetensors.torch import load_file

    path = lora_full_path(name)
    if not path:
        raise FileNotFoundError(f"LoRA not found: {name}")
    sd: dict[str, torch.Tensor] = load_file(path, device="cpu")
    try:
        import comfy.lora_convert  # type: ignore[import-not-found]

        sd = comfy.lora_convert.convert_lora(sd)
    except Exception as exc:  # conversion is a nicety; raw keys still match by signature
        log.debug("convert_lora skipped: %s", exc)
    pairs = extract_lora_pairs(sd)
    for p in pairs.values():
        p.scale *= strength
    return pairs


def _key_map(model_base: object) -> Mapping[str, KeyMapValue]:
    try:
        import comfy.lora  # type: ignore[import-not-found]

        return comfy.lora.model_lora_keys_unet(model_base, {})
    except Exception as exc:
        log.debug("model_lora_keys_unet unavailable: %s", exc)
        return {}


def _find_latent(args: tuple[object, ...], kwargs: Mapping[str, object]) -> torch.Tensor | None:
    for v in list(args) + list(kwargs.values()):
        if isinstance(v, torch.Tensor) and v.ndim == 4:
            return v
    return None


def _encode(clip: object, text: str) -> list[CondEntry]:
    tokens = clip.tokenize(text)  # type: ignore[attr-defined]
    if hasattr(clip, "encode_from_tokens_scheduled"):
        out = clip.encode_from_tokens_scheduled(tokens)  # type: ignore[attr-defined]
        return [[c[0], dict(c[1])] for c in out]
    cond, pooled = clip.encode_from_tokens(tokens, return_pooled=True)  # type: ignore[attr-defined]
    return [[cond, {"pooled_output": pooled}]]


def build_conditioning(clip: object, regions: list[Region], glob: str) -> tuple[list[CondEntry], list[CondEntry]]:
    conds: list[CondEntry] = []
    if glob.strip():
        conds.extend(_encode(clip, glob))
    elif not any(r.text.strip() for r in regions):
        conds.extend(_encode(clip, ""))
    for r in regions:
        if not r.text.strip():
            continue
        mask = cond_box_mask(r.x, r.y, r.w, r.h)
        for c in _encode(clip, r.text):
            d = {k: v for k, v in dict(c[1]).items() if k != "area"}
            d.update({"mask": mask, "mask_strength": 1.0, "set_area_to_bounds": False})
            conds.append([c[0], d])
    if not conds:
        conds = _encode(clip, "")
    first_t, first_d = conds[0]
    assert isinstance(first_t, torch.Tensor) and isinstance(first_d, dict)
    neg_d = {k: v for k, v in first_d.items() if k not in ("area", "mask", "mask_strength", "set_area_to_bounds")}
    pooled = neg_d.get("pooled_output")
    if isinstance(pooled, torch.Tensor):
        neg_d["pooled_output"] = torch.zeros_like(pooled)
    return conds, [[torch.zeros_like(first_t), neg_d]]


def make_wrapper(session: RegionalSession, modules: Mapping[str, tuple[torch.nn.Module, list[Target]]]
                 ) -> Callable[..., object]:
    def hook_for(targets: list[Target]) -> Callable[[torch.nn.Module, tuple[object, ...], object], object]:
        def hook(_m: torch.nn.Module, inp: tuple[object, ...], out: object) -> object:
            if not isinstance(out, torch.Tensor) or out.ndim < 2 or not inp or not isinstance(inp[0], torch.Tensor):
                return None
            if not session.probed and session.grid and out.shape[-2] > session.grid[0] * session.grid[1]:
                session.probed = True
                log.info("Regional LoRA: joint text+image sequence seen (seq=%d, image=%d)",
                         out.shape[-2], session.grid[0] * session.grid[1])
            res = session.apply(targets, inp[0], out)
            return None if res is out else res
        return hook

    def wrapper(executor: Callable[..., object], *args: object, **kwargs: object) -> object:
        lat = _find_latent(args, kwargs)
        session.set_grid(latent_grid(lat.shape[-2], lat.shape[-1]) if lat is not None else None)
        handles = [mod.register_forward_hook(hook_for(tg)) for mod, tg in modules.values()]
        try:
            result = executor(*args, **kwargs)
        finally:
            for h in handles:
                h.remove()
        reason = session.idle_reason() if modules else None
        if reason:
            log.warning("Regional LoRA had no effect: %s", reason)
        return result

    return wrapper


class JWTFRegionalLoRA(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFRegionalLoRA",
            display_name='Regional Character LoRA',
            category='JezzWTF/lora',
            description='Two character LoRAs, each confined to its own region of the image, with per-region prompts.',
            inputs=[
                io.Model.Input("model"),
                io.Clip.Input("clip"),
                io.Combo.Input("lora_a", options=lora_names()),
                io.Float.Input("strength_a", default=1.0, min=-4.0, max=4.0, step=0.05),
                io.Combo.Input("lora_b", options=lora_names()),
                io.Float.Input("strength_b", default=1.0, min=-4.0, max=4.0, step=0.05),
                io.Float.Input("feather", default=0.06, min=0.0, max=0.3, step=0.01),
                io.String.Input("regions", default='{}', multiline=False),
            ],
            outputs=[
                io.Model.Output("MODEL"),
                io.Conditioning.Output("CONDITIONING"),
                io.Conditioning.Output("NEGATIVE"),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, regions: str = "", lora_a: str = "", lora_b: str = "", strength_a: float = 1.0,
                   strength_b: float = 1.0, feather: float = 0.06, **_: object) -> str:
        return f"{regions}|{lora_a}|{lora_b}|{strength_a}|{strength_b}|{feather}"

    @classmethod
    def execute(cls, model: object, clip: object, lora_a: str, strength_a: float, lora_b: str, strength_b: float,
              feather: float, regions: str) -> io.NodeOutput:
        region_list, glob = parse_regions(regions)
        pairs = {"a": _load_pairs(lora_a, strength_a), "b": _load_pairs(lora_b, strength_b)}

        patched = model.clone()  # type: ignore[attr-defined]
        base = patched.model
        target_root: torch.nn.Module = getattr(base, "diffusion_model", base)
        named = dict(target_root.named_modules())
        candidates = [n for n, m in named.items() if n and (isinstance(m, torch.nn.Linear) or (
            isinstance(getattr(m, "weight", None), torch.Tensor) and getattr(m, "weight").ndim == 2))]
        targets = resolve_targets({c: list(p) for c, p in pairs.items()}, candidates, _key_map(base))
        modules = {n: (named[n], tg) for n, tg in targets.items()}
        log.info("Regional LoRA: %d layers matched (A=%d, B=%d LoRA pairs)", len(modules), len(pairs["a"]),
                 len(pairs["b"]))
        if not modules:
            stems = [b for p in pairs.values() for b in list(p)[:5]]
            log.warning("Regional LoRA matched no layers. LoRA stems: %s; modules: %s", stems[:5], candidates[:5])

        session = RegionalSession(regions=region_list, feather=float(feather), pairs=pairs)
        wrapper = make_wrapper(session, modules)
        import comfy.patcher_extension  # type: ignore[import-not-found]

        kind = comfy.patcher_extension.WrappersMP.DIFFUSION_MODEL
        if hasattr(patched, "add_wrapper_with_key"):
            patched.add_wrapper_with_key(kind, WRAPPER_KEY, wrapper)
        elif hasattr(patched, "add_wrapper"):
            patched.add_wrapper(kind, wrapper)
        else:
            raise RuntimeError("This ComfyUI build has no model wrappers; Regional LoRA needs a newer ComfyUI.")

        if hasattr(patched, "add_callback_with_key"):  # free the GPU matrices when sampling cleans up
            patched.add_callback_with_key(comfy.patcher_extension.CallbacksMP.ON_CLEANUP, WRAPPER_KEY,
                                          lambda *_a, **_k: session.release())

        conds, negative = build_conditioning(clip, region_list, glob)
        return io.NodeOutput(patched, conds, negative)


NODES = [JWTFRegionalLoRA]
