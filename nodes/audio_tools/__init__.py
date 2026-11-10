"""Audio tools: load audio files from the input folder and embed cover art into them."""
from __future__ import annotations

from comfy_api.latest import io

from .album_cover import JWTFAlbumCover
from .audio_loader import JWTFAudioLoader

NODES: list[type[io.ComfyNode]] = [JWTFAudioLoader, JWTFAlbumCover]

__all__ = ["NODES"]
