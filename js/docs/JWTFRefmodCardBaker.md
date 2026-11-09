# Refmod Character Card Baker

Put a character card into a refmod header, saved to `models/refmods`.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `image` | The input image. | IMAGE | Yes |  |
| `json_text` | Json text. | STRING | Yes |  |
| `filename_prefix` | Prefix for the saved file; a sub-folder can be included, for example `gifs/clip`. (default: %name%) | STRING | Yes |  |
| `base_refmod` | Base refmod. (default: `(none - character-only file)`) | COMBO | Yes | choose from the list |
| `avatar_max_size` | Avatar max size. (default: 512) | INT | Yes | 64 to 2048 (step 16) |
| `fill_missing_fields` | Fill missing fields. (default: true) | BOOLEAN | Yes |  |
| `system_prompt` | System prompt. | STRING | No |  |
| `base_refmod_path` | Base refmod path. | STRING | No |  |
| `save_to` | Save to. (default: `refmods folder`) | COMBO | No | `"refmods folder"`<br>`"output folder"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `saved_path` | Saved path. | STRING |
| `character_name` | Character name. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Where files are saved** page of the JezzWTF Documentation window (Alt+Shift+D).
