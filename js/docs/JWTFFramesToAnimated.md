# Frames to Animated WebP / APNG

Encode an image batch as an animated WebP or APNG, optionally searching for the best quality under a size target.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `images` | The input images (an image batch). | IMAGE | Yes |  |
| `fps` | Frames per second. (default: 20.0) | FLOAT | Yes | 0.1 to 240 (step 0.5) |
| `format` | Format. (default: `webp`) | COMBO | Yes | `"webp"`<br>`"apng"` |
| `filename_prefix` | Relative to the output folder. Put a subfolder in the prefix, e.g. gifs/anim saves to output/gifs/anim_00001.webp. (default: gifs/anim) | STRING | Yes |  |
| `lossless` | Lossless. (default: false) | BOOLEAN | No |  |
| `quality` | WebP lossy quality; ignored when a target size is set. (default: 80) | INT | No | 0 to 100 |
| `method` | WebP effort: 0 fast, 6 smallest. (default: 4) | INT | No | 0 to 6 |
| `dedupe_threshold` | 0 = merge exact duplicates only. (default: 0.0) | FLOAT | No | 0 to 20 (step 0.05) |
| `target_size_mb` | 0 = off. Lossy WebP searches the best quality that fits. (default: 0.0) | FLOAT | No | 0 to 512 (step 0.05) |
| `loop_count` | 0 = forever. (default: 0) | INT | No | 0 to 65535 |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `file_path` | File path. | STRING |
| `report` | Report. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **GIF Tools** page of the JezzWTF Documentation window (Alt+Shift+D).
