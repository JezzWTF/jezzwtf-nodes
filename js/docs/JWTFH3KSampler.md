# H3 KSampler

CFG-free SamplerCustomAdvanced-shaped sampler for MiniMax H3 with live preview.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `latent_image` | Latent image. | LATENT | Yes |  |
| `sampler_name` | Sampler name. (default: `euler`) | COMBO | Yes | choose from the list |
| `scheduler` | Scheduler. (default: `beta`) | COMBO | Yes | `"none"`<br>`"simple"`<br>`"sgm_uniform"`<br>`"karras"`<br>`"exponential"`<br>`"ddim_uniform"`<br>`"beta"`<br>`"normal"`<br>`"linear_quadratic"`<br>`"kl_optimal"` |
| `steps` | Steps. (default: 8) | INT | Yes | 1 to 10000 |
| `steps_to_run` | Steps to run. (default: -1) | INT | Yes | -1 to 10000 |
| `denoise` | Denoise. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `seed` | Random seed; the same seed gives the same result. (default: 0) | INT | Yes |  |
| `decode` | Decode. (default: true) | BOOLEAN | Yes |  |
| `tiled_decode` | Tiled decode. (default: false) | BOOLEAN | Yes |  |
| `preview_fps` | Preview fps. (default: 12) | INT | Yes | 1 to 60 |
| `noise` | Noise. | NOISE | No |  |
| `guider` | Guider. | GUIDER | No |  |
| `sampler` | Sampler. | SAMPLER | No |  |
| `sigmas` | Sigmas. | SIGMAS | No |  |
| `model` | The model to use. | MODEL | No |  |
| `positive` | Positive. | CONDITIONING | No |  |
| `vae` | The VAE to use. | VAE | No |  |
| `audio_vae` | Audio vae. | VAE | No |  |
| `preview` | Preview. (default: true) | BOOLEAN | No |  |
| `preview_max_res` | Preview max res. (default: 1024) | INT | No | 0 to 8192 (step 8) |
| `preview_frames` | Preview frames. (default: 1) | INT | No | 1 to 1024 |
| `preview_jpeg_quality` | Preview jpeg quality. (default: 80) | INT | No | 30 to 100 |
| `preview_tiny_vae` | Preview tiny vae. (default: `none`) | COMBO | No | choose from the list |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `latent` | Latent. | LATENT |
| `denoised` | Denoised. | LATENT |
| `image` | The input image. | IMAGE |
| `audio` | Audio. | AUDIO |

Notes:

- More detail, including how this node fits with the others, is in the **H3 Image Edit, samplers and upscale** page of the JezzWTF Documentation window (Alt+Shift+D).
