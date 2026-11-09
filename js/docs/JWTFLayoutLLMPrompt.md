# Layout LLM Prompt

Draw layout boxes on a canvas, or let an LLM draw them.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `scene` | Scene. | STRING | Yes |  |
| `width` | Width in pixels. (default: 1024) | INT | Yes | 16 to 16384 (step 16) |
| `height` | Height in pixels. (default: 1024) | INT | Yes | 16 to 16384 (step 16) |
| `max_boxes` | Max boxes. (default: 5) | INT | Yes | 1 to 16 |
| `extra_rules` | Extra rules. | STRING | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `system_prompt` | System prompt. | STRING |
| `prompt` | The text prompt. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Bounding Boxes and Layout LLM Prompt** page of the JezzWTF Documentation window (Alt+Shift+D).
