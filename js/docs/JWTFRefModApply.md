# RefMod Apply

Inject RefMod references into MiniMax H3 conditioning, with retention, a curve over the clip, and optional scrambling of several references.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `conditioning` | Conditioning. | CONDITIONING | Yes |  |
| `mod_1` | Mod 1. (default: `(none)`) | COMBO | Yes | choose from the list |
| `visual_strength_1` | Visual strength 1. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `audio_strength_1` | Audio strength 1. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `strength_1` | Strength 1. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_1` | Copies 1. (default: 1) | INT | Yes | 1 to 10 |
| `components_1` | Components 1. (default: `All`) | COMBO | Yes | `"All"`<br>`"Visual"`<br>`"Audio"` |
| `mod_2` | Mod 2. (default: `(none)`) | COMBO | Yes | choose from the list |
| `visual_strength_2` | Visual strength 2. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `audio_strength_2` | Audio strength 2. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `strength_2` | Strength 2. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_2` | Copies 2. (default: 1) | INT | Yes | 1 to 10 |
| `components_2` | Components 2. (default: `All`) | COMBO | Yes | `"All"`<br>`"Visual"`<br>`"Audio"` |
| `mod_3` | Mod 3. (default: `(none)`) | COMBO | Yes | choose from the list |
| `visual_strength_3` | Visual strength 3. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `audio_strength_3` | Audio strength 3. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `strength_3` | Strength 3. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_3` | Copies 3. (default: 1) | INT | Yes | 1 to 10 |
| `components_3` | Components 3. (default: `All`) | COMBO | Yes | `"All"`<br>`"Visual"`<br>`"Audio"` |
| `mod_4` | Mod 4. (default: `(none)`) | COMBO | Yes | choose from the list |
| `visual_strength_4` | Visual strength 4. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `audio_strength_4` | Audio strength 4. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `strength_4` | Strength 4. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_4` | Copies 4. (default: 1) | INT | Yes | 1 to 10 |
| `components_4` | Components 4. (default: `All`) | COMBO | Yes | `"All"`<br>`"Visual"`<br>`"Audio"` |
| `retention` | Retention. (default: 0.85) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `max_total_tokens` | Max total tokens. (default: 0) | INT | Yes | 0 to 1.04858e+06 |
| `curve_direction` | Curve direction. (default: `constant`) | COMBO | Yes | `"constant"`<br>`"concept_at_start"`<br>`"concept_at_end"`<br>`"concept_at_middle"`<br>`"concept_at_ends"` |
| `curve_shape` | Curve shape. (default: `linear`) | COMBO | Yes | `"linear"`<br>`"ease"`<br>`"sigmoid"`<br>`"tanh"`<br>`"quadratic"`<br>`"cubic"`<br>`"exponential"`<br>`"stair"`<br>`"elastic"`<br>`"bump"`<br>`"dip"` |
| `curve_value` | Curve value. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `scramble_seed` | Scramble seed. (default: -1) | INT | Yes | -1 to 2.14748e+09 |
| `scramble_mode` | Scramble mode. (default: `shuffle`) | COMBO | Yes | `"shuffle"`<br>`"subset"`<br>`"legacy_subset"` |
| `scramble_keep` | Scramble keep. (default: 1) | INT | Yes | 1 to 80 |
| `extra_mods` | Extra mods. | H3_REF_MODS | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `conditioning` | Conditioning. | CONDITIONING |
| `prompt_hint` | Prompt hint. | STRING |
| `info` | Info. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **RefMod Bake, Loader and Apply** page of the JezzWTF Documentation window (Alt+Shift+D).
