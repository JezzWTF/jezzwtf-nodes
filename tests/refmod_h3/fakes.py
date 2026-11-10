"""Tiny stand-ins for ComfyUI objects (VAEs, CLIP) so the RefMod code runs without a GPU."""
from __future__ import annotations

import torch


class FakeH3VideoVAE:
    """Encodes [T,H,W,3] to [1,24,T,H//16,W//16] (the H3 video VAE keeps the frame count here)."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, int, int]] = []

    def encode(self, frames: torch.Tensor) -> torch.Tensor:
        t, h, w, _ = frames.shape
        self.calls.append((int(t), int(h), int(w)))
        base = frames.float().mean(dim=-1)  # [T,H,W]
        pooled = torch.nn.functional.adaptive_avg_pool2d(base, (h // 16, w // 16))  # [T,h,w]
        return pooled.unsqueeze(0).unsqueeze(0).repeat(1, 24, 1, 1, 1)


class MiniMaxH3AudioVAE:
    """Named like the real first-stage model: the audio extractor checks the class name."""

    def encode(self, wave: torch.Tensor) -> torch.Tensor:
        frames = max(1, wave.shape[-1] // 800)
        return torch.zeros(1, 32, 2, frames)


class FakeAudioVAE:
    def __init__(self) -> None:
        self.first_stage_model = MiniMaxH3AudioVAE()
        self.device = torch.device("cpu")
        self.vae_dtype = torch.float32
        self.patcher = object()


class FakeImageVAE:
    """4-D VAE: [B,H,W,C] -> [1,C_lat,H//16,W//16]."""

    def __init__(self, channels: int) -> None:
        self.channels = channels

    def encode(self, pixels: torch.Tensor) -> torch.Tensor:
        _, h, w, _ = pixels.shape
        m = pixels[..., :3].float().mean()
        return torch.full((1, self.channels, h // 16, w // 16), float(m))


class FakeClip:
    """Records tokenize calls and returns a one-entry conditioning list."""

    def __init__(self) -> None:
        self.tokenize_calls: list[dict[str, object]] = []

    def tokenize(self, text: str, **kwargs: object) -> dict[str, object]:
        self.tokenize_calls.append({"text": text, **kwargs})
        return {"text": text, "images": kwargs.get("images")}

    def encode_from_tokens_scheduled(self, tokens: dict[str, object]) -> list[list[object]]:
        return [[torch.zeros(1, 4), {"text": tokens["text"], "n_images": len(tokens["images"] or [])}]]  # type: ignore[arg-type]
