# LoRA Inspector

Identify a LoRA by SHA-256 on Civitai and show base model, trigger words and samples.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `lora_name` | Lora name. | COMBO | Yes | choose from the list |
| `source` | Source. (default: `auto`) | COMBO | No | choose from the list |
| `refresh` | Refresh. (default: `use cache`) | COMBO | No | `"use cache"`<br>`"force refresh"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `model_name` | Model name. | STRING |
| `base_model` | Base model. | STRING |
| `trigger_words` | Trigger words. | STRING |
| `metadata_json` | Metadata json. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Where files are saved** page of the JezzWTF Documentation window (Alt+Shift+D).
