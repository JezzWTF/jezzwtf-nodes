"""Layout LLM prompt builder (spec section 3)."""

from __future__ import annotations

from comfy_api.latest import io


DEFAULT_SCENE = (
    "A retro travel poster for a seaside town: a red lighthouse on a cliff at the right, "
    "a small sailboat on the sea at the lower left, and the title \"VISIT PORT HAVEN\" "
    "in bold cream letters across the top."
)


def shape_label(width: int, height: int) -> str:
    if width > 1.15 * height:
        return "landscape"
    if height > 1.15 * width:
        return "portrait"
    return "roughly square"


def build_system_prompt(width: int, height: int, max_boxes: int, extra_rules: str = "") -> str:
    shape = shape_label(width, height)
    ux = f"{width / 1000:.2f}"
    uy = f"{height / 1000:.2f}"
    rules = [
        f"Use at most {max_boxes} boxes.",
        "Give every distinct subject its own box, and every separate piece of text its own box.",
        "Do not add a box for the background unless the scene explicitly asks for one.",
        "Map positional words to coordinates: left/top mean small values, right/bottom mean large values, "
        "centre means around 500.",
        "Keep boxes tight around their subject and fully inside the 0-1000 grid.",
        "Text boxes are wide and short, sized to the lettering they hold.",
        "Only let boxes overlap where one thing really occludes another.",
        "List background items first and foreground items last.",
        "Answer with the bare JSON array only: no markdown, no code fences, no commentary.",
    ]
    extra = (extra_rules or "").strip()
    if extra:
        rules.append(extra)
    lines = [
        "You plan image layouts for a text-to-image model.",
        "",
        f"The canvas is {width}x{height} pixels ({shape}).",
        "All coordinates are integers on a 0-1000 grid on both axes: 0 is the top or left edge, "
        "1000 is the bottom or right edge, and 500 is the middle.",
        f"One grid unit is {ux} px horizontally and {uy} px vertically.",
        "",
        "Return a JSON array. Each box is an object with these keys:",
        '- "type": "obj" for a visual subject, or "text" for rendered lettering.',
        '- "bbox": [ymin, xmin, ymax, xmax] on the 0-1000 grid, with ymin < ymax and xmin < xmax.',
        '- "text": the exact words to render, keeping the capitalisation of the request (text boxes only).',
        '- "desc": a short visual description; for text boxes, the lettering style, colour and size.',
        "",
        "Rules:",
        *[f"- {r}" for r in rules],
        "",
        'Example for "a cat on a sofa under the headline HELLO":',
        '[{"type": "text", "bbox": [60, 200, 200, 800], "text": "HELLO", "desc": "bold white sans-serif headline"},'
        ' {"type": "obj", "bbox": [420, 250, 900, 750], "desc": "a ginger cat curled up on a green sofa"}]',
    ]
    return "\n".join(lines).strip() + "\n"


def build_user_prompt(scene: str) -> str:
    return f"Scene description:\n{(scene or '').strip()}\n\nReturn the JSON array now."


class JWTFLayoutLLMPrompt(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFLayoutLLMPrompt",
            display_name='Layout LLM Prompt',
            category='JezzWTF/LLM',
            inputs=[
                io.String.Input("scene", default='A retro travel poster for a seaside town: a red lighthouse on a cliff at the right, a small sailboat on the sea at the lower left, and the title "VISIT PORT HAVEN" in bold cream letters across the top.', multiline=True, tooltip="Scene description passed to the language model as the layout request."),
                io.Int.Input("width", default=1024, min=16, max=16384, step=16, tooltip="Target canvas width in pixels included in the layout instructions."),
                io.Int.Input("height", default=1024, min=16, max=16384, step=16, tooltip="Target canvas height in pixels included in the layout instructions."),
                io.Int.Input("max_boxes", default=5, min=1, max=16, tooltip="Maximum number of boxes requested in the generated layout."),
                io.String.Input("extra_rules", default='', multiline=True, optional=True, tooltip="Optional instructions appended to the generated system prompt."),
            ],
            outputs=[
                io.String.Output("system_prompt", tooltip="System instructions defining the canvas, box limit and required layout JSON format."),
                io.String.Output("prompt", tooltip="User prompt asking the model to lay out the supplied scene."),
            ],
        )

    @classmethod
    def execute(cls, scene: str, width: int, height: int, max_boxes: int, extra_rules: str = "") -> io.NodeOutput:
        return io.NodeOutput(build_system_prompt(int(width), int(height), int(max_boxes), extra_rules), build_user_prompt(scene))


NODES = [JWTFLayoutLLMPrompt]
