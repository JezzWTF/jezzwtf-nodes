# Resolution Picker

Aspect ratio and megapixels (or a preset) to width, height and an empty latent.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `mode` | Mode. (default: `Ratio + Megapixels`) | COMBO | Yes | `"Ratio + Megapixels"`<br>`"Preset Resolution"` |
| `aspect_ratio` | Aspect ratio. (default: `16:9 (Widescreen)`) | COMBO | Yes | choose from the list |
| `custom_ratio_w` | Custom ratio w. (default: 16.0) | FLOAT | Yes | 0.1 to 100 (step 0.01) |
| `custom_ratio_h` | Custom ratio h. (default: 9.0) | FLOAT | Yes | 0.1 to 100 (step 0.01) |
| `megapixels` | Megapixels. (default: 1.0) | FLOAT | Yes | 0.05 to 16 (step 0.05) |
| `preset_resolution` | Preset resolution. (default: `1280x720 (HD 720p)`) | COMBO | Yes | choose from the list |
| `snap_presets` | Snap presets. (default: true) | BOOLEAN | Yes |  |
| `multiple` | Multiple. (default: 32) | INT | Yes | 1 to 256 |
| `swap_orientation` | Swap orientation. (default: false) | BOOLEAN | Yes |  |
| `batch_size` | Batch size. (default: 1) | INT | Yes | 1 to 4096 |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `width` | Width in pixels. | INT |
| `height` | Height in pixels. | INT |
| `latent` | Latent. | LATENT |

Notes:

- More detail, including how this node fits with the others, is in the **Duration to Frames and Resolution Picker** page of the JezzWTF Documentation window (Alt+Shift+D).
