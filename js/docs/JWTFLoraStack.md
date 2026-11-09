# LoRA Stack

Apply a stack of LoRAs from models/loras, edited as a visual list.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | The model to use. | MODEL | Yes |  |
| `lora_data` | Lora data. (default: {}) | STRING | Yes |  |
| `clip` | The CLIP / text encoder to use. | CLIP | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `MODEL` | Model. | MODEL |
| `CLIP` | Clip. | CLIP |

Notes:

- More detail, including how this node fits with the others, is in the **LoRA nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
