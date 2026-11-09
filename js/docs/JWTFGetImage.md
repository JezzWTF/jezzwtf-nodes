# Get Image

Grab an in-graph image as IMAGE and MASK.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `image` | The input image. | IMAGE | Yes |  |
| `invert_mask` | Invert mask. (default: false) | BOOLEAN | No |  |
| `mask_threshold` | Mask threshold. (default: 0.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `mask_mode` | Mask mode. (default: `Alpha Channel`) | COMBO | No | `"Alpha Channel"`<br>`"Luminance"`<br>`"Blank"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `IMAGE` | Image. | IMAGE |
| `MASK` | Mask. | MASK |

Notes:

- More detail, including how this node fits with the others, is in the **Image nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
