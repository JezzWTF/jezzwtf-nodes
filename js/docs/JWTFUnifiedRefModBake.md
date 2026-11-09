# Image RefMod Bake

References for Qwen Image 2.1, Fibo 2 and Flux 3.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | The model to use. (default: `qwen21`) | COMBO | Yes | `"qwen21"`<br>`"fibo2"`<br>`"flux3"` |
| `images` | The input images (an image batch). | IMAGE | Yes |  |
| `name` | Name. (default: my_character) | STRING | Yes |  |
| `resolution` | Resolution. (default: 1024) | INT | Yes | 0 to 4096 (step 16) |
| `subfolder` | Subfolder. | STRING | Yes |  |
| `overwrite` | Overwrite. (default: false) | BOOLEAN | Yes |  |
| `vae` | The VAE to use. | VAE | No |  |
| `image_2` | Image 2. | IMAGE | No |  |
| `image_3` | Image 3. | IMAGE | No |  |
| `image_4` | Image 4. | IMAGE | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `path` | File path, overriding the picker. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Tail and Image RefMod** page of the JezzWTF Documentation window (Alt+Shift+D).
