# Image Aspect Size

Aspect-aware size output for an image.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `image` | Image batch whose aspect ratio determines the calculated dimensions. | IMAGE | Yes |  |
| `target_size` | Longest side in pixels. The other dimension is calculated to preserve aspect ratio, snapped to multiples of 8. (default: 1024) | INT | Yes | 64 to 8192 (step 8) |
| `flip` | Swap width and height before scaling — useful for rotating orientation without changing the image. (default: false) | BOOLEAN | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `IMAGE` | Original image batch passed through unchanged. | IMAGE |
| `WIDTH` | Calculated width in pixels after scaling and snapping to a multiple of 8. | INT |
| `HEIGHT` | Calculated height in pixels after scaling and snapping to a multiple of 8. | INT |

Notes:

- More detail, including how this node fits with the others, is in the **Image nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
