"""Run Timer: times whole workflow runs into a persistent history (node, floating panel, routes)."""
from __future__ import annotations

from .node import NODES
from .routes import register_with_server

ROUTES_REGISTERED = register_with_server()

__all__ = ["NODES", "ROUTES_REGISTERED"]
