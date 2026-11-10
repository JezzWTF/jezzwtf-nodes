# Get Image

Grab an in-graph image as IMAGE and MASK.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `image` | Source pixels to preview and use for mask extraction. | IMAGE | Yes |  |
| `invert_mask` | Flips black and white in the mask after any threshold is applied. (default: false) | BOOLEAN | No |  |
| `mask_threshold` | Binarises the mask by keeping values strictly above this cutoff, with 0 leaving the mask continuous. (default: 0.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `mask_mode` | Uses inverse alpha or inverse luminance, with a zero mask when the selected channel data is unavailable. (default: `Alpha Channel`) | COMBO | No | `"Alpha Channel"`<br>`"Luminance"`<br>`"Blank"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `IMAGE` | Source image with any alpha channel removed. | IMAGE |
| `MASK` | Mask computed from the selected channel data, threshold and inversion. | MASK |

Notes:

- More detail, including how this node fits with the others, is in the **Image nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
