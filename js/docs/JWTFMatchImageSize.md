# Match Image Size

Resize or pad one image to another's size, with several fit modes.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `input` | Image or mask to resize. | IMAGE,MASK | Yes |  |
| `resize_type` | Determines whether to scale, fit, crop or pad the source to the target dimensions. (default: `scale dimensions`) | COMBO | Yes | `"scale dimensions"`<br>`"fit within"`<br>`"fill (crop)"`<br>`"pad to"`<br>`"shortest side"`<br>`"longest side"`<br>`"fit width"`<br>`"fit height"` |
| `scale_method` | Interpolation filter used when resampling the source. (default: `lanczos`) | COMBO | Yes | `"nearest-exact"`<br>`"bilinear"`<br>`"area"`<br>`"bicubic"`<br>`"lanczos"` |
| `reference_image` | Image or mask supplying target dimensions for any explicit side set to 0. | IMAGE,MASK | No |  |
| `width` | Target width in pixels, with 0 taking the reference width. (default: 0) | INT | No | 0 to 16384 |
| `height` | Target height in pixels, with 0 taking the reference height. (default: 0) | INT | No | 0 to 16384 |
| `crop` | In scale dimensions mode, selects centre cropping or direct resizing to the target aspect ratio. (default: `center`) | COMBO | No | `"center"`<br>`"disabled"` |
| `pad_color` | Hex colour used around the centred result in pad to mode, with invalid values falling back to black. (default: #000000) | STRING | No |  |
| `round_to` | Pixel multiple for rounding calculated sides, with 1 leaving them rounded to whole pixels. (default: 1) | INT | No | 1 to 128 |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `image` | Resized image, with one channel when the source is a mask. | IMAGE |
| `mask` | First channel of the resized result, which is red for an RGB image. | MASK |
| `width` | Actual result width in pixels. | INT |
| `height` | Actual result height in pixels. | INT |

Notes:

- More detail, including how this node fits with the others, is in the **Image nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
