# RefMod Bake (Character)

Bake portrait stills, a clip and/or a voice into one reusable H3 RefMod bundle.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `name` | File name. Saved to models/refmods/<subfolder>/<name>.safetensors; the saved_path output holds the full path. (default: my_character) | STRING | Yes |  |
| `vae` | The VAE to use. | VAE | Yes |  |
| `images` | The input images (an image batch). | IMAGE | No |  |
| `video_frames` | Video frames. | IMAGE | No |  |
| `folder` | Folder. | STRING | No |  |
| `audio` | Audio. | AUDIO | No |  |
| `audio_vae` | Audio vae. | VAE | No |  |
| `audio_type` | Audio type. (default: `voice`) | COMBO | No | `"voice"`<br>`"singing"`<br>`"music_style"`<br>`"sound_fx"`<br>`"ambience"` |
| `audio_max_seconds` | Audio max seconds. (default: 30.0) | FLOAT | No | 0.025 to 600 (step 0.5) |
| `audio_max_tokens` | Audio max tokens. (default: 5120) | INT | No | 0 to 2.14748e+09 |
| `ref_resolution` | Ref resolution. (default: 1024) | INT | No | 256 to 2048 (step 64) |
| `max_visual_tokens` | Max visual tokens. (default: 16384) | INT | No | 0 to 2.14748e+09 (step 512) |
| `visual_budget` | Visual budget. (default: `error`) | COMBO | No | `"error"`<br>`"truncate"` |
| `folder_max_items` | Folder max items. (default: 8) | INT | No | 1 to 256 |
| `folder_max_edge` | Folder max edge. (default: 1536) | INT | No | 256 to 4096 (step 64) |
| `description` | Description. | STRING | No |  |
| `subfolder` | Folder inside models/refmods. Empty saves straight into models/refmods. (default: characters) | STRING | No |  |
| `overwrite` | Replace a file of the same name instead of failing. (default: true) | BOOLEAN | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `mods` | Mods. | H3_REF_MODS |
| `saved_path` | Saved path. | STRING |
| `details` | Details. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **RefMod Bake, Loader and Apply** page of the JezzWTF Documentation window (Alt+Shift+D).
