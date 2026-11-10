"""Multi Switch: up to six independent true/false pairs behind one switch; output N is the chosen side of pair N."""
from __future__ import annotations

from comfy_api.latest import io

MAX_SLOTS = 6
SLOTS = range(1, MAX_SLOTS + 1)


def chosen_side(switch: bool) -> str:
    return "true" if switch else "false"


class MultiSwitch(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        templates = {i: io.MatchType.Template(f"slot{i}") for i in SLOTS}
        inputs: list[io.Input] = [
            io.Boolean.Input("switch", default=False, label_on="true", label_off="false", tooltip="false passes every pair's false input through, true passes every pair's true input. Can also be wired in from another node."),
        ]
        for i in SLOTS:
            inputs.append(io.MatchType.Input(f"false_{i}", template=templates[i], display_name="false", optional=True, lazy=True, tooltip=f"Pair {i}: passed to output {i} while the switch is false."))
            inputs.append(io.MatchType.Input(f"true_{i}", template=templates[i], display_name="true", optional=True, lazy=True, tooltip=f"Pair {i}: passed to output {i} while the switch is true."))
        return io.Schema(
            node_id="MultiSwitch",
            display_name="Multi Switch",
            category="JezzWTF/utils",
            description="Switch several values at once: each true/false pair feeds its own output, and one switch flips them all. Only the chosen side of each pair is computed.",
            inputs=inputs,
            outputs=[io.MatchType.Output(template=templates[i], id=f"output_{i}", display_name=f"output {i}", tooltip=f"The chosen side of pair {i}; it has the type of what is connected.") for i in SLOTS],
        )

    @classmethod
    def check_lazy_status(cls, switch: bool = False, **inputs: object) -> list[str]:
        side = chosen_side(switch)
        return [f"{side}_{i}" for i in SLOTS if f"{side}_{i}" in inputs and inputs[f"{side}_{i}"] is None]

    @classmethod
    def execute(cls, switch: bool = False, **inputs: object) -> io.NodeOutput:
        side = chosen_side(switch)
        return io.NodeOutput(*(inputs.get(f"{side}_{i}") for i in SLOTS))


NODES = [MultiSwitch]
