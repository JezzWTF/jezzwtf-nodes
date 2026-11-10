"""Shared typing helpers for the RefMod / MiniMax H3 node family.

Free of ComfyUI imports so the pure-logic modules stay testable.
"""
from __future__ import annotations

from typing import Union

InputSpec = tuple[object, ...]
InputTypes = dict[str, dict[str, InputSpec]]
JSONScalar = Union[str, int, float, bool, None]
JSONValue = Union[JSONScalar, list["JSONValue"], dict[str, "JSONValue"]]
JSONDict = dict[str, JSONValue]
UIPayload = dict[str, list[object]]

CATEGORY_REFMOD = "JezzWTF/refmod"
CATEGORY_SAMPLING = "JezzWTF/sampling"
CATEGORY_LOADERS = "JezzWTF/loaders"

# Custom socket type carried between RefMod nodes: list[tuple[RefMod, float]].
H3_REF_MODS = "H3_REF_MODS"


class RefModError(ValueError):
    """User-facing error raised by the RefMod toolkit."""
