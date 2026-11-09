"""Shared typing helpers for the utility-core node family.

Kept free of ComfyUI imports so the pure-logic modules stay testable.
"""
from __future__ import annotations

from typing import Union

InputSpec = tuple[object, ...]
InputTypes = dict[str, dict[str, InputSpec]]
JSONScalar = Union[str, int, float, bool, None]
JSONValue = Union[JSONScalar, list["JSONValue"], dict[str, "JSONValue"]]
UIPayload = dict[str, list[object]]


class AnyType(str):
    """Socket type that never compares unequal, so it links to anything."""

    def __ne__(self, other: object) -> bool:
        return False

    __hash__ = str.__hash__


ANY = AnyType("*")

CATEGORY_UTILS = "JezzWTF/utils"
CATEGORY_IMAGE = "JezzWTF/image"
CATEGORY_DATASET = "JezzWTF/dataset"
CATEGORY_CONDITIONING = "JezzWTF/conditioning"
