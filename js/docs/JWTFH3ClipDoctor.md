# H3 Clip Doctor

Check H3 video/AV latents before sampling or export. The latent is authoritative: optional repairs resize/trim/pad decoded media and correct FPS metadata, never invent encoded audio or resize latent samples.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `latent` | Latent. | LATENT | Yes |  |
| `auto_fix` | Auto fix. (default: false) | BOOLEAN | Yes |  |
| `strict` | Raise if any hard check still fails. (default: true) | BOOLEAN | Yes |  |
| `target_fps` | Target fps. (default: 24) | FLOAT | Yes | 1 to 240 |
| `spatial_compression` | Pixel dimensions per latent grid cell; match the H3 VAE. (default: 16) | INT | Yes | 1 to 128 |
| `images` | The input images (an image batch). | IMAGE | No |  |
| `audio` | Audio. | AUDIO | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `latent` | Latent. | LATENT |
| `images` | The input images (an image batch). | IMAGE |
| `audio` | Audio. | AUDIO |
| `report` | Report. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Tail and Image RefMod** page of the JezzWTF Documentation window (Alt+Shift+D).
