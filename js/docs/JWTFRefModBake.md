# RefMod Bake (Character)

Bake portrait stills, a clip and/or a voice into one reusable H3 RefMod bundle.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `name` | File name. Saved to models/refmods/<subfolder>/<name>.safetensors; the saved_path output holds the full path. (default: my_character) | STRING | Yes |  |
| `vae` | MiniMax H3 video VAE used to encode visual references. | VAE | Yes |  |
| `images` | Image batch whose frames are encoded as separate still references. | IMAGE | No |  |
| `video_frames` | Frame batch treated as one video reference. | IMAGE | No |  |
| `folder` | Optional folder of reference media, with relative paths resolved under ComfyUI's input folder. | STRING | No |  |
| `audio` | Optional audio clip to encode as a separate reference. | AUDIO | No |  |
| `audio_vae` | MiniMax H3 audio VAE required to encode a connected audio reference. | VAE | No |  |
| `audio_type` | Concept type stored with the audio reference and used in prompt hints. (default: `voice`) | COMBO | No | `"voice"`<br>`"singing"`<br>`"music_style"`<br>`"sound_fx"`<br>`"ambience"` |
| `audio_max_seconds` | Maximum duration in seconds of the audio used for the reference. (default: 30.0) | FLOAT | No | 0.025 to 600 (step 0.5) |
| `audio_max_tokens` | Maximum audio reference tokens before encoding fails the budget check, with 0 disabling the limit. (default: 5120) | INT | No | 0 to 2.14748e+09 |
| `ref_resolution` | Short-edge limit in pixels before grid rounding and minimum-size handling. (default: 1024) | INT | No | 256 to 2048 (step 64) |
| `max_visual_tokens` | Maximum visual reference tokens, with 0 disabling the budget. (default: 16384) | INT | No | 0 to 2.14748e+09 (step 512) |
| `visual_budget` | Chooses whether to fail or truncate visual references when they exceed the token budget. (default: `error`) | COMBO | No | `"error"`<br>`"truncate"` |
| `folder_max_items` | Maximum number of media files loaded from the reference folder. (default: 8) | INT | No | 1 to 256 |
| `folder_max_edge` | Maximum long edge in pixels for media loaded from the reference folder. (default: 1536) | INT | No | 256 to 4096 (step 64) |
| `description` | Optional description stored with the reference and used to build prompt hints. | STRING | No |  |
| `subfolder` | Folder inside models/refmods. Empty saves straight into models/refmods. (default: characters) | STRING | No |  |
| `overwrite` | Replace a file of the same name instead of failing. (default: true) | BOOLEAN | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `mods` | Baked reference components paired with full strength for use by RefMod Apply. | H3_REF_MODS |
| `saved_path` | Full path to the saved safetensors bundle. | STRING |
| `details` | JSON summary of the bundle path, member names, kinds and token counts. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **RefMod Bake, Loader and Apply** page of the JezzWTF Documentation window (Alt+Shift+D).
