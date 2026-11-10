# LoRA Stack

Apply a stack of LoRAs from models/loras, edited as a visual list.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | Diffusion model to patch with the enabled LoRAs. | MODEL | Yes |  |
| `lora_data` | JSON list of LoRA selections, enable flags and strengths written by the stack editor. (default: {}) | STRING | Yes |  |
| `clip` | Optional text encoder to patch with the enabled LoRAs. | CLIP | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `MODEL` | Model with the enabled LoRAs applied in stack order. | MODEL |
| `CLIP` | Text encoder with its LoRA patches applied, or empty when no encoder was connected. | CLIP |

Notes:

- More detail, including how this node fits with the others, is in the **LoRA nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
