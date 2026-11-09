"""Remote Set / Get: pass a value across the graph without a visible wire.

Execution order fix: the frontend rewrites the prompt so every Get receives a
hidden `set_link` input wired to the matching Set's output. That makes ComfyUI
run the Set first and cache the Get correctly. The process-global store stays
as a fallback for a Get without that link (e.g. Set muted within the same run).

Lifetime: the store is scoped to one prompt. The first access during a new prompt drops every
value held from the previous one, so large tensors are not pinned in VRAM/RAM for the life of
the process. Set -> Get inside one run keeps working; a value does not survive into a later
prompt (use the wired link, which ComfyUI caches, instead). Versions stay monotonic so a Get's
IS_CHANGED never repeats a key.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from ._comfy import current_prompt_id
from ._types import ANY, CATEGORY_UTILS, InputTypes

PLACEHOLDER = "select a key..."
COLORS: tuple[str, ...] = (
    "Default", "Void", "Neon", "Plasma", "Toxic", "Flare", "Blood", "Quantum",
    "Gold", "Abyss", "Ghost", "Rose", "Matrix", "Nebula",
)
LINK_INPUT = "set_link"


@dataclass(frozen=True)
class StoreEntry:
    value: object
    color: str
    node_id: str | None


class SetGetStore:
    """Thread-safe key -> value store, cleared when a new prompt starts using it."""

    def __init__(self, scope: Callable[[], str | None] = current_prompt_id) -> None:
        self._scope = scope
        self._scope_id: str | None = None
        self._lock = threading.Lock()
        self._entries: dict[str, StoreEntry] = {}
        self._versions: dict[str, int] = {}

    def _sync(self) -> None:
        """Drop everything held from an earlier prompt. Caller holds the lock."""
        sid = self._scope()
        if sid != self._scope_id:
            self._entries.clear()
            self._scope_id = sid

    def set(self, key: str, value: object, color: str = "Default", node_id: str | None = None) -> None:
        with self._lock:
            self._sync()
            self._entries[key] = StoreEntry(value, color, node_id)
            self._versions[key] = self._versions.get(key, 0) + 1

    def version(self, key: str) -> int:
        """How many times `key` was written; 0 when never set."""
        with self._lock:
            return self._versions.get(key, 0)

    def get(self, key: str) -> object:
        with self._lock:
            self._sync()
            if key == PLACEHOLDER or key not in self._entries:
                raise KeyError(
                    f"Get: key '{key}' was not found or not selected. "
                    "Run the matching Set node first, or pick a key."
                )
            return self._entries[key].value

    def entry(self, key: str) -> StoreEntry | None:
        with self._lock:
            self._sync()
            return self._entries.get(key)

    def keys(self) -> list[str]:
        with self._lock:
            self._sync()
            return list(self._entries)


STORE = SetGetStore()


class JWTFSet:
    CATEGORY = CATEGORY_UTILS
    RETURN_TYPES = (ANY,)
    RETURN_NAMES = ("pass_through",)
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {
                "key": ("STRING", {"default": "lora", "multiline": False}),
                "value": (ANY, {}),
                "color": (list(COLORS), {"default": "Default"}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    def run(self, key: str, value: object, color: str = "Default", unique_id: str | None = None) -> tuple[object]:
        STORE.set(key, value, color, None if unique_id is None else str(unique_id))
        return (value,)


class JWTFGet:
    CATEGORY = CATEGORY_UTILS
    RETURN_TYPES = (ANY,)
    RETURN_NAMES = ("value",)
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {"key": ([PLACEHOLDER],)},
            # Injected by the frontend at prompt time; the socket is hidden in the UI.
            "optional": {LINK_INPUT: (ANY, {"forceInput": True})},
        }

    @classmethod
    def VALIDATE_INPUTS(cls, key: str) -> bool:
        # The real key list lives in the frontend; accept any key here.
        return True

    @classmethod
    def IS_CHANGED(cls, key: str, **_: object) -> str:
        # Without a wired set_link the value comes from the global store, so a re-run of the
        # Set (new version) must invalidate this Get's cached output.
        return f"{key}:{STORE.version(key)}"

    def run(self, key: str, **linked: object) -> tuple[object]:
        if LINK_INPUT in linked:
            return (linked[LINK_INPUT],)
        return (STORE.get(key),)


NODE_CLASS_MAPPINGS = {"JWTFSet": JWTFSet, "JWTFGet": JWTFGet}
NODE_DISPLAY_NAME_MAPPINGS = {"JWTFSet": "Set (Remote)", "JWTFGet": "Get (Remote)"}
