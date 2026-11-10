"""Gallery Load: a floating image gallery that feeds a loader node, plus the folder-listing route behind it."""
from __future__ import annotations

from comfy_api.latest import io

from .gallery_load import JWTFGalleryLoad
from .routes import register_with_server

NODES: list[type[io.ComfyNode]] = [JWTFGalleryLoad]

ROUTES_REGISTERED = register_with_server()

__all__ = ["NODES", "ROUTES_REGISTERED"]
