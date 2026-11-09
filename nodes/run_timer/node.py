"""The Run Timer node: a pass-through that marks a workflow as "time this run".

The timing itself is done by the browser (see js/run_timer) from ComfyUI execution events; the node
only tells the server when it executed and hands its optional input straight back, untouched.
"""
from __future__ import annotations

from .live import LIVE
from .store import now_ms

try:
    from ..utility_core._comfy import current_prompt_id
    from ..utility_core._types import ANY, CATEGORY_UTILS, InputTypes
except ImportError:  # imported as a top-level package (tests)
    from utility_core._comfy import current_prompt_id  # type: ignore[no-redef]
    from utility_core._types import ANY, CATEGORY_UTILS, InputTypes  # type: ignore[no-redef]


class JWTFRunTimer:
    CATEGORY = CATEGORY_UTILS
    FUNCTION = "run"
    OUTPUT_NODE = True  # executes even with nothing wired to it
    RETURN_TYPES = (ANY,)
    RETURN_NAMES = ("value",)

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "optional": {
                "value": (ANY, {}),
                "label": ("STRING", {"default": "", "multiline": False}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **_: object) -> float:
        return float("nan")  # never cached away: it must run on every queue

    def run(self, value: object = None, label: str = "") -> tuple[object]:
        LIVE.mark(current_prompt_id(), label if isinstance(label, str) else "", now_ms())
        return (value,)


NODE_CLASS_MAPPINGS = {"JWTFRunTimer": JWTFRunTimer}
NODE_DISPLAY_NAME_MAPPINGS = {"JWTFRunTimer": "Run Timer"}
