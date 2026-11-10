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
                io.Boolean.Input("switch", default=False, label_on='true', label_off='false', tooltip='Selects the true inputs when enabled and the false inputs when disabled, routing each slot to its corresponding output.'),
            ],
            accept_all_inputs=True,  # the front end adds true_N / false_N inputs on the fly
            outputs=[
                io.AnyType.Output("output_1", tooltip="Passes through true_1 when the switch is true or false_1 when it is false, returning no value if that input is disconnected."),
                io.AnyType.Output("output_2", tooltip="Passes through true_2 when the switch is true or false_2 when it is false, returning no value if that input is disconnected."),
                io.AnyType.Output("output_3", tooltip="Passes through true_3 when the switch is true or false_3 when it is false, returning no value if that input is disconnected."),
                io.AnyType.Output("output_4", tooltip="Passes through true_4 when the switch is true or false_4 when it is false, returning no value if that input is disconnected."),
                io.AnyType.Output("output_5", tooltip="Passes through true_5 when the switch is true or false_5 when it is false, returning no value if that input is disconnected."),
                io.AnyType.Output("output_6", tooltip="Passes through true_6 when the switch is true or false_6 when it is false, returning no value if that input is disconnected."),
            ],
        )

    @classmethod
    def execute(cls, switch: bool, **kwargs: object) -> io.NodeOutput:
        side = "true" if switch else "false"
        return io.NodeOutput(*(kwargs.get(f"{side}_{i}") for i in range(1, MAX_SLOTS + 1)))


NODES = [MultiSwitch]
