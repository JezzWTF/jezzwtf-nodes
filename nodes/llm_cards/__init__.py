"""LLM + cards node family: LM Studio bridge, layout prompts, bounding boxes, card bakers, character chat."""

from __future__ import annotations

from comfy_api.latest import io

from . import character_chat as _character_chat
from . import lmstudio as _lmstudio
from .bakers import JWTFV2PNGBaker, JWTFWorkflowPNGBaker
from .bboxes import JWTFBoundingBoxes
from .character_chat import JWTFCharacterChat
from .common import register_routes
from .layout_prompt import JWTFLayoutLLMPrompt
from .lmstudio import JWTFLMStudio, JWTFLMStudioPromptBox

NODES: list[type[io.ComfyNode]] = [
    JWTFLMStudio,
    JWTFLMStudioPromptBox,
    JWTFLayoutLLMPrompt,
    JWTFBoundingBoxes,
    JWTFV2PNGBaker,
    JWTFWorkflowPNGBaker,
    JWTFCharacterChat,
]


def _register_all(routes: object) -> None:
    _lmstudio.register(routes)
    _character_chat.register(routes)


ROUTES_REGISTERED = register_routes(_register_all)

__all__ = ["NODES"]
