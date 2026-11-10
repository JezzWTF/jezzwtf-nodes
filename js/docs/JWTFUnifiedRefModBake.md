# Image RefMod Bake

References for Qwen Image 2.1, Fibo 2 and Flux 3.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | Chooses which model family will encode the reference images. (default: `qwen21`) | COMBO | Yes | `"qwen21"`<br>`"fibo2"`<br>`"flux3"` |
| `images` | First image batch to encode, with each frame counted as one reference. | IMAGE | Yes |  |
| `name` | Base filename of the reference bundle. (default: my_character) | STRING | Yes |  |
| `resolution` | Square root of the target pixel area for reference encoding, with 0 using source dimensions before model-specific rounding. (default: 1024) | INT | Yes | 0 to 4096 (step 16) |
| `subfolder` | Optional destination subfolder under the RefMod library. | STRING | Yes |  |
| `overwrite` | Replaces an existing bundle when enabled, otherwise returning the existing path. (default: false) | BOOLEAN | Yes |  |
| `vae` | VAE matching the selected model family, required for encoding. | VAE | No |  |
| `image_2` | Additional images appended after the first batch. | IMAGE | No |  |
| `image_3` | Additional images appended after the second input. | IMAGE | No |  |
| `image_4` | Additional images appended last. | IMAGE | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `path` | Full path to the saved or already-existing reference bundle. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Tail and Image RefMod** page of the JezzWTF Documentation window (Alt+Shift+D).
