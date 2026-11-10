# MiniMax H3 Image Edit

One-node H3 image edit.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | Diffusion model used to sample the edit or generated image. | MODEL | Yes |  |
| `clip` | Text encoder used to build the edit conditioning. | CLIP | Yes |  |
| `vae` | MiniMax H3 VAE used to select the still or video conditioning path and decode the sampled latent. | VAE | Yes |  |
| `prompt` | Text describing the edit or image to generate. | STRING | Yes |  |
| `width` | Requested generation width in pixels, rounded to a multiple of 32 when both dimensions are positive. (default: 0) | INT | Yes | 0 to 8192 (step 8) |
| `height` | Requested generation height in pixels, with either dimension set to 0 selecting automatic sizing. (default: 0) | INT | Yes | 0 to 8192 (step 8) |
| `frame_length` | Number of frames requested from the H3 video model, ignored by the still-image path. (default: 1) | INT | Yes | 1 to 257 |
| `batch_index` | Zero-based decoded frame to return, clamped to the available frames. (default: 0) | INT | Yes | 0 to 256 |
| `seed` | Seed used to generate sampling noise. (default: 0) | INT | Yes |  |
| `steps` | Number of sampling steps. (default: 20) | INT | Yes | 1 to 150 |
| `cfg` | Classifier-free guidance scale, with 1 skipping the separate empty-prompt encoding. (default: 1.0) | FLOAT | Yes | 0 to 100 (step 0.1) |
| `sampler_name` | Sampling algorithm used for denoising the latent. | COMBO | Yes | choose from the list |
| `scheduler` | Noise schedule used for the selected sampling algorithm. | COMBO | Yes | `"simple"`<br>`"sgm_uniform"`<br>`"karras"`<br>`"exponential"`<br>`"ddim_uniform"`<br>`"beta"`<br>`"normal"`<br>`"linear_quadratic"`<br>`"kl_optimal"` |
| `denoise` | Fraction of the denoising schedule used for the generation. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `image` | Optional source image to edit and use for automatic sizing and final output dimensions. | IMAGE | No |  |
| `last_frame` | Final-frame reference for H3 video, or a second reference for the still-image model when a source image is connected. | IMAGE | No |  |
| `megapixels` | Target generation area in megapixels when editing with automatic dimensions. (default: 1.0) | FLOAT | No | 0.1 to 8 (step 0.01) |
| `resize_back_method` | Interpolation used to resize the decoded edit back to the source image dimensions. (default: `lanczos`) | COMBO | No | `"lanczos"`<br>`"bicubic"`<br>`"bilinear"`<br>`"area"`<br>`"nearest-exact"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `image` | Selected output frame resized to the input image dimensions when editing. | IMAGE |
| `native_res` | Selected decoded frame at native generation dimensions. | IMAGE |
| `positive` | Positive conditioning generated for the supplied prompt and references. | CONDITIONING |
| `latent` | Sampled latent before frame selection and decoding. | LATENT |
| `width` | Final output width in pixels after any resize back to the input image size. | INT |
| `height` | Final output height in pixels after any resize back to the input image size. | INT |

Notes:

- More detail, including how this node fits with the others, is in the **H3 Image Edit, samplers and upscale** page of the JezzWTF Documentation window (Alt+Shift+D).
