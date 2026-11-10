# H3 Upscale Picker

Same-scale target size on a 16-px grid for the MiniMax H3 latent upscaler.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `width` | Source width in pixels. (default: 640) | INT | Yes | 1 to 16384 |
| `height` | Source height in pixels. (default: 352) | INT | Yes | 1 to 16384 |
| `mode` | Chooses whether to calculate output dimensions from a scale factor or a target pixel area. (default: `Scale factor`) | COMBO | Yes | `"Scale factor"`<br>`"Target megapixels"` |
| `scale` | Preset upscale factor, with Custom using the numeric scale. (default: `2x`) | COMBO | Yes | choose from the list |
| `custom_scale` | Upscale factor used when the scale choice is Custom. (default: 2.0) | FLOAT | Yes | 1 to 4 (step 0.01) |
| `target_megapixels` | Target image area in units of 1,048,576 pixels, with the requested scale clamped between 1x and 4x. (default: 0.5) | FLOAT | Yes | 0.05 to 16 (step 0.05) |
| `multiple` | Output pixel grid size, rounded up to a multiple of 16. (default: 16) | INT | Yes | 16 to 256 (step 16) |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `width` | Selected output width in pixels on the requested grid. | INT |
| `height` | Selected output height in pixels on the requested grid. | INT |
| `scale` | Mean of the horizontal and vertical scale factors after choosing the output dimensions. | FLOAT |
| `info` | Summary of the chosen dimensions, per-axis scales, pixel area and any scale clamping. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **H3 Image Edit, samplers and upscale** page of the JezzWTF Documentation window (Alt+Shift+D).
