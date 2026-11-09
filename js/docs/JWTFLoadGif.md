# Load GIF

GIF to IMAGE frames, mask, fps and frame delays.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `gif` | Gif. | COMBO | Yes | choose from the list |
| `path` | Optional GIF path (input, output or temp). Overrides the picker. | STRING | No |  |
| `max_frames` | 0 = all frames. (default: 0) | INT | No | 0 to 10000 |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `images` | The input images (an image batch). | IMAGE |
| `mask` | The mask. | MASK |
| `fps` | Frames per second. | FLOAT |
| `frame_count` | Frame count. | INT |
| `delays_ms` | Delays ms. | STRING |
| `gif_path` | Gif path. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **GIF Tools** page of the JezzWTF Documentation window (Alt+Shift+D).
