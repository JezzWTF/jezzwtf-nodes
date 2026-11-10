# Ultimate Model Loader

Diffusion model, attention backend, block-sparse attention, two text encoders and two VAEs.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model_name` | Diffusion weights to load from ComfyUI's configured diffusion model folders. | COMBO | Yes | choose from the list |
| `quant_format` | Expected weight quantisation for diagnostics, with auto reporting the metadata detected in the loaded model. (default: `auto`) | COMBO | Yes | `"auto"`<br>`"bf16"`<br>`"float8_e4m3fn"`<br>`"float8_e5m2"`<br>`"mxfp8"`<br>`"nvfp4"` |
| `model_type` | Model family hint used for automatic text encoder selection and sparse attention diagnostics. (default: `default`) | COMBO | Yes | `"default"`<br>`"minimax_h3"`<br>`"flux3"`<br>`"moss"` |
| `kitchen` | Allows the registered Comfy Kitchen INT8 attention backend to be selected. (default: true) | BOOLEAN | Yes |  |
| `sage2` | Allows the registered SageAttention 2 backend to be selected. (default: false) | BOOLEAN | Yes |  |
| `sage3` | Allows the registered SageAttention 3 backend to be selected with highest priority. (default: false) | BOOLEAN | Yes |  |
| `triton` | Sets the Triton backend flag, which only takes effect if ComfyUI has enabled the backend at startup. (default: false) | BOOLEAN | Yes |  |
| `flash2` | Allows the registered FlashAttention 2 backend to be selected. (default: false) | BOOLEAN | Yes |  |
| `pytorch` | Allows registered PyTorch attention as the last fallback among enabled backends. (default: false) | BOOLEAN | Yes |  |
| `sparse` | Enables block-sparse attention on supported builds, mutually exclusive with VSA. (default: false) | BOOLEAN | Yes |  |
| `vsa` | Enables video sparse attention on MiniMax H3, mutually exclusive with block-sparse attention. (default: false) | BOOLEAN | Yes |  |
| `clip1_name` | Weights file for the primary text encoder. | COMBO | Yes | choose from the list |
| `clip1_type` | Primary text encoder architecture, with auto using the model family hint. (default: `auto`) | COMBO | Yes | choose from the list |
| `clip1_device` | Device placement for the primary text encoder, with default using ComfyUI's normal placement. (default: `default`) | COMBO | Yes | `"default"`<br>`"cpu"` |
| `clip2_enabled` | Loads a separate second text encoder when enabled. (default: false) | BOOLEAN | Yes |  |
| `clip2_name` | Weights file for the optional second text encoder. | COMBO | Yes | choose from the list |
| `clip2_type` | Second text encoder architecture, with auto using the model family hint. (default: `auto`) | COMBO | Yes | choose from the list |
| `clip2_device` | Device placement for the second text encoder, with default using ComfyUI's normal placement. (default: `default`) | COMBO | Yes | `"default"`<br>`"cpu"` |
| `vae_name` | Weights file for the primary image or video VAE. | COMBO | Yes | choose from the list |
| `audio_vae_enabled` | Loads a separate audio VAE when enabled. (default: false) | BOOLEAN | Yes |  |
| `audio_vae_name` | Weights file for the optional audio VAE. | COMBO | Yes | choose from the list |
| `heading_model` | Editable label for the model section, saved by the loader panel. (default: Model) | STRING | Yes |  |
| `heading_engine` | Editable label for the efficiency settings section, saved by the loader panel. (default: Efficiencies) | STRING | Yes |  |
| `heading_clips` | Editable label for the text encoder section, saved by the loader panel. (default: Text Encoders) | STRING | Yes |  |
| `heading_vaes` | Editable label for the VAE section, saved by the loader panel. (default: VAEs) | STRING | Yes |  |
| `section_order` | Comma-separated section IDs written by the loader panel when sections are reordered. (default: model,engine,clips,vaes) | STRING | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `MODEL` | Loaded diffusion model with any selected attention patches. | MODEL |
| `CLIP (main)` | Primary text encoder loaded for conditioning. | CLIP |
| `CLIP (enhancer)` | Second text encoder for optional prompt enhancement, or empty when disabled. | CLIP |
| `VAE (video/default)` | Primary image or video VAE. | VAE |
| `VAE (audio)` | Separate audio VAE, or empty when disabled. | VAE |

Notes:

- More detail, including how this node fits with the others, is in the **Model loaders** page of the JezzWTF Documentation window (Alt+Shift+D).
