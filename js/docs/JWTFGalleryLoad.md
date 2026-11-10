# Gallery Load

Pick images in a floating gallery window (input or output folders, with folders and search). Several picks become one batch.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `selection` | The picked images as a JSON list; the Gallery window writes this. (default: []) | STRING | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `images` | Selected images as an RGB batch, with later images resized to the first image's dimensions. | IMAGE |
| `masks` | Inverse-alpha masks at the batch dimensions, with zeros for images without transparency. | MASK |
| `names` | Gallery file labels in selection order, one per line. | STRING |
| `count` | Number of images in the returned batch. | INT |

Notes:

- More detail, including how this node fits with the others, is in the **Gallery Load** page of the JezzWTF Documentation window (Alt+Shift+D).
