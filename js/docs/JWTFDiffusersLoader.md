# Diffusers Loader

Load a Diffusers-layout folder or a single diffusion-model file, with an optional attention backend.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model_name` | Model name. | COMBO | Yes | choose from the list |
| `sageattention_version` | Sageattention version. (default: `None`) | COMBO | Yes | `"None"`<br>`"SageAttention 2"`<br>`"SageAttention 3"` |
| `flashattention_version` | Flashattention version. (default: `None`) | COMBO | Yes | `"None"`<br>`"FlashAttention 2"`<br>`"FlashAttention 3"`<br>`"FlashAttention 4"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `MODEL` | Model. | MODEL |
| `CLIP` | Clip. | CLIP |
| `VAE` | Vae. | VAE |

Notes:

- More detail, including how this node fits with the others, is in the **Model loaders** page of the JezzWTF Documentation window (Alt+Shift+D).
