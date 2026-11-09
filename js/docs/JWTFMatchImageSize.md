# Match Image Size

Resize or pad one image to another's size, with several fit modes.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `input` | Input. | IMAGE,MASK | Yes |  |
| `resize_type` | Resize type. (default: `scale dimensions`) | COMBO | Yes | `"scale dimensions"`<br>`"fit within"`<br>`"fill (crop)"`<br>`"pad to"`<br>`"shortest side"`<br>`"longest side"`<br>`"fit width"`<br>`"fit height"` |
| `scale_method` | Scale method. (default: `lanczos`) | COMBO | Yes | `"nearest-exact"`<br>`"bilinear"`<br>`"area"`<br>`"bicubic"`<br>`"lanczos"` |
| `reference_image` | Reference image. | IMAGE,MASK | No |  |
| `width` | Width in pixels. (default: 0) | INT | No | 0 to 16384 |
| `height` | Height in pixels. (default: 0) | INT | No | 0 to 16384 |
| `crop` | Crop. (default: `center`) | COMBO | No | `"center"`<br>`"disabled"` |
| `pad_color` | Pad color. (default: #000000) | STRING | No |  |
| `round_to` | Round to. (default: 1) | INT | No | 1 to 128 |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `image` | The input image. | IMAGE |
| `mask` | The mask. | MASK |
| `width` | Width in pixels. | INT |
| `height` | Height in pixels. | INT |

Notes:

- More detail, including how this node fits with the others, is in the **Image nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
