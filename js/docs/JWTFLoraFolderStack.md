# LoRA Folder Stack

Apply LoRAs picked from one subfolder of models/loras, each with its own on/off and strength.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | The model to use. | MODEL | Yes |  |
| `folder` | Subfolder of models/loras (blank = the root folder itself). | STRING | Yes |  |
| `lora_data` | Lora data. (default: {}) | STRING | Yes |  |
| `clip` | The CLIP / text encoder to use. | CLIP | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `MODEL` | Model. | MODEL |
| `CLIP` | Clip. | CLIP |
| `applied` | Applied. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **LoRA nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
