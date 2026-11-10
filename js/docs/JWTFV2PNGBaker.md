# Character Card PNG Baker

Bake a Character Card V2 into a PNG, saved to `input/characters` so Character Chat lists it.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `image` | Images to save as PNGs with the same character card embedded in each one. | IMAGE | Yes |  |
| `json_text` | Character card JSON to parse and embed in each PNG. | STRING | Yes |  |
| `filename_prefix` | Relative subfolder and filename prefix, with %name% replaced by the sanitised character name. (default: V2_cards/%name%) | STRING | Yes |  |
| `fill_missing_fields` | Fills missing V2 fields with defaults when enabled. (default: true) | BOOLEAN | Yes |  |
| `save_to` | Chooses between ComfyUI's input/characters directory and its output directory. (default: `characters folder`) | COMBO | No | `"characters folder"`<br>`"output folder"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `saved_path` | Paths to all saved character PNGs, one per line. | STRING |
| `character_name` | Character name read from the embedded card. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Where files are saved** page of the JezzWTF Documentation window (Alt+Shift+D).
