# Ultimate KSampler

KSampler with live preview, chained step runs, RES4LYF dispatch and optional decode.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | The model to use. | MODEL | Yes |  |
| `positive` | Positive. | CONDITIONING | Yes |  |
| `latent_image` | Latent image. | LATENT | Yes |  |
| `sampler_name` | Sampler name. (default: `euler`) | COMBO | Yes | choose from the list |
| `scheduler` | Scheduler. (default: `beta`) | COMBO | Yes | `"none"`<br>`"simple"`<br>`"sgm_uniform"`<br>`"karras"`<br>`"exponential"`<br>`"ddim_uniform"`<br>`"beta"`<br>`"normal"`<br>`"linear_quadratic"`<br>`"kl_optimal"` |
| `steps` | Steps. (default: 30) | INT | Yes | 1 to 10000 |
| `steps_to_run` | Steps to run. (default: -1) | INT | Yes | -1 to 10000 |
| `cfg` | Cfg. (default: 5.5) | FLOAT | Yes | -100 to 100 (step 0.01) |
| `cfg_enabled` | Cfg enabled. (default: true) | BOOLEAN | Yes |  |
| `denoise` | Denoise. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `seed` | Random seed; the same seed gives the same result. (default: 0) | INT | Yes |  |
| `eta` | Eta. (default: 0.5) | FLOAT | Yes | -100 to 100 (step 0.01) |
| `sampler_mode` | Sampler mode. (default: `standard`) | COMBO | Yes | `"standard"`<br>`"unsample"`<br>`"resample"` |
| `bongmath` | Bongmath. (default: true) | BOOLEAN | Yes |  |
| `decode` | Decode. (default: true) | BOOLEAN | Yes |  |
| `tiled_decode` | Tiled decode. (default: false) | BOOLEAN | Yes |  |
| `preview_fps` | Preview fps. (default: 12) | INT | Yes | 1 to 60 |
| `negative` | Negative. | CONDITIONING | No |  |
| `vae` | The VAE to use. | VAE | No |  |
| `audio_vae` | Audio vae. | VAE | No |  |
| `sigmas` | Sigmas. | SIGMAS | No |  |
| `options` | Options. | OPTIONS | No |  |
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
