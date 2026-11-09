# RefMod Loader

Load up to four RefMod files by name, each with its own strength and copy count, and output them for RefMod Apply.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `mod_1` | Mod 1. (default: `(none)`) | COMBO | Yes | choose from the list |
| `strength_1` | Strength 1. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_1` | Copies 1. (default: 1) | INT | Yes | 1 to 10 |
| `mod_2` | Mod 2. (default: `(none)`) | COMBO | Yes | choose from the list |
| `strength_2` | Strength 2. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_2` | Copies 2. (default: 1) | INT | Yes | 1 to 10 |
| `mod_3` | Mod 3. (default: `(none)`) | COMBO | Yes | choose from the list |
| `strength_3` | Strength 3. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_3` | Copies 3. (default: 1) | INT | Yes | 1 to 10 |
| `mod_4` | Mod 4. (default: `(none)`) | COMBO | Yes | choose from the list |
| `strength_4` | Strength 4. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_4` | Copies 4. (default: 1) | INT | Yes | 1 to 10 |
| `show_info` | Show info. (default: false) | BOOLEAN | No |  |
| `max_total_tokens` | Max total tokens. (default: 0) | INT | No | 0 to 1.04858e+06 |
| `visual_strength_1` | Visual strength 1. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `audio_strength_1` | Audio strength 1. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `components_1` | Components 1. (default: `All`) | COMBO | No | `"All"`<br>`"Visual"`<br>`"Audio"` |
| `visual_strength_2` | Visual strength 2. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `audio_strength_2` | Audio strength 2. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `components_2` | Components 2. (default: `All`) | COMBO | No | `"All"`<br>`"Visual"`<br>`"Audio"` |
| `visual_strength_3` | Visual strength 3. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `audio_strength_3` | Audio strength 3. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `components_3` | Components 3. (default: `All`) | COMBO | No | `"All"`<br>`"Visual"`<br>`"Audio"` |
| `visual_strength_4` | Visual strength 4. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `audio_strength_4` | Audio strength 4. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `components_4` | Components 4. (default: `All`) | COMBO | No | `"All"`<br>`"Visual"`<br>`"Audio"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `mods` | Mods. | H3_REF_MODS |
| `prompt_hint` | Prompt hint. | STRING |
| `info` | Info. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **RefMod Bake, Loader and Apply** page of the JezzWTF Documentation window (Alt+Shift+D).
