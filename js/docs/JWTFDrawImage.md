# Draw Image

Layered sketch pad that loads like Load Image, with pressure, undo and zoom.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `width` | Canvas width in pixels when there is no saved drawing. (default: 1024) | INT | Yes | 64 to 8192 (step 8) |
| `height` | Canvas height in pixels when there is no saved drawing. (default: 1024) | INT | Yes | 64 to 8192 (step 8) |
| `background` | Canvas background colour, with transparent mode also premultiplying the saved drawing's RGB by its alpha. (default: `white`) | COMBO | Yes | `"white"`<br>`"black"`<br>`"transparent"` |
| `image` | Path under ComfyUI's input folder written by the drawing editor when it saves the rendered canvas. | STRING | Yes |  |
| `drawing_state` | Serialized editable canvas state written by the drawing editor to restore the drawing in the workflow. | STRING | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `image` | RGB pixels of the saved drawing or of a blank canvas at the requested dimensions. | IMAGE |
| `mask` | Inverse alpha of the drawing, with white marking transparent pixels. | MASK |

Notes:

- More detail, including how this node fits with the others, is in the **Where files are saved** page of the JezzWTF Documentation window (Alt+Shift+D).
