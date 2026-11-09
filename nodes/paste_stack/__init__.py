"""Paste Stack: a floating clipboard-history panel. Adds no nodes, only a clipboard helper route."""

from __future__ import annotations

from .routes import register_with_server

NODE_CLASS_MAPPINGS: dict[str, type] = {}
NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {}

ROUTES_REGISTERED = register_with_server()
