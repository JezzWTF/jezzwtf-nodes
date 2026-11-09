"""Pure logic for the Regional Character LoRA: region parsing, token masks, LoRA matrix
extraction, layer matching and the forward-hook delta. No ComfyUI imports."""
from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

import torch

CHARS = ("a", "b")
SIG_PREFIXES = ("lora_unet_", "lora_te_", "lora_", "diffusion_model.", "diffusion_model_", "transformer.",
                "model.diffusion_model.", "model.", "base_model.")
DOWN_SUFFIXES = (".lora_down.weight", ".lora_A.weight")
UP_SUFFIXES = (".lora_up.weight", ".lora_B.weight")
KeyMapValue = str | tuple[str, tuple[int, int, int]]


@dataclass
class Region:
    char: str = "a"
    x: float = 0.0
    y: float = 0.0
    w: float = 0.5
    h: float = 1.0
    text: str = ""


def _f(v: object, default: float) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return default
    try:
        f = float(v)
    except ValueError:
        return default
    return f if math.isfinite(f) else default


def parse_regions(raw: object) -> tuple[list[Region], str]:
    data: object = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw) if raw.strip() else {}
        except (ValueError, TypeError):
            return [], ""
    glob = ""
    if isinstance(data, dict):
        g = data.get("global", "")
        glob = g if isinstance(g, str) else ""
        data = data.get("regions", [])
    if not isinstance(data, list):
        return [], glob
    out: list[Region] = []
    for r in data:
        if not isinstance(r, dict):
            continue
        ch = str(r.get("char", "a")).lower()
        text = r.get("text", "")
        out.append(Region(char="b" if ch == "b" else "a", x=_f(r.get("x"), 0.0), y=_f(r.get("y"), 0.0),
                          w=_f(r.get("w"), 0.5), h=_f(r.get("h"), 1.0), text=text if isinstance(text, str) else ""))
    return out, glob


def latent_grid(h: int, w: int, patch: int = 2) -> tuple[int, int]:
    """Token grid of a patchified latent. Flux-style models pad to a multiple of the patch, so
    the grid is the ceiling of H/patch, W/patch."""
    return max(1, -(-h // patch)), max(1, -(-w // patch))


def rect_mask(rows: int, cols: int, x: float, y: float, w: float, h: float, feather: float) -> torch.Tensor:
    """Soft rectangle sampled at cell centres, flattened row-major to `rows*cols`."""
    c0, c1 = x * cols, (x + w) * cols
    r0, r1 = y * rows, (y + h) * rows
    fc = max(1e-3, feather * cols)
    fr = max(1e-3, feather * rows)
    j = torch.arange(cols, dtype=torch.float32) + 0.5
    i = torch.arange(rows, dtype=torch.float32) + 0.5
    # A side on the image border has nothing to blend into: no ramp there, or the border dims.
    edge = 1e-6
    mc = torch.ones_like(j)
    if x > edge:
        mc = mc * torch.sigmoid((j - c0) / fc)
    if x + w < 1.0 - edge:
        mc = mc * torch.sigmoid((c1 - j) / fc)
    mr = torch.ones_like(i)
    if y > edge:
        mr = mr * torch.sigmoid((i - r0) / fr)
    if y + h < 1.0 - edge:
        mr = mr * torch.sigmoid((r1 - i) / fr)
    return (mr[:, None] * mc[None, :]).clamp(0.0, 1.0).reshape(-1)


def char_masks(regions: Iterable[Region], rows: int, cols: int, feather: float) -> dict[str, torch.Tensor]:
    out: dict[str, torch.Tensor] = {}
    for r in regions:
        m = rect_mask(rows, cols, r.x, r.y, r.w, r.h, feather)
        out[r.char] = torch.maximum(out[r.char], m) if r.char in out else m
    return out


def token_mask(grid_mask: torch.Tensor, seq: int) -> torch.Tensor | None:
    """Image tokens are assumed to trail any text tokens in the sequence."""
    n_img = grid_mask.numel()
    if seq == n_img:
        return grid_mask
    if seq > n_img:
        return torch.cat([torch.zeros(seq - n_img, dtype=grid_mask.dtype, device=grid_mask.device), grid_mask])
    return None


def sig(s: str) -> str:
    s = s.lower()
    for p in SIG_PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
    return s.replace(".", "").replace("_", "")


@dataclass
class LoraPair:
    down: torch.Tensor  # [rank, in]
    up: torch.Tensor  # [out, rank]
    scale: float


def extract_lora_pairs(sd: Mapping[str, torch.Tensor]) -> dict[str, LoraPair]:
    alphas: dict[str, float] = {}
    downs: dict[str, torch.Tensor] = {}
    ups: dict[str, torch.Tensor] = {}
    for key, val in sd.items():
        if key.endswith("alpha"):
            base = key[: -len(".alpha")] if key.endswith(".alpha") else key[: -len("alpha")]
            alphas[base] = float(val.flatten()[0])
            continue
        for suf in DOWN_SUFFIXES:
            if key.endswith(suf):
                downs[key[: -len(suf)]] = val.float()
        for suf in UP_SUFFIXES:
            if key.endswith(suf):
                ups[key[: -len(suf)]] = val.float()
    out: dict[str, LoraPair] = {}
    for base, down in downs.items():
        up = ups.get(base)
        if up is None or down.ndim != 2 or up.ndim != 2 or up.shape[1] != down.shape[0]:
            continue
        rank = down.shape[0]
        alpha = alphas.get(base, float(rank))
        out[base] = LoraPair(down=down, up=up, scale=alpha / rank)
    return out


@dataclass(frozen=True)
class Target:
    char: str
    base: str
    offset: int | None = None  # output-feature slice for fused layers (e.g. qkv)
    size: int | None = None


def _module_from_weight_key(k: str) -> str:
    if k.startswith("diffusion_model."):
        k = k[len("diffusion_model."):]
    return k[: -len(".weight")] if k.endswith(".weight") else k


def resolve_targets(per_char: Mapping[str, Iterable[str]], module_names: Iterable[str],
                    key_map: Mapping[str, KeyMapValue] | None = None) -> dict[str, list[Target]]:
    """Map LoRA bases onto module names. ComfyUI's own LoRA key map is tried first (it knows
    diffusers/kohya/fused-qkv layouts); the normalised-signature match is the fallback."""
    names = list(module_names)
    name_set = set(names)
    by_sig: dict[str, str] = {}
    for n in names:
        by_sig.setdefault(sig(n), n)
    out: dict[str, list[Target]] = {}
    for char, bases in per_char.items():
        for base in bases:
            target: tuple[str, Target] | None = None
            mapped = key_map.get(base) if key_map else None
            if isinstance(mapped, str):
                mod = _module_from_weight_key(mapped)
                if mod in name_set:
                    target = (mod, Target(char, base))
            elif isinstance(mapped, tuple) and len(mapped) == 2:
                mod = _module_from_weight_key(mapped[0])
                dim, off, size = mapped[1]
                if mod in name_set and dim == 0:
                    target = (mod, Target(char, base, off, size))
            if target is None and sig(base) in by_sig:
                target = (by_sig[sig(base)], Target(char, base))
            if target is not None:
                out.setdefault(target[0], []).append(target[1])
    return out


def cond_box_mask(x: float, y: float, w: float, h: float, size: int = 256) -> torch.Tensor:
    y0 = min(max(round(y * size), 0), size - 1)
    x0 = min(max(round(x * size), 0), size - 1)
    y1 = min(max(round((y + h) * size), y0 + 1), size)
    x1 = min(max(round((x + w) * size), x0 + 1), size)
    m = torch.zeros((1, size, size), dtype=torch.float32)
    m[:, y0:y1, x0:x1] = 1.0
    return m


def compute_dtype(dtype: torch.dtype) -> torch.dtype:
    return dtype if dtype in (torch.float16, torch.bfloat16) else torch.float32


@dataclass
class RegionalSession:
    """State captured by the diffusion-model wrapper. Matrices are prepared per (device, dtype)
    so a model moved between devices or precisions keeps working."""

    regions: list[Region]
    feather: float
    pairs: dict[str, dict[str, LoraPair]]  # char → base → pair (scale already × strength)
    grid: tuple[int, int] | None = None
    _grid_masks: dict[str, torch.Tensor] = field(default_factory=dict)
    _mask_cache: dict[tuple[str, int, str, torch.dtype], torch.Tensor | None] = field(default_factory=dict)
    _prepared: dict[tuple[str, torch.dtype], dict[tuple[str, str], tuple[torch.Tensor, torch.Tensor]]] = field(
        default_factory=dict)
    probed: bool = False
    applied: bool = False  # a masked delta has been added at least once
    idle_reported: bool = False
    seen_seqs: set[int] = field(default_factory=set)

    def release(self) -> None:
        """Drop the per-device matrices and mask caches (called when sampling cleans up)."""
        self._prepared.clear()
        self._mask_cache.clear()

    def idle_reason(self) -> str | None:
        """Once, after a model call in which no delta was ever applied: why. None otherwise."""
        if self.applied or self.idle_reported:
            return None
        self.idle_reported = True
        if self.grid is None:
            return "no 4-D [B, C, H, W] latent reached the model (5-D video latents are not supported)"
        n_img = self.grid[0] * self.grid[1]
        seqs = sorted(self.seen_seqs)[:6]
        return (f"no layer saw at least {n_img} tokens for a {self.grid[0]}x{self.grid[1]} image-token grid "
                f"(sequence lengths seen: {seqs}); the model probably uses a patch size other than 2")

    def set_grid(self, grid: tuple[int, int] | None) -> None:
        if grid == self.grid:
            return
        self.grid = grid
        self._mask_cache.clear()
        self._grid_masks = char_masks(self.regions, grid[0], grid[1], self.feather) if grid else {}

    def mask_for(self, char: str, seq: int, device: torch.device, dtype: torch.dtype) -> torch.Tensor | None:
        key = (char, seq, str(device), dtype)
        if key not in self._mask_cache:
            g = self._grid_masks.get(char)
            m = token_mask(g, seq) if g is not None else None
            self._mask_cache[key] = m.to(device=device, dtype=dtype) if m is not None else None
        return self._mask_cache[key]

    def matrices(self, device: torch.device, dtype: torch.dtype) -> dict[tuple[str, str], tuple[torch.Tensor, torch.Tensor]]:
        key = (str(device), dtype)
        if key not in self._prepared:
            self._prepared[key] = {
                (c, b): (p.down.to(device=device, dtype=dtype), (p.up * p.scale).to(device=device, dtype=dtype))
                for c, bases in self.pairs.items() for b, p in bases.items()
            }
        return self._prepared[key]

    def apply(self, targets: list[Target], x_in: torch.Tensor, out: torch.Tensor) -> torch.Tensor:
        """Forward-hook body: add each side's masked low-rank delta to `out`."""
        if out.ndim < 2 or x_in.ndim < 2 or self.grid is None:
            return out
        seq = out.shape[-2]
        if len(self.seen_seqs) < 16:
            self.seen_seqs.add(seq)
        cd = compute_dtype(out.dtype)
        mats = self.matrices(out.device, cd)
        x = x_in.to(cd)
        result: torch.Tensor | None = None
        for t in targets:
            mask = self.mask_for(t.char, seq, out.device, cd)
            pair = mats.get((t.char, t.base))
            if mask is None or pair is None:
                continue
            down, up = pair
            try:
                delta = (x @ down.T) @ up.T
            except RuntimeError:
                continue
            width = t.size if t.size is not None else out.shape[-1]
            if delta.shape[-1] != width or delta.shape[-2] != seq:
                continue
            delta = delta * mask.view(*([1] * (delta.ndim - 2)), seq, 1)
            if result is None:
                result = out.clone()
            if t.offset is None:
                result += delta.to(out.dtype)
            else:
                result[..., t.offset:t.offset + width] += delta.to(out.dtype)
        if result is not None:
            self.applied = True
        return out if result is None else result
