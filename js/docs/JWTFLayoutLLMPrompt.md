# Layout LLM Prompt

Draw layout boxes on a canvas, or let an LLM draw them.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `scene` | Scene description passed to the language model as the layout request. | STRING | Yes |  |
| `width` | Target canvas width in pixels included in the layout instructions. (default: 1024) | INT | Yes | 16 to 16384 (step 16) |
| `height` | Target canvas height in pixels included in the layout instructions. (default: 1024) | INT | Yes | 16 to 16384 (step 16) |
| `max_boxes` | Maximum number of boxes requested in the generated layout. (default: 5) | INT | Yes | 1 to 16 |
| `extra_rules` | Optional instructions appended to the generated system prompt. | STRING | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `system_prompt` | System instructions defining the canvas, box limit and required layout JSON format. | STRING |
| `prompt` | User prompt asking the model to lay out the supplied scene. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Bounding Boxes and Layout LLM Prompt** page of the JezzWTF Documentation window (Alt+Shift+D).
