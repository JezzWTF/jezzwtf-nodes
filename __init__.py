"""JezzWTF nodes: utilities, LLM + character cards, model loaders, RefMod/H3, GIF tools and workspace panels."""
from __future__ import annotations

import importlib
import logging

from comfy_api.latest import ComfyExtension, io

_log = logging.getLogger(__name__)

_NODE_MODULES: tuple[str, ...] = (
    ".nodes.image_aspect_size",
    ".nodes.multi_switch",
    ".nodes.video_compare",
    ".nodes.utility_core",
    ".nodes.audio_tools",
    ".nodes.gallery",
    ".nodes.llm_cards",
    ".nodes.model_loaders",
    ".nodes.refmod_h3",
    ".nodes.paste_stack",
    ".nodes.run_timer",
    ".nodes.gif_tools",
)


def _collect_nodes() -> list[type[io.ComfyNode]]:
    """Every node class from every family; a family that fails to import is logged and skipped."""
    nodes: list[type[io.ComfyNode]] = []
    for name in _NODE_MODULES:
        try:
            module = importlib.import_module(name, __name__)
        except Exception:
            _log.exception("Failed to load JezzWTF nodes from %s", name)
            continue
        nodes.extend(getattr(module, "NODES", []))
    return nodes


class JezzWTFExtension(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return _collect_nodes()


async def comfy_entrypoint() -> JezzWTFExtension:
    return JezzWTFExtension()


WEB_DIRECTORY = "./js"

__all__ = ["comfy_entrypoint", "WEB_DIRECTORY"]
