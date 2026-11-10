# H3 KSampler

CFG-free SamplerCustomAdvanced-shaped sampler for MiniMax H3 with live preview.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `latent_image` | Starting image, video or audio-video latent to denoise. | LATENT | Yes |  |
| `sampler_name` | Sampling algorithm used when no external sampler is connected. (default: `euler`) | COMBO | Yes | choose from the list |
| `scheduler` | Noise schedule used when no external sigmas are connected. (default: `beta`) | COMBO | Yes | `"none"`<br>`"simple"`<br>`"sgm_uniform"`<br>`"karras"`<br>`"exponential"`<br>`"ddim_uniform"`<br>`"beta"`<br>`"normal"`<br>`"linear_quadratic"`<br>`"kl_optimal"` |
| `steps` | Number of steps used to build the noise schedule from the widgets. (default: 8) | INT | Yes | 1 to 10000 |
| `steps_to_run` | Limits how many initial schedule steps run, with -1 running the full schedule. (default: -1) | INT | Yes | -1 to 10000 |
| `denoise` | Fraction of the widget-generated schedule used for denoising. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `seed` | Seed used to create noise when no external noise generator is connected. (default: 0) | INT | Yes |  |
| `decode` | Decodes the sampled result through the connected VAEs when enabled. (default: true) | BOOLEAN | Yes |  |
| `tiled_decode` | Uses tiled decoding for the visual VAE when supported. (default: false) | BOOLEAN | Yes |  |
| `preview_fps` | Playback speed in frames per second for animated sampling previews. (default: 12) | INT | Yes | 1 to 60 |
| `noise` | Optional noise generator that overrides seeded noise from this node. | NOISE | No |  |
| `guider` | Optional external guider that replaces the node's basic positive-only guider. | GUIDER | No |  |
| `sampler` | Optional external sampler that overrides the sampler picker. | SAMPLER | No |  |
| `sigmas` | Optional explicit noise schedule, required when the scheduler is None. | SIGMAS | No |  |
| `model` | Model used to build the basic guider and preferred for generating the noise schedule when connected. | MODEL | No |  |
| `positive` | Positive conditioning used to build the basic guider when no external guider is connected. | CONDITIONING | No |  |
| `vae` | Optional VAE for visual decoding and sampling previews. | VAE | No |  |
| `audio_vae` | Optional audio VAE for decoding the audio stream of an audio-video latent. | VAE | No |  |
| `preview` | Enables intermediate image or video previews during sampling. (default: true) | BOOLEAN | No |  |
| `preview_max_res` | Maximum preview edge in pixels, with 0 disabling the resolution limit. (default: 1024) | INT | No | 0 to 8192 (step 8) |
| `preview_frames` | Maximum number of frames in each preview update, with 1 showing a still image. (default: 1) | INT | No | 1 to 1024 |
| `preview_jpeg_quality` | JPEG compression quality for live preview frames on a scale from 30 to 100. (default: 80) | INT | No | 30 to 100 |
| `preview_tiny_vae` | Selects a tiny preview decoder, with the current None option using the normal preview fallback. (default: `none`) | COMBO | No | choose from the list |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `latent` | Sampled latent at the end of the executed schedule. | LATENT |
| `denoised` | Denoised latent when the sampler provides one, otherwise the sampled latent. | LATENT |
| `image` | Decoded image or frame batch, with a placeholder when visual decoding is unavailable or disabled. | IMAGE |
| `audio` | Decoded audio stream, with silence when audio decoding is unavailable or disabled. | AUDIO |

Notes:

- More detail, including how this node fits with the others, is in the **H3 Image Edit, samplers and upscale** page of the JezzWTF Documentation window (Alt+Shift+D).
