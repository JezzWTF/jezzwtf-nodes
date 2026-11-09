# Tail Capture

Save the last frames of a clip so the next clip can continue from them.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `images` | The input images (an image batch). | IMAGE | Yes |  |
| `vae` | The VAE to use. | VAE | Yes |  |
| `tail_seconds` | Tail seconds. (default: 1.0) | FLOAT | Yes | 0.25 to 10 (step 0.05) |
| `source_fps` | Source fps. (default: 24.0) | FLOAT | Yes | 1 to 120 (step 0.5) |
| `audio` | Audio. | AUDIO | No |  |
| `audio_vae` | Audio vae. | VAE | No |  |
| `audio_type` | Audio type. (default: `voice`) | COMBO | No | `"voice"`<br>`"singing"`<br>`"music_style"`<br>`"sound_fx"`<br>`"ambience"` |
| `ref_resolution` | Ref resolution. (default: 512) | INT | No | 256 to 2048 (step 64) |
| `max_visual_tokens` | Max visual tokens. (default: 16384) | INT | No | 0 to 2.14748e+09 (step 512) |
| `visual_budget` | Visual budget. (default: `truncate`) | COMBO | No | `"truncate"`<br>`"error"` |
| `description` | Description. | STRING | No |  |
| `save_name` | Save name. (default: tail_latest) | STRING | No |  |

Notes:

- More detail, including how this node fits with the others, is in the **Tail and Image RefMod** page of the JezzWTF Documentation window (Alt+Shift+D).
