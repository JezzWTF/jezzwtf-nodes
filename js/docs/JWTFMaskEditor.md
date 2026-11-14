# Mask Editor

Run once to load the image, then paint white to select or erase to black. Saved painting applies to every image in the batch. White means masked/inpaint. Optional incoming masks are used until a painting is saved.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `images` | The input images (an image batch). | IMAGE | Yes |  |
| `mask` | The mask. | MASK | No |  |
| `painted_mask` | Saved grayscale PNG under the input folder, managed by the editor. Clear to return to the incoming mask. | STRING | No |  |
| `invert` | Invert. (default: false) | BOOLEAN | No |  |
| `feather` | Feather. (default: 0) | INT | No | 0 to 64 |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `images` | The input images (an image batch). | IMAGE |
| `mask` | The mask. | MASK |
| `mask_image` | Mask image. | IMAGE |

Notes:

- More detail, including how this node fits with the others, is in the **Image Compare, Image Saver and Mask Editor** page of the JezzWTF Documentation window (Alt+Shift+D).
