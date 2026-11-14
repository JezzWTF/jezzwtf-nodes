# Image Saver (Smart Squeeze)

Save PNG, WebP, JPEG, AVIF or TIFF. Smart Squeeze searches for the smallest tested encoding meeting a local colour SSIM target, measured at up to 1024px. PNG can embed workflow metadata.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `images` | The input images (an image batch). | IMAGE | Yes |  |
| `filename_prefix` | Prefix for the saved file; a sub-folder can be included, for example `gifs/clip`. (default: images/JezzWTF) | STRING | Yes |  |
| `format` | Format. (default: `webp`) | COMBO | Yes | `"png"`<br>`"webp"`<br>`"jpeg"`<br>`"avif"`<br>`"tiff"` |
| `smart_squeeze` | Smart squeeze. (default: true) | BOOLEAN | Yes |  |
| `quality_tier` | Quality tier. (default: 8) | INT | Yes | 5 to 10 |
| `quality` | Used when Smart Squeeze is off. (default: 90) | INT | Yes | 1 to 100 |
| `embed_workflow` | Embed prompt and workflow in PNG files only. (default: true) | BOOLEAN | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `images` | The input images (an image batch). | IMAGE |
| `file_paths` | File paths. | STRING |
| `report` | Report. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Image Compare, Image Saver and Mask Editor** page of the JezzWTF Documentation window (Alt+Shift+D).
