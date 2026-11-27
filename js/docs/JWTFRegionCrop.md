# Region Crop (Refine)

Crop one selected box or mask, add context padding and enlarge it for refinement. Keep the region output connected to Region Composite and supply the same original image there. Empty selections stop execution.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `images` | The input images (an image batch). | IMAGE | Yes |  |
| `image_index` | Image index. (default: 0) | INT | Yes | 0 to 999 |
| `region_index` | Region index. (default: 0) | INT | Yes | 0 to 999 |
| `padding` | Extra context on each side, as a fraction of the selected box dimensions. (default: 0.25) | FLOAT | Yes | 0 to 2 (step 0.05) |
| `long_edge` | Refinement crop's long edge; both dimensions round to a 16-pixel grid. (default: 768) | INT | Yes | 64 to 2048 (step 16) |
| `bboxes` | Bboxes. | BOUNDING_BOX | No |  |
| `mask` | The mask. | MASK | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `crop` | Crop. | IMAGE |
| `crop_mask` | Crop mask. | MASK |
| `region` | Region. | JWTF_IMAGE_REGION |

Notes:

- More detail, including how this node fits with the others, is in the **Image Compare, Image Saver and Mask Editor** page of the JezzWTF Documentation window (Alt+Shift+D).
