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

from comfy_api.latest import io

from ._comfy import current_prompt_id

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


class JWTFSet(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFSet",
            display_name='Set (Remote)',
            category='JezzWTF/utils',
            inputs=[
                io.String.Input("key", default='lora', multiline=False, tooltip="Name under which the value is stored and matched by Get nodes."),
                io.AnyType.Input("value", tooltip="Data from any socket type to store under the chosen key."),
                io.Combo.Input("color", options=['Default', 'Void', 'Neon', 'Plasma', 'Toxic', 'Flare', 'Blood', 'Quantum', 'Gold', 'Abyss', 'Ghost', 'Rose', 'Matrix', 'Nebula'], default='Default', tooltip="Canvas colour theme associated with the named value."),
            ],
            outputs=[
                io.AnyType.Output("pass_through", tooltip="The same value that was stored under the chosen key."),
            ],
            hidden=[io.Hidden.unique_id],
        )

    @classmethod
    def execute(cls, key: str, value: object, color: str = "Default") -> io.NodeOutput:
        unique_id = cls.hidden.unique_id
        STORE.set(key, value, color, None if unique_id is None else str(unique_id))
        return io.NodeOutput(value)


class JWTFGet(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFGet",
            display_name='Get (Remote)',
            category='JezzWTF/utils',
            inputs=[
                io.Combo.Input("key", options=['select a key...'], tooltip="Name of the Set node value to retrieve, populated by the frontend."),
                io.AnyType.Input("set_link", optional=True, extra_dict={'forceInput': True}, tooltip="Optional link supplied by the frontend to use the matching Set node's current output directly."),
            ],
            outputs=[
                io.AnyType.Output("value", tooltip="Value from the linked Set output or the named store entry when no link is present."),
            ],
        )

    @classmethod
    def validate_inputs(cls, key: str) -> bool:
        # The real key list lives in the frontend; accept any key here.
        return True

    @classmethod
    def fingerprint_inputs(cls, key: str, **_: object) -> str:
        # Without a wired set_link the value comes from the global store, so a re-run of the
        # Set (new version) must invalidate this Get's cached output.
        return f"{key}:{STORE.version(key)}"

    @classmethod
    def execute(cls, key: str, **linked: object) -> io.NodeOutput:
        if LINK_INPUT in linked:
            return io.NodeOutput(linked[LINK_INPUT])
        return io.NodeOutput(STORE.get(key))


NODES = [JWTFSet, JWTFGet]
