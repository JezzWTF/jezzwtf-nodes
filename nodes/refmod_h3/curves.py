"""Apply math for H3 RefMods: strength, temporal curves, blur-mixing, scramble, budget,
and injection into conditioning. Pure logic (torch only).
"""
from __future__ import annotations

import dataclasses
import logging
import math
import random
from collections.abc import Callable, Sequence
from typing import Protocol, Union, runtime_checkable

import torch
import torch.nn.functional as F

from ._types import RefModError
from .bundle import RefMod

log = logging.getLogger("jezzwtf.refmod_h3")

DIRECTIONS = ("constant", "concept_at_start", "concept_at_end", "concept_at_middle", "concept_at_ends")
DIRECTION_ALIASES = {"decrease": "concept_at_start", "increase": "concept_at_end"}
SCRAMBLE_MODES = ("shuffle", "subset", "legacy_subset")
RETENTION_PRESETS = {
    "fully_preserved": 1.0,
    "partially_preserved": 0.7,
    "attribute_transfer": 0.4,
    "weak_reference": 0.15,
}


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def _elastic(x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return 2.0 ** (-10.0 * x) * math.sin((10.0 * x - 0.75) * (2.0 * math.pi / 3.0)) + 1.0


EASINGS: dict[str, Callable[[float], float]] = {
    "linear": lambda x: x,
    "ease": lambda x: x * x * (3.0 - 2.0 * x),
    "sigmoid": lambda x: 1.0 / (1.0 + math.exp(-12.0 * (x - 0.5))),
    "tanh": lambda x: 0.5 * (math.tanh(8.0 * (x - 0.5)) + 1.0),
    "quadratic": lambda x: x * x,
    "cubic": lambda x: x * x * x,
    "exponential": lambda x: 2.0 ** x - 1.0,
    "stair": lambda x: min(1.0, math.floor(4.0 * x) / 3.0),
    "elastic": _elastic,
    "bump": lambda x: 1.0 - abs(2.0 * x - 1.0),
    "dip": lambda x: abs(2.0 * x - 1.0),
}
SHAPES = tuple(EASINGS)

CURVE_PRESETS: dict[str, tuple[str, str, float]] = {
    "flat": ("constant", "linear", 1.0),
    "fade_in": ("concept_at_end", "linear", 1.0),
    "fade_out": ("concept_at_start", "linear", 1.0),
    "bump": ("concept_at_end", "bump", 1.0),
    "dip": ("constant", "dip", 1.0),
}


@runtime_checkable
class Interpolant(Protocol):
    def interp(self, x: float) -> float: ...


CurveSpec = Union[None, str, tuple[str, str, float], Sequence[float], Sequence[tuple[float, float]], Interpolant]


def normalise_direction(direction: str) -> str:
    d = str(direction).strip()
    return DIRECTION_ALIASES.get(d, d)


def _xs(t: int) -> list[float]:
    return [i / (t - 1) for i in range(t)]


def direction_curve(direction: str, shape: str, value: float, t: int) -> list[float] | None:
    """Per-frame curve for ``t`` frames from a (direction, shape, value) triple."""
    if t <= 1:
        return None
    ease = EASINGS.get(shape)
    if ease is None:
        raise RefModError(f"unknown curve shape {shape!r}; expected one of {', '.join(SHAPES)}")
    d = normalise_direction(direction)
    v = float(value)
    ys = [ease(x) for x in _xs(t)]
    if d == "constant":
        if shape == "linear":
            return None if v >= 1.0 else [v] * t
        return [_clamp01(v * y) for y in ys]
    if d == "concept_at_end":
        return [_clamp01(v * y) for y in ys]
    if d == "concept_at_start":
        return [_clamp01(v * (1.0 - y)) for y in ys]
    if d == "concept_at_middle":
        return [_clamp01(v * (1.0 - abs(2.0 * y - 1.0))) for y in ys]
    if d == "concept_at_ends":
        return [_clamp01(v * abs(2.0 * y - 1.0)) for y in ys]
    return None


def _interp_points(points: Sequence[tuple[float, float]], x: float) -> float:
    pts = sorted((float(px), float(py)) for px, py in points)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y1
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def frame_curve(spec: CurveSpec, t: int) -> list[float] | None:
    """Resolve any accepted curve spec to per-frame values for ``t`` frames (None = flat)."""
    if spec is None or t <= 1:
        return None
    if isinstance(spec, str):
        preset = CURVE_PRESETS.get(spec.strip())
        if preset is None:
            raise RefModError(f"unknown curve preset {spec!r}")
        return direction_curve(*preset, t)
    if isinstance(spec, Interpolant):
        return [float(spec.interp(x)) for x in _xs(t)]
    if isinstance(spec, tuple) and len(spec) == 3 and isinstance(spec[0], str):
        return direction_curve(spec[0], str(spec[1]), float(spec[2]), t)
    if isinstance(spec, Sequence):
        items = list(spec)
        if items and all(isinstance(p, (tuple, list)) and len(p) == 2 for p in items):
            pts = [(float(p[0]), float(p[1])) for p in items]  # type: ignore[index]
            return [_interp_points(pts, x) for x in _xs(t)]
        if len(items) == t and all(isinstance(v, (int, float)) for v in items):
            return [float(v) for v in items]  # type: ignore[arg-type]
        raise RefModError(f"curve list must have exactly {t} numbers or (x, y) control points")
    raise RefModError(f"unsupported curve spec {type(spec).__name__}")


def resolve_retention(retention: float | str) -> float:
    if isinstance(retention, str):
        key = retention.strip()
        if key in RETENTION_PRESETS:
            return RETENTION_PRESETS[key]
        try:
            return float(key)
        except ValueError as exc:
            raise RefModError(f"unknown retention {retention!r}") from exc
    return float(retention)


def effective_strength(row_strength: float, retention: float | str) -> float:
    return _clamp01(float(row_strength) * resolve_retention(retention))


# --------------------------------------------------------------------------- blur mixing

def blur_latent(kind: str, latent: torch.Tensor) -> torch.Tensor:
    """A low-pass copy: weakening mixes toward this, never toward zero or noise."""
    dev = latent.device
    work = latent.to("cpu") if dev.type == "mps" else latent
    x = work.float()
    if kind == "audio":
        b, c, two, t = x.shape
        if t <= 1:
            return latent
        flat = x.reshape(b * c * two, 1, t)
        pooled = F.adaptive_avg_pool1d(flat, max(1, t // 8))
        up = F.interpolate(pooled, size=t, mode="linear", align_corners=False)
        out = up.reshape(b, c, two, t)
    else:
        _, _, t, h, w = x.shape
        pooled = F.adaptive_avg_pool3d(x, (t, max(1, h // 8), max(1, w // 8)))
        out = F.interpolate(pooled, size=(t, h, w), mode="trilinear", align_corners=False)
    return out.to(dtype=latent.dtype, device=dev)


def weaken(mod: RefMod, eff: float, curve: list[float] | None) -> torch.Tensor:
    latent = mod.latent
    if curve is not None:
        weights = [_clamp01(eff * c) for c in curve]
        if all(w >= 1.0 for w in weights):
            return latent
        blurred = blur_latent(mod.kind, latent)
        w = torch.tensor(weights, dtype=torch.float32, device=latent.device)
        shape = [1, 1, len(weights), 1, 1] if mod.is_visual else [1, 1, 1, len(weights)]
        w = w.view(*shape)
        return (w * latent.float() + (1.0 - w) * blurred.float()).to(latent.dtype)
    if eff < 1.0:
        blurred = blur_latent(mod.kind, latent)
        return (eff * latent.float() + (1.0 - eff) * blurred.float()).to(latent.dtype)
    return latent


BlockValue = Union[str, int, bool, torch.Tensor, None]
Block = dict[str, BlockValue]


def make_block(mod: RefMod, latent: torch.Tensor) -> Block:
    if mod.kind == "audio":
        return {"kind": "audio", "ref_audio_t": int(latent.shape[-1]), "audio_latent": latent, "refmod": True}
    _, _, t, h, w = latent.shape
    block: Block = {"kind": mod.kind, "latent_h": int(h), "latent_w": int(w), "latent": latent}
    if mod.kind == "video":
        block.update({"latent_t": int(t), "ref_audio_t": 0, "audio_latent": None})
    block["refmod"] = True
    return block


def ref_block(mod: RefMod, eff: float, curve_spec: CurveSpec) -> Block | None:
    """Build one injected reference block, or None when the effective strength is 0."""
    if eff <= 0.0:
        return None
    t = mod.latent_t
    curve: list[float] | None
    if t <= 1 and isinstance(curve_spec, tuple) and len(curve_spec) == 3 \
            and normalise_direction(curve_spec[0]) != "constant":
        cap = _clamp01(float(curve_spec[2]))
        if cap < eff:
            log.info("refmod %s: single-frame mod, curve direction ignored; value %.2f caps strength",
                     mod.name, cap)
        eff = min(eff, cap)
        curve = None
        if eff <= 0.0:
            return None
    else:
        curve = frame_curve(curve_spec, t)
    return make_block(mod, weaken(mod, eff, curve))


# --------------------------------------------------------------------------- scramble / budget

Row = tuple[RefMod, float]


def scramble_rows(rows: list[Row], seed: int, mode: str, keep: int) -> list[Row]:
    if seed < 0 or len(rows) < 2:
        return list(rows)
    if mode not in SCRAMBLE_MODES:
        raise RefModError(f"unknown scramble mode {mode!r}; expected one of {', '.join(SCRAMBLE_MODES)}")
    rng = random.Random(seed)
    out = list(rows)
    rng.shuffle(out)
    n = len(out)
    if mode == "legacy_subset":
        return out[: rng.randint(max(1, n // 2), n)]
    if mode == "subset":
        return out[: max(1, int(keep))]
    return out


def total_tokens(rows: list[Row]) -> int:
    return sum(m.token_count for m, s in rows if s > 0)


def check_budget(rows: list[Row], budget: int | float) -> int:
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) \
            or budget < 0 or int(budget) != budget:
        raise RefModError(f"token budget must be a finite non-negative integer, got {budget!r}")
    total = total_tokens(rows)
    if int(budget) > 0 and total > int(budget):
        raise RefModError(f"RefMods use {total} reference tokens, over the budget of {int(budget)}. "
                          "Lower copies/slots or raise the token budget.")
    return total


# --------------------------------------------------------------------------- injection

CondEntry = list[object]  # [tensor, dict]


def inject_blocks(conditioning: object, blocks: list[Block]) -> object:
    """Append blocks to ``minimax_refs`` (CONDITIONING list) or to a ``MINIMAX_H3_COND.refs``."""
    if isinstance(conditioning, list):
        out: list[CondEntry] = []
        for entry in conditioning:
            if not isinstance(entry, (list, tuple)) or len(entry) < 2 or not isinstance(entry[1], dict):
                raise RefModError("conditioning entry is not [tensor, dict]")
            d = dict(entry[1])
            existing = d.get("minimax_refs") or []
            d["minimax_refs"] = list(existing) + list(blocks)
            out.append([entry[0], d, *entry[2:]])
        return out
    if dataclasses.is_dataclass(conditioning) and not isinstance(conditioning, type) \
            and hasattr(conditioning, "refs"):
        refs = list(getattr(conditioning, "refs") or [])
        return dataclasses.replace(conditioning, refs=refs + list(blocks))  # type: ignore[type-var]
    raise RefModError(f"unsupported conditioning type {type(conditioning).__name__}; "
                      "connect MiniMax H3 conditioning")


def apply_rows(conditioning: object, rows: list[Row], retention: float | str = 1.0,
               curve: CurveSpec = None, scramble_seed: int = -1, scramble_mode: str = "shuffle",
               scramble_keep: int = 1, budget: int = 0) -> tuple[object, int]:
    """Scramble, budget-check, weaken and inject. Returns (conditioning, block count)."""
    chosen = scramble_rows(rows, scramble_seed, scramble_mode, scramble_keep)
    check_budget(chosen, budget)
    blocks: list[Block] = []
    for mod, strength in chosen:
        block = ref_block(mod, effective_strength(strength, retention), curve)
        if block is not None:
            blocks.append(block)
    if not blocks:
        return conditioning, 0
    return inject_blocks(conditioning, blocks), len(blocks)
