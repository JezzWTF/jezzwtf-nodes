# Duration to Frames

Seconds to frame count, with model presets and a safe expression field.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `duration` | Requested clip length in seconds, available as a in the frame-count expression. (default: 6.0) | FLOAT | Yes | 0 to 3600 (step 0.1) |
| `preset` | Selects a built-in frame rate and formula or uses the editable values in Custom mode. (default: `MiniMax H3 (24 FPS)`) | COMBO | Yes | `"MiniMax H3 (24 FPS)"`<br>`"24 FPS"`<br>`"30 FPS"`<br>`"Custom"` |
| `expression` | Custom formula evaluated with a as seconds and fps as the frame rate, with the result rounded and clamped to at least one frame. | STRING | Yes |  |
| `fps` | Frame rate in frames per second used in Custom mode. (default: 24) | INT | Yes | 1 to 240 |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `frames` | Integer frame count calculated from the selected formula. | INT |
| `seconds` | Actual duration in seconds after frame-count rounding, calculated as frames divided by the selected rate. | FLOAT |
| `fps` | Effective frames per second as a floating-point value. | FLOAT |
| `fps_int` | Effective frames per second as an integer. | INT |

Notes:

- More detail, including how this node fits with the others, is in the **Duration to Frames and Resolution Picker** page of the JezzWTF Documentation window (Alt+Shift+D).
