# Character Card PNG Baker

Bake a Character Card V2 into a PNG, saved to `input/characters` so Character Chat lists it.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `image` | The input image. | IMAGE | Yes |  |
| `json_text` | Json text. | STRING | Yes |  |
| `filename_prefix` | Prefix for the saved file; a sub-folder can be included, for example `gifs/clip`. (default: V2_cards/%name%) | STRING | Yes |  |
| `fill_missing_fields` | Fill missing fields. (default: true) | BOOLEAN | Yes |  |
| `save_to` | Save to. (default: `characters folder`) | COMBO | No | `"characters folder"`<br>`"output folder"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `saved_path` | Saved path. | STRING |
| `character_name` | Character name. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Where files are saved** page of the JezzWTF Documentation window (Alt+Shift+D).
