"""Checks against a real ComfyUI checkout (skipped when none is found): the Prompt Relay bias must
reach the softmax through `wrap_attn`, and the wrapper/patcher APIs the regional LoRA uses must exist."""
from __future__ import annotations

import os
import sys

import pytest
import torch

COMFY_DIR = os.environ.get("COMFYUI_DIR", r"A:\GUIs\ComfyInstallTesting\ComfyUI_windows_portable\ComfyUI")

if not os.path.isfile(os.path.join(COMFY_DIR, "comfy", "ldm", "modules", "attention.py")):
    pytest.skip("no ComfyUI checkout", allow_module_level=True)
if COMFY_DIR not in sys.path:
    sys.path.append(COMFY_DIR)

attention = pytest.importorskip("comfy.ldm.modules.attention")

from model_loaders.relay_logic import RelayMask, build_segments, install_override, make_relay_override  # noqa: E402


def _reference(q: torch.Tensor, k: torch.Tensor, v: torch.Tensor, bias: torch.Tensor | None) -> torch.Tensor:
    s = (q @ k.transpose(-1, -2)) / q.shape[-1] ** 0.5
    if bias is not None:
        s = s + bias
    return torch.softmax(s, dim=-1) @ v


@pytest.mark.parametrize("masked", [False, True])
def test_relay_bias_reaches_comfy_softmax(masked: bool) -> None:
    torch.manual_seed(0)
    frames, tpf, lk, heads, dim = 4, 3, 8, 2, 8
    lq = frames * tpf
    q, k, v = (torch.randn(1, n, heads * dim) for n in (lq, lk, lk))
    segs = build_segments([(2, 4), (4, 8)], [2, 2], 1e-3)
    mask = RelayMask(segs, frames, tpf)
    topts: dict[str, object] = {"cond_or_uncond": [0]}
    model_options: dict[str, object] = {"transformer_options": topts}
    install_override(model_options, lambda prev: make_relay_override(mask, prev))
    opts = model_options["transformer_options"]
    assert isinstance(opts, dict)

    plain = attention.optimized_attention(q, k, v, heads, transformer_options={})
    fn = attention.optimized_attention_masked if masked else attention.optimized_attention
    args = (q, k, v, heads, None) if masked else (q, k, v, heads)
    patched = fn(*args, transformer_options=opts)
    assert not torch.allclose(plain, patched, atol=1e-4)

    bias = mask(lq, lk, q.dtype, q.device, opts)
    assert bias is not None
    qh, kh, vh = (t.view(1, -1, heads, dim).transpose(1, 2) for t in (q, k, v))
    expected = _reference(qh, kh, vh, bias).transpose(1, 2).reshape(1, lq, heads * dim)
    assert torch.allclose(patched, expected, atol=1e-4)


def test_model_patcher_wrapper_api_present() -> None:
    patcher_ext = pytest.importorskip("comfy.patcher_extension")
    model_patcher = pytest.importorskip("comfy.model_patcher")
    assert hasattr(patcher_ext.WrappersMP, "DIFFUSION_MODEL")
    assert hasattr(model_patcher.ModelPatcher, "add_wrapper_with_key")
    lora = pytest.importorskip("comfy.lora")
    assert callable(lora.model_lora_keys_unet)
