# Bounding Boxes

Draw layout boxes on a canvas, or let an LLM draw them.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `width` | Layout width in pixels, used for the preview and pixel box coordinates. (default: 1024) | INT | Yes | 64 to 16384 (step 16) |
| `height` | Layout height in pixels, used for the preview and pixel box coordinates. (default: 1024) | INT | Yes | 64 to 16384 (step 16) |
| `background` | Optional image whose first frame is drawn beneath the boxes in the preview. | IMAGE | No |  |
| `bboxes` | Box data from another node or JSON text, imported when it differs from the editor's last import. | BOUNDING_BOX,ARRAY,STRING | No |  |
| `editor_state` | JSON region data written by the bounding-box editor and used when there is no new import. | STRING | No |  |
| `last_incoming` | Key of the most recently imported boxes, recorded by the editor to preserve local edits across runs. | STRING | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `preview` | Rendered layout with its boxes and optional background. | IMAGE |
| `bboxes` | Boxes grouped in one frame as pixel x, y, width and height values, or an empty list when there are no boxes. | BOUNDING_BOX |
| `elements` | Layout elements with type, description and 0-to-1000 corner coordinates, plus text and colour palette where applicable. | ARRAY |

Notes:

- More detail, including how this node fits with the others, is in the **Bounding Boxes and Layout LLM Prompt** page of the JezzWTF Documentation window (Alt+Shift+D).
