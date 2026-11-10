# Tail Capture

Save the last frames of a clip so the next clip can continue from them.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `images` | Source frame batch with at least two frames, sampled from the end of the clip. | IMAGE | Yes |  |
| `vae` | MiniMax H3 video VAE used to encode the selected tail frames. | VAE | Yes |  |
| `tail_seconds` | Length of the source tail in seconds, resampled to the H3 frame rate and trimmed to a valid frame count. (default: 1.0) | FLOAT | Yes | 0.25 to 10 (step 0.05) |
| `source_fps` | Source playback rate in frames per second used to locate the start of the tail. (default: 24.0) | FLOAT | Yes | 1 to 120 (step 0.5) |
| `audio` | Optional audio whose ending is cropped to the requested tail duration. | AUDIO | No |  |
| `audio_vae` | MiniMax H3 audio VAE required to encode a connected audio reference. | VAE | No |  |
| `audio_type` | Concept type stored with the audio reference and used in prompt hints. (default: `voice`) | COMBO | No | `"voice"`<br>`"singing"`<br>`"music_style"`<br>`"sound_fx"`<br>`"ambience"` |
| `ref_resolution` | Short-edge limit in pixels before grid rounding and minimum-size handling. (default: 512) | INT | No | 256 to 2048 (step 64) |
| `max_visual_tokens` | Maximum visual reference tokens, with 0 disabling the budget. (default: 16384) | INT | No | 0 to 2.14748e+09 (step 512) |
| `visual_budget` | Chooses whether to trim the visual tail or fail when it exceeds the token budget. (default: `truncate`) | COMBO | No | `"truncate"`<br>`"error"` |
| `description` | Optional description stored with the reference and used to build prompt hints. | STRING | No |  |
| `save_name` | Base name shared by the two alternating capture files and the corresponding Tail Load node. (default: tail_latest) | STRING | No |  |

Notes:

- More detail, including how this node fits with the others, is in the **Tail and Image RefMod** page of the JezzWTF Documentation window (Alt+Shift+D).
