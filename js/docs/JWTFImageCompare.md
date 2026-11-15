# Image Compare

Compare image batches with a wipe, blend, difference, toggle or mask. B is resized to A; shorter batches repeat.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `image_a` | Image a. | IMAGE | Yes |  |
| `image_b` | Image b. | IMAGE | Yes |  |
| `mask` | The mask. | MASK | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `difference` | Difference. | IMAGE |
| `metrics` | Metrics. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Image Compare, Image Saver and Mask Editor** page of the JezzWTF Documentation window (Alt+Shift+D).
