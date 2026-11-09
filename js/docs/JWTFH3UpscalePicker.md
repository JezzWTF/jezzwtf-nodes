# H3 Upscale Picker

Same-scale target size on a 16-px grid for the MiniMax H3 latent upscaler.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `width` | Width in pixels. (default: 640) | INT | Yes | 1 to 16384 |
| `height` | Height in pixels. (default: 352) | INT | Yes | 1 to 16384 |
| `mode` | Mode. (default: `Scale factor`) | COMBO | Yes | `"Scale factor"`<br>`"Target megapixels"` |
| `scale` | Scale. (default: `2x`) | COMBO | Yes | choose from the list |
| `custom_scale` | Custom scale. (default: 2.0) | FLOAT | Yes | 1 to 4 (step 0.01) |
| `target_megapixels` | Target megapixels. (default: 0.5) | FLOAT | Yes | 0.05 to 16 (step 0.05) |
| `multiple` | Multiple. (default: 16) | INT | Yes | 16 to 256 (step 16) |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `width` | Width in pixels. | INT |
| `height` | Height in pixels. | INT |
| `scale` | Scale. | FLOAT |
| `info` | Info. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **H3 Image Edit, samplers and upscale** page of the JezzWTF Documentation window (Alt+Shift+D).
