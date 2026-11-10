# Refmod Character Card Baker

Put a character card into a refmod header, saved to `models/refmods`.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `image` | First image in the batch, embedded as the character's PNG avatar. | IMAGE | Yes |  |
| `json_text` | Character card JSON to embed in the safetensors metadata. | STRING | Yes |  |
| `filename_prefix` | Relative destination prefix, with %name% replaced by the sanitised character name. (default: %name%) | STRING | Yes |  |
| `base_refmod` | Existing RefMod whose tensors are retained, or None to create a character-only file. (default: `(none - character-only file)`) | COMBO | Yes | choose from the list |
| `avatar_max_size` | Maximum avatar edge in pixels, with smaller images preserved at their original size. (default: 512) | INT | Yes | 64 to 2048 (step 16) |
| `fill_missing_fields` | Fills missing V2 character card fields with defaults when enabled. (default: true) | BOOLEAN | Yes |  |
| `system_prompt` | Optional instructions embedded alongside the character card, with blank omitting this metadata. | STRING | No |  |
| `base_refmod_path` | Explicit base RefMod file path that overrides the picker when provided. | STRING | No |  |
| `save_to` | Chooses between the RefMod library and ComfyUI's output directory. (default: `refmods folder`) | COMBO | No | `"refmods folder"`<br>`"output folder"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `saved_path` | Full path of the written safetensors file. | STRING |
| `character_name` | Name read from the embedded character card. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Where files are saved** page of the JezzWTF Documentation window (Alt+Shift+D).
