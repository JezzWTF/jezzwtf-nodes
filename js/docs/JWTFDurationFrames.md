# Duration to Frames

Seconds to frame count, with model presets and a safe expression field.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `duration` | Duration. (default: 6.0) | FLOAT | Yes | 0 to 3600 (step 0.1) |
| `preset` | Preset. (default: `MiniMax H3 (24 FPS)`) | COMBO | Yes | `"MiniMax H3 (24 FPS)"`<br>`"24 FPS"`<br>`"30 FPS"`<br>`"Custom"` |
| `expression` | Expression. | STRING | Yes |  |
| `fps` | Frames per second. (default: 24) | INT | Yes | 1 to 240 |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `frames` | Frames. | INT |
| `seconds` | Seconds. | FLOAT |
| `fps` | Frames per second. | FLOAT |
| `fps_int` | Fps int. | INT |

Notes:

- More detail, including how this node fits with the others, is in the **Duration to Frames and Resolution Picker** page of the JezzWTF Documentation window (Alt+Shift+D).
