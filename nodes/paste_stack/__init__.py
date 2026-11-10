"""Paste Stack: a floating clipboard-history panel. Adds no nodes, only a clipboard helper route."""

from __future__ import annotations

from comfy_api.latest import io

from .routes import register_with_server

NODES: list[type[io.ComfyNode]] = []

ROUTES_REGISTERED = register_with_server()

__all__ = ["NODES", "ROUTES_REGISTERED"]
