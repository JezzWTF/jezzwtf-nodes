# Draw Image

Layered sketch pad that loads like Load Image, with pressure, undo and zoom.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `width` | Width in pixels. (default: 1024) | INT | Yes | 64 to 8192 (step 8) |
| `height` | Height in pixels. (default: 1024) | INT | Yes | 64 to 8192 (step 8) |
| `background` | Background. (default: `white`) | COMBO | Yes | `"white"`<br>`"black"`<br>`"transparent"` |
| `image` | The input image. | STRING | Yes |  |
| `drawing_state` | Drawing state. | STRING | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `image` | The input image. | IMAGE |
| `mask` | The mask. | MASK |

Notes:

- More detail, including how this node fits with the others, is in the **Where files are saved** page of the JezzWTF Documentation window (Alt+Shift+D).
