# Image RefMod Apply

Apply saved RefMods to Qwen, Fibo or Flux image-edit conditioning, with the model detected from the RefMod or chosen by hand.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | The model to use. (default: `auto (from refmod)`) | COMBO | Yes | `"auto (from refmod)"`<br>`"qwen21"`<br>`"fibo2"`<br>`"flux3"` |
| `refmod_1` | Refmod 1. (default: `None`) | COMBO | Yes | choose from the list |
| `clip` | The CLIP / text encoder to use. | CLIP | No |  |
| `prompt` | The text prompt. | STRING | No |  |
| `negative_prompt` | What the result should avoid. | STRING | No |  |
| `positive` | Positive. | CONDITIONING | No |  |
| `negative` | Negative. | CONDITIONING | No |  |
| `refmod_2` | Refmod 2. (default: `None`) | COMBO | No | choose from the list |
| `refmod_3` | Refmod 3. (default: `None`) | COMBO | No | choose from the list |
| `extra_image` | Extra image. | IMAGE | No |  |
| `vae` | The VAE to use. | VAE | No |  |
| `extra_image_resolution` | Extra image resolution. (default: 1024) | INT | No | 0 to 4096 (step 16) |
| `extra_image_scale` | Extra image scale. (default: `keep aspect (resolution)`) | COMBO | No | `"keep aspect (resolution)"`<br>`"match first reference"` |
| `ref_strength` | Ref strength. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `ref_on_negative` | Ref on negative. (default: true) | BOOLEAN | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `positive` | Positive. | CONDITIONING |
| `negative` | Negative. | CONDITIONING |
| `latent` | Latent. | LATENT |

Notes:

- More detail, including how this node fits with the others, is in the guide of the JezzWTF Documentation window (Alt+Shift+D).
