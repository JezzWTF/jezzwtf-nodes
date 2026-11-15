# Image RefMod Apply

Apply saved reference bundles with model-specific conditioning. MOSS and Krea require matching edit LoRAs. LTX image guides need a target video latent and core LTXVAddLatentGuide; crop guides with LTXV Crop Guides after sampling.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | Selects the target model family, with auto using the first selected RefMod's family. (default: `auto (from refmod)`) | COMBO | Yes | `"auto (from refmod)"`<br>`"qwen21"`<br>`"fibo2"`<br>`"flux3"`<br>`"moss_image"`<br>`"krea2"`<br>`"flux_kontext"`<br>`"flux2"`<br>`"ltxv"` |
| `refmod_1` | First saved reference bundle to load, or None to omit this slot. (default: `None`) | COMBO | Yes | choose from the list |
| `clip` | Text encoder for model families that encode prompt text in this node. | CLIP | No |  |
| `prompt` | Positive text used for model families that encode prompts directly. | STRING | No |  |
| `negative_prompt` | Negative text used for model families that encode prompts directly. | STRING | No |  |
| `positive` | Upstream positive conditioning for model families that attach references to already encoded prompts. | CONDITIONING | No |  |
| `negative` | Upstream negative conditioning for model families that attach references to already encoded prompts. | CONDITIONING | No |  |
| `refmod_2` | Optional second saved reference bundle, which must match the first bundle's model family. (default: `None`) | COMBO | No | choose from the list |
| `refmod_3` | Optional third saved reference bundle, which must match the other bundles' model family. (default: `None`) | COMBO | No | choose from the list |
| `extra_image` | Additional images encoded at runtime and appended to the saved references. | IMAGE | No |  |
| `vae` | VAE matching the selected model family, required when extra images are connected. | VAE | No |  |
| `extra_image_resolution` | Square root of the target pixel area for encoding extra images, with 0 using source dimensions before model-specific rounding. (default: 1024) | INT | No | 0 to 4096 (step 16) |
| `extra_image_scale` | How the extra image is sized: to the resolution setting, or to the pixel area of the first saved reference (its own aspect is kept). With no saved reference the resolution setting is used. (default: `keep aspect (resolution)`) | COMBO | No | `"keep aspect (resolution)"`<br>`"match first reference"` |
| `ref_strength` | Fraction of the denoising schedule during which the references are active, for models that support scheduling. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `ref_on_negative` | Also attaches the references to negative conditioning on model families that support this option. (default: true) | BOOLEAN | No |  |
| `edit_format` | MOSS/Krea edit LoRA training layout. Match kv_cache to the training configuration; Moss-Image-Edit is MOSS-only. (default: `ai-toolkit`) | COMBO | No | `"ai-toolkit"`<br>`"ai-toolkit (kv_cache off)"`<br>`"Moss-Image-Edit"`<br>`"Krea2 style reference"` |
| `latent_in` | Target video latent for LTX guides; other families return an empty latent at the first reference's size. | LATENT | No |  |
| `latent_idx` | LTX guide placement in latent frames, not pixel frames. (default: 0) | INT | No | -9999 to 9999 |
| `guide_strength` | LTX guide strength; 0 passes the target latent through unchanged. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `positive` | Positive conditioning built for the selected model with the supplied references. | CONDITIONING |
| `negative` | Negative conditioning with references attached when supported and enabled. | CONDITIONING |
| `latent` | For LTX, the target video latent with guide data appended; crop guides after sampling. For image families, an empty latent at the first reference's size, or a 64 by 64 grid without references. | LATENT |

Notes:

- More detail, including how this node fits with the others, is in the **Tail and Image RefMod** page of the JezzWTF Documentation window (Alt+Shift+D).
