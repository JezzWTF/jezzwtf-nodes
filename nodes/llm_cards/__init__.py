"""LLM + cards node family: LM Studio bridge, layout prompts, bounding boxes, card bakers, character chat."""

from __future__ import annotations

from . import character_chat as _character_chat
from . import lmstudio as _lmstudio
from .bakers import JWTFV2PNGBaker, JWTFWorkflowPNGBaker
from .bboxes import JWTFBoundingBoxes
from .character_chat import JWTFCharacterChat
from .common import register_routes
from .layout_prompt import JWTFLayoutLLMPrompt
from .lmstudio import JWTFLMStudio, JWTFLMStudioPromptBox

NODE_CLASS_MAPPINGS = {
    "JWTFLMStudio": JWTFLMStudio,
    "JWTFLMStudioPromptBox": JWTFLMStudioPromptBox,
    "JWTFLayoutLLMPrompt": JWTFLayoutLLMPrompt,
    "JWTFBoundingBoxes": JWTFBoundingBoxes,
    "JWTFV2PNGBaker": JWTFV2PNGBaker,
    "JWTFWorkflowPNGBaker": JWTFWorkflowPNGBaker,
    "JWTFCharacterChat": JWTFCharacterChat,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "JWTFLMStudio": "LM Studio Bridge",
    "JWTFLMStudioPromptBox": "LM Studio Prompt Box",
    "JWTFLayoutLLMPrompt": "Layout LLM Prompt",
    "JWTFBoundingBoxes": "Bounding Boxes",
    "JWTFV2PNGBaker": "Character Card PNG Baker",
    "JWTFWorkflowPNGBaker": "Workflow PNG Baker",
    "JWTFCharacterChat": "Character Chat",
}


def _register_all(routes: object) -> None:
    _lmstudio.register(routes)
    _character_chat.register(routes)


ROUTES_REGISTERED = register_routes(_register_all)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
