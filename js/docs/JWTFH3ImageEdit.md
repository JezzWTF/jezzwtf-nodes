# MiniMax H3 Image Edit

One-node H3 image edit.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | The model to use. | MODEL | Yes |  |
| `clip` | The CLIP / text encoder to use. | CLIP | Yes |  |
| `vae` | The VAE to use. | VAE | Yes |  |
| `prompt` | The text prompt. | STRING | Yes |  |
| `width` | Width in pixels. (default: 0) | INT | Yes | 0 to 8192 (step 8) |
| `height` | Height in pixels. (default: 0) | INT | Yes | 0 to 8192 (step 8) |
| `frame_length` | Frame length. (default: 1) | INT | Yes | 1 to 257 |
| `batch_index` | Batch index. (default: 0) | INT | Yes | 0 to 256 |
| `seed` | Random seed; the same seed gives the same result. (default: 0) | INT | Yes |  |
| `steps` | Steps. (default: 20) | INT | Yes | 1 to 150 |
| `cfg` | Cfg. (default: 1.0) | FLOAT | Yes | 0 to 100 (step 0.1) |
| `sampler_name` | Sampler name. | COMBO | Yes | choose from the list |
| `scheduler` | Scheduler. | COMBO | Yes | `"simple"`<br>`"sgm_uniform"`<br>`"karras"`<br>`"exponential"`<br>`"ddim_uniform"`<br>`"beta"`<br>`"normal"`<br>`"linear_quadratic"`<br>`"kl_optimal"` |
| `denoise` | Denoise. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `image` | The input image. | IMAGE | No |  |
| `last_frame` | Last frame. | IMAGE | No |  |
| `megapixels` | Megapixels. (default: 1.0) | FLOAT | No | 0.1 to 8 (step 0.01) |
| `resize_back_method` | Resize back method. (default: `lanczos`) | COMBO | No | `"lanczos"`<br>`"bicubic"`<br>`"bilinear"`<br>`"area"`<br>`"nearest-exact"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `image` | The input image. | IMAGE |
| `native_res` | Native res. | IMAGE |
| `positive` | Positive. | CONDITIONING |
| `latent` | Latent. | LATENT |
| `width` | Width in pixels. | INT |
| `height` | Height in pixels. | INT |

Notes:

- More detail, including how this node fits with the others, is in the **H3 Image Edit, samplers and upscale** page of the JezzWTF Documentation window (Alt+Shift+D).
