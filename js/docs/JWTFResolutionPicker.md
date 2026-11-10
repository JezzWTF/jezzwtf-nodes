# Resolution Picker

Aspect ratio and megapixels (or a preset) to width, height and an empty latent.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `mode` | Chooses between an aspect ratio with a pixel budget and a named resolution preset. (default: `Ratio + Megapixels`) | COMBO | Yes | `"Ratio + Megapixels"`<br>`"Preset Resolution"` |
| `aspect_ratio` | Aspect ratio used with the megapixel target, including a Custom option for entering both ratio components. (default: `16:9 (Widescreen)`) | COMBO | Yes | choose from the list |
| `custom_ratio_w` | Horizontal component of the aspect ratio when Custom is selected. (default: 16.0) | FLOAT | Yes | 0.1 to 100 (step 0.01) |
| `custom_ratio_h` | Vertical component of the aspect ratio when Custom is selected. (default: 9.0) | FLOAT | Yes | 0.1 to 100 (step 0.01) |
| `megapixels` | Target image area in millions of pixels before dimensions are snapped. (default: 1.0) | FLOAT | Yes | 0.05 to 16 (step 0.05) |
| `preset_resolution` | Named pixel dimensions used in preset mode. (default: `1280x720 (HD 720p)`) | COMBO | Yes | choose from the list |
| `snap_presets` | Rounds preset dimensions to the chosen pixel multiple when enabled. (default: true) | BOOLEAN | Yes |  |
| `multiple` | Pixel multiple used to snap calculated dimensions and optionally presets. (default: 32) | INT | Yes | 1 to 256 |
| `swap_orientation` | Exchanges the final width and height. (default: false) | BOOLEAN | Yes |  |
| `batch_size` | Number of blank samples in the latent batch. (default: 1) | INT | Yes | 1 to 4096 |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `width` | Selected image width in pixels after snapping and orientation. | INT |
| `height` | Selected image height in pixels after snapping and orientation. | INT |
| `latent` | Zero-filled four-channel latent batch at one-eighth the selected pixel dimensions. | LATENT |

Notes:

- More detail, including how this node fits with the others, is in the **Duration to Frames and Resolution Picker** page of the JezzWTF Documentation window (Alt+Shift+D).
