"""`JWTFLoraInspector`: hash a LoRA, look it up on Civitai, show it on the node."""
from __future__ import annotations

import os
import time

from comfy_api.latest import io

from ._comfy import PACK_DIR, log, lora_full_path, lora_names, send_sync, user_cache_dir
from .inspector_logic import InspectorCache, JSONDict, inspect_lora, node_outputs, resolve_api_key

EVENT_PROGRESS = "jezzwtf.lora_inspector.progress"
EVENT_METADATA = "jezzwtf.lora_inspector.metadata"
EVENT_ERROR = "jezzwtf.lora_inspector.error"

_cache: InspectorCache | None = None


def get_cache() -> InspectorCache:
    global _cache
    if _cache is None:
        _cache = InspectorCache(os.path.join(user_cache_dir(), "lora_inspector_cache.json"))
    return _cache


def key_files() -> list[str]:
    return [os.path.join(user_cache_dir(), "civitai_api_key.txt"), os.path.join(PACK_DIR, "civitai_api_key.txt")]


def run_inspection(lora: str, source: str, node: str, force: bool, sid: str | None = None) -> JSONDict:
    """Shared by the node and the HTTP route; emits websocket progress tagged with `node`, to
    client `sid` when the caller knows it. The API key comes from the environment or a key file."""

    def progress(stage: str, value: float, message: str) -> None:
        send_sync(EVENT_PROGRESS, {"node": node, "stage": stage, "value": value, "message": message}, sid)

    try:
        path = lora_full_path(lora)
        if not path:
            raise FileNotFoundError(f"LoRA not found: {lora}")
        key = resolve_api_key(None, os.environ, key_files())
        payload = inspect_lora(path, lora, source, key, force, get_cache(), progress)
    except Exception as exc:
        send_sync(EVENT_ERROR, {"node": node, "message": str(exc)}, sid)
        raise
    send_sync(EVENT_METADATA, {"node": node, "payload": payload}, sid)
    progress("done", 1.0, "done")
    return payload


class JWTFLoraInspector(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFLoraInspector",
            display_name='LoRA Inspector',
            category='JezzWTF/lora',
            description='Identify a LoRA by SHA-256 on Civitai and show base model, trigger words and samples.',
            inputs=[
                io.Combo.Input("lora_name", options=lora_names()),
                io.Combo.Input("source", options=['auto', 'civitai.com', 'red.civitai.com'], default='auto', optional=True),
                io.Combo.Input("refresh", options=['use cache', 'force refresh'], default='use cache', optional=True),
            ],
            outputs=[
                io.String.Output("model_name"),
                io.String.Output("base_model"),
                io.String.Output("trigger_words"),
                io.String.Output("metadata_json"),
            ],
            hidden=[io.Hidden.unique_id],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, lora_name: str = "", source: str = "auto", refresh: str = "use cache", **_: object) -> str:
        if refresh == "force refresh":
            return str(time.time())
        return f"{lora_name}|{source}"

    @classmethod
    def execute(cls, lora_name: str, source: str = "auto", refresh: str = "use cache") -> io.NodeOutput:
        unique_id = cls.hidden.unique_id
        node = str(unique_id) if unique_id is not None else "0"
        payload = run_inspection(lora_name, source, node, refresh == "force refresh")
        if payload.get("warning"):
            log.warning("LoRA Inspector: %s", payload["warning"])
        return io.NodeOutput(*node_outputs(payload, lora_name))


NODES = [JWTFLoraInspector]
