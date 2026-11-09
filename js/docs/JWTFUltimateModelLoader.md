# Ultimate Model Loader

Diffusion model, attention backend, block-sparse attention, two text encoders and two VAEs.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model_name` | Model name. | COMBO | Yes | choose from the list |
| `quant_format` | Quant format. (default: `auto`) | COMBO | Yes | `"auto"`<br>`"bf16"`<br>`"asym_w4a8_int8"`<br>`"convrot_w4a4"`<br>`"float8_e4m3fn"`<br>`"float8_e5m2"`<br>`"int8_tensorwise"`<br>`"mxfp8"`<br>`"nvfp4"`<br>`"w6a8_int8"` |
| `model_type` | Model type. (default: `default`) | COMBO | Yes | `"default"`<br>`"minimax_h3"`<br>`"flux3"`<br>`"moss"` |
| `kitchen` | Kitchen. (default: true) | BOOLEAN | Yes |  |
| `sage2` | Sage2. (default: false) | BOOLEAN | Yes |  |
| `sage3` | Sage3. (default: false) | BOOLEAN | Yes |  |
| `triton` | Triton. (default: false) | BOOLEAN | Yes |  |
| `flash2` | Flash2. (default: false) | BOOLEAN | Yes |  |
| `pytorch` | Pytorch. (default: false) | BOOLEAN | Yes |  |
| `sparse` | Sparse. (default: false) | BOOLEAN | Yes |  |
| `vsa` | Vsa. (default: false) | BOOLEAN | Yes |  |
| `clip1_name` | Clip1 name. | COMBO | Yes | choose from the list |
| `clip1_type` | Clip1 type. (default: `auto`) | COMBO | Yes | choose from the list |
| `clip1_device` | Clip1 device. (default: `default`) | COMBO | Yes | `"default"`<br>`"cpu"` |
| `clip2_enabled` | Clip2 enabled. (default: false) | BOOLEAN | Yes |  |
| `clip2_name` | Clip2 name. | COMBO | Yes | choose from the list |
| `clip2_type` | Clip2 type. (default: `auto`) | COMBO | Yes | choose from the list |
| `clip2_device` | Clip2 device. (default: `default`) | COMBO | Yes | `"default"`<br>`"cpu"` |
| `vae_name` | Vae name. | COMBO | Yes | choose from the list |
| `audio_vae_enabled` | Audio vae enabled. (default: false) | BOOLEAN | Yes |  |
| `audio_vae_name` | Audio vae name. | COMBO | Yes | choose from the list |
| `heading_model` | Heading model. (default: Model) | STRING | Yes |  |
| `heading_engine` | Heading engine. (default: Efficiencies) | STRING | Yes |  |
| `heading_clips` | Heading clips. (default: Text Encoders) | STRING | Yes |  |
| `heading_vaes` | Heading vaes. (default: VAEs) | STRING | Yes |  |
| `section_order` | Section order. (default: model,engine,clips,vaes) | STRING | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `MODEL` | Model. | MODEL |
| `CLIP (main)` | Clip (main). | CLIP |
| `CLIP (enhancer)` | Clip (enhancer). | CLIP |
| `VAE (video/default)` | Vae (video/default). | VAE |
| `VAE (audio)` | Vae (audio). | VAE |

Notes:

- More detail, including how this node fits with the others, is in the **Model loaders** page of the JezzWTF Documentation window (Alt+Shift+D).
