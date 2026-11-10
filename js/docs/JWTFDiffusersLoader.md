# Diffusers Loader

Load a Diffusers-layout folder or a single diffusion-model file, with an optional attention backend.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model_name` | Diffusers directory or standalone diffusion weights file selected from the configured model folders. | COMBO | Yes | choose from the list |
| `sageattention_version` | Optional SageAttention backend, used if available and no FlashAttention version takes precedence. (default: `None`) | COMBO | Yes | `"None"`<br>`"SageAttention 2"`<br>`"SageAttention 3"` |
| `flashattention_version` | Optional FlashAttention backend, with masked attention calls falling back to the default backend. (default: `None`) | COMBO | Yes | `"None"`<br>`"FlashAttention 2"`<br>`"FlashAttention 3"`<br>`"FlashAttention 4"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `MODEL` | Loaded diffusion model with the requested attention backend when available. | MODEL |
| `CLIP` | Text encoder loaded from the selected Diffusers directory when present. | CLIP |
| `VAE` | VAE loaded from the selected Diffusers directory when present. | VAE |

Notes:

- More detail, including how this node fits with the others, is in the **Model loaders** page of the JezzWTF Documentation window (Alt+Shift+D).
