# LoRA Folder Stack (Multi-Model)

Folder LoRA stack applied to up to five models (CLIP only on the first).

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | The model to use. | MODEL | Yes |  |
| `folder` | Subfolder of models/loras (blank = the root folder itself). | STRING | Yes |  |
| `lora_data` | Lora data. (default: {}) | STRING | Yes |  |
| `clip` | The CLIP / text encoder to use. | CLIP | No |  |
| `model_2` | Model 2. | MODEL | No |  |
| `model_3` | Model 3. | MODEL | No |  |
| `model_4` | Model 4. | MODEL | No |  |
| `model_5` | Model 5. | MODEL | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `MODEL` | Model. | MODEL |
| `CLIP` | Clip. | CLIP |
| `applied` | Applied. | STRING |
| `MODEL 2` | Model 2. | MODEL |
| `MODEL 3` | Model 3. | MODEL |
| `MODEL 4` | Model 4. | MODEL |
| `MODEL 5` | Model 5. | MODEL |

Notes:

- More detail, including how this node fits with the others, is in the guide of the JezzWTF Documentation window (Alt+Shift+D).
