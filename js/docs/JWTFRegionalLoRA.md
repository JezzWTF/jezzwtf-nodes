# Regional Character LoRA

Two character LoRAs, each confined to its own region of the image, with per-region prompts.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | The model to use. | MODEL | Yes |  |
| `clip` | The CLIP / text encoder to use. | CLIP | Yes |  |
| `lora_a` | Lora a. | COMBO | Yes | choose from the list |
| `strength_a` | Strength a. (default: 1.0) | FLOAT | Yes | -4 to 4 (step 0.05) |
| `lora_b` | Lora b. | COMBO | Yes | choose from the list |
| `strength_b` | Strength b. (default: 1.0) | FLOAT | Yes | -4 to 4 (step 0.05) |
| `feather` | Feather. (default: 0.06) | FLOAT | Yes | 0 to 0.3 (step 0.01) |
| `regions` | Regions. (default: {}) | STRING | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `MODEL` | Model. | MODEL |
| `CONDITIONING` | Conditioning. | CONDITIONING |
| `NEGATIVE` | Negative. | CONDITIONING |

Notes:

- More detail, including how this node fits with the others, is in the **LoRA nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
