import importlib
import logging

from .nodes.image_aspect_size import ImageAspectSize
from .nodes.multi_switch import MultiSwitch
from .nodes.video_compare import VideoCompare

NODE_CLASS_MAPPINGS = {
    "ImageAspectSize": ImageAspectSize,
    "MultiSwitch":     MultiSwitch,
    "VideoCompare":    VideoCompare,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageAspectSize": "Image Aspect Size",
    "MultiSwitch":     "Multi Switch",
    "VideoCompare":    "Video Compare",
}

_NODE_MODULES = (
    ".nodes.utility_core",
    ".nodes.llm_cards",
    ".nodes.model_loaders",
    ".nodes.refmod_h3",
    ".nodes.paste_stack",
    ".nodes.run_timer",
    ".nodes.gif_tools",
)

_log = logging.getLogger(__name__)
for _module_name in _NODE_MODULES:
    try:
        _module = importlib.import_module(_module_name, __name__)
    except Exception:
        _log.exception("Failed to load JezzWTF nodes from %s", _module_name)
        continue
    NODE_CLASS_MAPPINGS.update(_module.NODE_CLASS_MAPPINGS)
    NODE_DISPLAY_NAME_MAPPINGS.update(_module.NODE_DISPLAY_NAME_MAPPINGS)

WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
