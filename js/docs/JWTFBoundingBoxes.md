# Bounding Boxes

Draw layout boxes on a canvas, or let an LLM draw them.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `width` | Width in pixels. (default: 1024) | INT | Yes | 64 to 16384 (step 16) |
| `height` | Height in pixels. (default: 1024) | INT | Yes | 64 to 16384 (step 16) |
| `background` | Background. | IMAGE | No |  |
| `bboxes` | Bboxes. | BOUNDING_BOX,ARRAY,STRING | No |  |
| `editor_state` | Editor state. | STRING | No |  |
| `last_incoming` | Last incoming. | STRING | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `preview` | Preview. | IMAGE |
| `bboxes` | Bboxes. | BOUNDING_BOX |
| `elements` | Elements. | ARRAY |

Notes:

- More detail, including how this node fits with the others, is in the **Bounding Boxes and Layout LLM Prompt** page of the JezzWTF Documentation window (Alt+Shift+D).
