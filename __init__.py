from .nodes.image_aspect_size import ImageAspectSize
from .nodes.multi_switch import MultiSwitch

NODE_CLASS_MAPPINGS = {
    "ImageAspectSize": ImageAspectSize,
    "MultiSwitch":     MultiSwitch,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageAspectSize": "Image Aspect Size",
    "MultiSwitch":     "Multi Switch",
}

WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
