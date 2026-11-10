"""Model Preview Mirror: a pass-through that shows a sampler's live preview in its own panel.

The samplers in this pack (and KJNodes' Model Preview Override) attach an OUTER_SAMPLE wrapper to the model and send
each preview frame over the `kj_preview_override` websocket event. This node tells its panel which sampler to follow,
by reading the node id off that wrapper; with no wrapper on the connected model the panel follows any preview.
"""
from __future__ import annotations

import logging

from comfy_api.latest import io

log = logging.getLogger("jezzwtf.utility_core.preview_mirror")

WRAPPER_KEY = "kj_preview_override"
UI_KEY = "jezzwtf_source_id"


def source_id(model: object) -> str | None:
    """The node id of the sampler whose preview wrapper is on `model`, or None when there is none."""
    getter = getattr(model, "get_wrappers", None)
    if not callable(getter):
        return None
    try:
        from comfy.patcher_extension import WrappersMP  # type: ignore[import-not-found]

        wrappers = getter(WrappersMP.OUTER_SAMPLE, WRAPPER_KEY)
    except Exception as exc:  # noqa: BLE001 - an unusual ModelPatcher must not fail the run
        log.debug("could not read the preview wrapper: %s", exc)
        return None
    node_id = getattr(wrappers[-1], "node_id", None) if wrappers else None
    return str(node_id) if node_id not in (None, "") else None


class JWTFModelPreviewMirror(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFModelPreviewMirror",
            display_name="Model Preview Mirror",
            category="JezzWTF/sampling",
            description="Pass a value through and show a sampler's live preview beside it. Connect the model the sampler uses to follow that sampler, or leave it unconnected to follow any preview.",
            inputs=[
                io.AnyType.Input("any", optional=True, tooltip="Optional. A MODEL that has a JezzWTF or KJNodes sampler preview attached makes the panel follow that sampler; any value passes straight through."),
            ],
            outputs=[io.AnyType.Output("any", tooltip="The input value, unchanged.")],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, any: object = None) -> io.NodeOutput:  # noqa: A002 - the input is named "any"
        source = source_id(any) if any is not None else None
        return io.NodeOutput(any, ui={UI_KEY: [source] if source else []})


NODES = [JWTFModelPreviewMirror]
