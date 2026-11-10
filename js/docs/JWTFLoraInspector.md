# LoRA Inspector

Identify a LoRA by SHA-256 on Civitai and show base model, trigger words and samples.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `lora_name` | Local LoRA file to read and identify by hash for a Civitai metadata lookup. | COMBO | Yes | choose from the list |
| `source` | Selects the Civitai site for lookup or lets the inspector choose automatically. (default: `auto`) | COMBO | No | choose from the list |
| `refresh` | Reuses cached metadata by default or requests a fresh lookup. (default: `use cache`) | COMBO | No | `"use cache"`<br>`"force refresh"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `model_name` | Model title from Civitai or local metadata, falling back to the filename. | STRING |
| `base_model` | Base model reported by Civitai or embedded metadata, or empty when unknown. | STRING |
| `trigger_words` | Comma-separated trigger words from the inspection results. | STRING |
| `metadata_json` | Complete inspection payload as JSON, including available remote and local metadata. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Where files are saved** page of the JezzWTF Documentation window (Alt+Shift+D).
