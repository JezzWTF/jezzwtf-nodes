# Regional Character LoRA

Two character LoRAs, each confined to its own region of the image, with per-region prompts.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | Diffusion model to patch so LoRA effects follow spatial masks. | MODEL | Yes |  |
| `clip` | Text encoder used for global and region prompts. | CLIP | Yes |  |
| `lora_a` | LoRA file whose weights apply in regions assigned to A. | COMBO | Yes | choose from the list |
| `strength_a` | Multiplier for LoRA A within its regions, with 0 disabling it. (default: 1.0) | FLOAT | Yes | -4 to 4 (step 0.05) |
| `lora_b` | LoRA file whose weights apply in regions assigned to B. | COMBO | Yes | choose from the list |
| `strength_b` | Multiplier for LoRA B within its regions, with 0 disabling it. (default: 1.0) | FLOAT | Yes | -4 to 4 (step 0.05) |
| `feather` | Width of the LoRA mask edge transition as a fraction of the corresponding image dimension. (default: 0.06) | FLOAT | Yes | 0 to 0.3 (step 0.01) |
| `regions` | JSON written by the region editor containing normalised rectangles, their LoRA assignments and local and global prompts. (default: {}) | STRING | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `MODEL` | Model with LoRA effects masked to the assigned regions during sampling. | MODEL |
| `CONDITIONING` | Positive conditioning containing the global prompt and masked regional prompts. | CONDITIONING |
| `NEGATIVE` | Zeroed negative conditioning derived from the first positive entry with region mask metadata removed. | CONDITIONING |

Notes:

- More detail, including how this node fits with the others, is in the **LoRA nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
