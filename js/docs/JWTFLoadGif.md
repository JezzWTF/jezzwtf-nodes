# Load GIF

GIF to IMAGE frames, mask, fps and frame delays.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `gif` | GIF selected from ComfyUI's input folder, unless an explicit path is supplied. | COMBO | Yes | choose from the list |
| `path` | Optional GIF path (input, output or temp). Overrides the picker. | STRING | No |  |
| `max_frames` | 0 = all frames. (default: 0) | INT | No | 0 to 10000 |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `images` | Decoded RGB frames in playback order, up to the requested frame limit. | IMAGE |
| `mask` | Per-frame inverse alpha, with white marking transparent pixels. | MASK |
| `fps` | Average frames per second calculated from the returned frame delays. | FLOAT |
| `frame_count` | Number of frames returned after applying the frame limit. | INT |
| `delays_ms` | JSON array of the returned frames' delays in milliseconds. | STRING |
| `gif_path` | Absolute path of the loaded GIF. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **GIF Tools** page of the JezzWTF Documentation window (Alt+Shift+D).
