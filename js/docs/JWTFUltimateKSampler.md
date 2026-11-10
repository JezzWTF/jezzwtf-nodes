# Ultimate KSampler

KSampler with live preview, chained step runs, RES4LYF dispatch and optional decode.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | Diffusion model used for sampling and optional live previews. | MODEL | Yes |  |
| `positive` | Positive conditioning passed to the sampling guider. | CONDITIONING | Yes |  |
| `latent_image` | Starting image, video or audio-video latent to denoise. | LATENT | Yes |  |
| `sampler_name` | Sampling algorithm, with clown-prefixed choices delegated to RES4LYF when installed. (default: `euler`) | COMBO | Yes | choose from the list |
| `scheduler` | Noise schedule used when no custom sigmas are connected. (default: `beta`) | COMBO | Yes | `"none"`<br>`"simple"`<br>`"sgm_uniform"`<br>`"karras"`<br>`"exponential"`<br>`"ddim_uniform"`<br>`"beta"`<br>`"normal"`<br>`"linear_quadratic"`<br>`"kl_optimal"` |
| `steps` | Number of steps used to build the noise schedule. (default: 30) | INT | Yes | 1 to 10000 |
| `steps_to_run` | Limits how many initial schedule steps run, with -1 running the full schedule. (default: -1) | INT | Yes | -1 to 10000 |
| `cfg` | Classifier-free guidance scale used when guidance and negative conditioning are both available. (default: 5.5) | FLOAT | Yes | -100 to 100 (step 0.01) |
| `cfg_enabled` | Enables classifier-free guidance when negative conditioning is connected. (default: true) | BOOLEAN | Yes |  |
| `denoise` | Fraction of the generated schedule used for denoising. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `seed` | Seed used to generate sampling noise. (default: 0) | INT | Yes |  |
| `eta` | Noise parameter passed to the RES4LYF sampler for clown-prefixed algorithms. (default: 0.5) | FLOAT | Yes | -100 to 100 (step 0.01) |
| `sampler_mode` | Sampling mode forwarded to the RES4LYF sampler for clown-prefixed algorithms. (default: `standard`) | COMBO | Yes | `"standard"`<br>`"unsample"`<br>`"resample"` |
| `bongmath` | Enables the bongmath option on the RES4LYF sampler for clown-prefixed algorithms. (default: true) | BOOLEAN | Yes |  |
| `decode` | Decodes the sampled result through the connected VAEs when enabled. (default: true) | BOOLEAN | Yes |  |
| `tiled_decode` | Uses tiled decoding for the visual VAE when supported. (default: false) | BOOLEAN | Yes |  |
| `preview_fps` | Playback speed in frames per second for animated sampling previews. (default: 12) | INT | Yes | 1 to 60 |
| `negative` | Negative conditioning required to use classifier-free guidance. | CONDITIONING | No |  |
| `vae` | Optional VAE for visual decoding and sampling previews. | VAE | No |  |
| `audio_vae` | Optional audio VAE for decoding the audio stream of an audio-video latent. | VAE | No |  |
| `sigmas` | Optional explicit noise schedule, required when the scheduler is None. | SIGMAS | No |  |
| `options` | Optional RES4LYF options forwarded to the sampler for clown-prefixed algorithms. | OPTIONS | No |  |
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
