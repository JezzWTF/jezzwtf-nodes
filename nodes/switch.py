"""Switch and Route: choose between two inputs, or send one input to one of two outputs, with a true/false switch."""
from __future__ import annotations

from comfy_api.latest import io

# Unconnected optional inputs are simply absent from execute(); a connected input that has not been computed yet
# arrives as None. check_lazy_status() asks for the chosen side only, so the other side's upstream nodes never run.
MISSING = object()


class JWTFSwitch(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        template = io.MatchType.Template("switch")
        return io.Schema(
            node_id="JWTFSwitch",
            display_name="Switch",
            category="JezzWTF/utils",
            description="Pick one of two inputs with a true/false switch. The output takes the type of what you connect, and only the chosen side is computed.",
            search_aliases=["if", "else", "branch", "select", "toggle", "choose"],
            inputs=[
                io.Boolean.Input("switch", default=False, label_on="true", label_off="false", tooltip="true passes the true input through, false passes the false input. Can also be wired in from another node."),
                io.MatchType.Input("if_true", template=template, display_name="true", optional=True, lazy=True, tooltip="Passed through when the switch is true. Not computed while the switch is false."),
                io.MatchType.Input("if_false", template=template, display_name="false", optional=True, lazy=True, tooltip="Passed through when the switch is false. Not computed while the switch is true."),
            ],
            outputs=[io.MatchType.Output(template=template, id="output", display_name="output", tooltip="The chosen input, unchanged; it has the same type as what is connected.")],
        )

    @classmethod
    def validate_inputs(cls, switch: bool = False, if_true: object = MISSING, if_false: object = MISSING) -> bool | str:
        if if_true is MISSING and if_false is MISSING:
            return "Switch: connect something to the true or the false input."
        return True

    @classmethod
    def check_lazy_status(cls, switch: bool = False, if_true: object = MISSING, if_false: object = MISSING) -> list[str]:
        if switch and if_true is None:
            return ["if_true"]
        if not switch and if_false is None:
            return ["if_false"]
        return []

    @classmethod
    def execute(cls, switch: bool = False, if_true: object = MISSING, if_false: object = MISSING) -> io.NodeOutput:
        chosen = if_true if switch else if_false
        if chosen is MISSING:
            side = "true" if switch else "false"
            raise ValueError(f"Switch: the switch is {side} but nothing is connected to its {side} input.")
        return io.NodeOutput(chosen)


class JWTFRoute(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        template = io.MatchType.Template("route")
        return io.Schema(
            node_id="JWTFRoute",
            display_name="Route",
            category="JezzWTF/utils",
            description="Send one input to either the true or the false output with a true/false switch. Whatever hangs off the other output is skipped for this run.",
            search_aliases=["split", "branch", "router", "divert", "direct"],
            inputs=[
                io.Boolean.Input("switch", default=False, label_on="true", label_off="false", tooltip="true sends the value out of the true output, false out of the false output. Can also be wired in from another node."),
                io.MatchType.Input("value", template=template, tooltip="The value to send on."),
            ],
            outputs=[
                io.MatchType.Output(template=template, id="if_true", display_name="true", tooltip="The value while the switch is true. While it is false, nodes connected here do not run."),
                io.MatchType.Output(template=template, id="if_false", display_name="false", tooltip="The value while the switch is false. While it is true, nodes connected here do not run."),
            ],
        )

    @classmethod
    def execute(cls, switch: bool, value: object) -> io.NodeOutput:
        from comfy_execution.graph_utils import ExecutionBlocker  # type: ignore[import-not-found]

        blocked = ExecutionBlocker(None)  # None: blocked silently, no error message
        return io.NodeOutput(value, blocked) if switch else io.NodeOutput(blocked, value)


NODES = [JWTFSwitch, JWTFRoute]
