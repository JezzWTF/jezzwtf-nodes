# Gallery Load

Pick images in a floating gallery window (input or output folders, with folders and search). Several picks become one batch.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `selection` | The picked images as a JSON list; the Gallery window writes this. (default: []) | STRING | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `images` | The input images (an image batch). | IMAGE |
| `masks` | Masks. | MASK |
| `names` | Names. | STRING |
| `count` | Count. | INT |

Notes:

- More detail, including how this node fits with the others, is in the **Gallery Load** page of the JezzWTF Documentation window (Alt+Shift+D).
