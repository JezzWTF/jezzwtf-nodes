# LoRA Folder Stack (Multi-Model)

Folder LoRA stack applied to up to five models (CLIP only on the first).

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | First diffusion model to patch with the stack. | MODEL | Yes |  |
| `folder` | Subfolder of models/loras (blank = the root folder itself). | STRING | Yes |  |
| `lora_data` | JSON list of LoRA selections, enable flags and strengths written by the stack editor. (default: {}) | STRING | Yes |  |
| `clip` | Optional text encoder patched alongside the first diffusion model. | CLIP | No |  |
| `model_2` | Second model to patch with the same stack. | MODEL | No |  |
| `model_3` | Third model to patch with the same stack. | MODEL | No |  |
| `model_4` | Fourth model to patch with the same stack. | MODEL | No |  |
| `model_5` | Fifth model to patch with the same stack. | MODEL | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `MODEL` | First model with the enabled LoRAs applied in stack order. | MODEL |
| `CLIP` | Text encoder patched alongside the first model, or empty when no encoder was connected. | CLIP |
| `applied` | Summary of the LoRAs applied to the first model, including their strengths. | STRING |
| `MODEL 2` | Patched second model, or empty when its input is disconnected. | MODEL |
| `MODEL 3` | Patched third model, or empty when its input is disconnected. | MODEL |
| `MODEL 4` | Patched fourth model, or empty when its input is disconnected. | MODEL |
| `MODEL 5` | Patched fifth model, or empty when its input is disconnected. | MODEL |

Notes:

- More detail, including how this node fits with the others, is in the guide of the JezzWTF Documentation window (Alt+Shift+D).
