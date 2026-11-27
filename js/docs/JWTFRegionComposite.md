# Region Composite (Refine)

Resize a refined crop back to its recorded region and blend through the original selection. Unselected frames, pixels outside the crop and original alpha channels are preserved.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `images` | The same original image batch supplied to Region Crop. | IMAGE | Yes |  |
| `refined_crop` | Refined crop. | IMAGE | Yes |  |
| `region` | Region. | JWTF_IMAGE_REGION | Yes |  |
| `feather` | Blend softness in original-image pixels. (default: 16) | INT | Yes | 0 to 128 |
| `opacity` | Opacity. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.05) |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `image` | The input image. | IMAGE |
| `blend_mask` | Blend mask. | MASK |

Notes:

- More detail, including how this node fits with the others, is in the **Image Compare, Image Saver and Mask Editor** page of the JezzWTF Documentation window (Alt+Shift+D).
