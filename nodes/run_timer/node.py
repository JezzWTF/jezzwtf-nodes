"""The Run Timer node: a small display of the current and last run.

Every run is timed by the browser (see js/run_timer) from ComfyUI execution events, node or no node; this node
only shows the stopwatch, can label its runs, and tells the server when it executed.
"""
from __future__ import annotations

from comfy_api.latest import io

from .live import LIVE
from .store import now_ms

try:
    from ..utility_core._comfy import current_prompt_id
except ImportError:  # imported as a top-level package (tests)
    from utility_core._comfy import current_prompt_id  # type: ignore[no-redef]


class JWTFRunTimer(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFRunTimer",
            display_name='Run Timer',
            category='JezzWTF/utils',
            description="A display of the current and last run time. Every run is timed whether or not this node is on the canvas; renaming it labels its runs.",
            inputs=[
                io.String.Input("label", default='', multiline=False, optional=True, tooltip="Label under which this node files its runs, populated from the node title by the frontend."),
            ],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, label: str = "") -> io.NodeOutput:
        LIVE.mark(current_prompt_id(), label if isinstance(label, str) else "", now_ms())
        return io.NodeOutput()


NODES = [JWTFRunTimer]
