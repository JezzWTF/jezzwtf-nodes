from __future__ import annotations

from comfy_api.latest import io

MAX_SLOTS = 6


class MultiSwitch(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MultiSwitch",
            display_name='Multi Switch',
            category='JezzWTF/utils',
            inputs=[
                io.Boolean.Input("switch", default=False, label_on='true', label_off='false', tooltip='Option A → false_N inputs pass through.  Option B → true_N inputs pass through.'),
            ],
            accept_all_inputs=True,  # the front end adds true_N / false_N inputs on the fly
            outputs=[
                io.AnyType.Output("output_1"),
                io.AnyType.Output("output_2"),
                io.AnyType.Output("output_3"),
                io.AnyType.Output("output_4"),
                io.AnyType.Output("output_5"),
                io.AnyType.Output("output_6"),
            ],
        )

    @classmethod
    def execute(cls, switch: bool, **kwargs: object) -> io.NodeOutput:
        side = "true" if switch else "false"
        return io.NodeOutput(*(kwargs.get(f"{side}_{i}") for i in range(1, MAX_SLOTS + 1)))


NODES = [MultiSwitch]
