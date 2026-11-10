# RefMod Apply

Inject RefMod references into MiniMax H3 conditioning, with retention, a curve over the clip, and optional scrambling of several references.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `conditioning` | MiniMax H3 conditioning to receive the selected reference blocks. | CONDITIONING | Yes |  |
| `mod_1` | Selects the RefMod bundle for slot 1, or None to leave the slot empty. (default: `(none)`) | COMBO | Yes | choose from the list |
| `visual_strength_1` | Multiplier for visual references in slot 1, combined with the slot strength. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `audio_strength_1` | Multiplier for audio references in slot 1, combined with the slot strength. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `strength_1` | Multiplier for all included components in slot 1, with 0 skipping the slot. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_1` | Number of times to include each selected reference in slot 1, multiplying its token cost. (default: 1) | INT | Yes | 1 to 10 |
| `components_1` | Includes visual references, audio references or both from slot 1. (default: `All`) | COMBO | Yes | `"All"`<br>`"Visual"`<br>`"Audio"` |
| `mod_2` | Selects the RefMod bundle for slot 2, or None to leave the slot empty. (default: `(none)`) | COMBO | Yes | choose from the list |
| `visual_strength_2` | Multiplier for visual references in slot 2, combined with the slot strength. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `audio_strength_2` | Multiplier for audio references in slot 2, combined with the slot strength. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `strength_2` | Multiplier for all included components in slot 2, with 0 skipping the slot. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_2` | Number of times to include each selected reference in slot 2, multiplying its token cost. (default: 1) | INT | Yes | 1 to 10 |
| `components_2` | Includes visual references, audio references or both from slot 2. (default: `All`) | COMBO | Yes | `"All"`<br>`"Visual"`<br>`"Audio"` |
| `mod_3` | Selects the RefMod bundle for slot 3, or None to leave the slot empty. (default: `(none)`) | COMBO | Yes | choose from the list |
| `visual_strength_3` | Multiplier for visual references in slot 3, combined with the slot strength. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `audio_strength_3` | Multiplier for audio references in slot 3, combined with the slot strength. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `strength_3` | Multiplier for all included components in slot 3, with 0 skipping the slot. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_3` | Number of times to include each selected reference in slot 3, multiplying its token cost. (default: 1) | INT | Yes | 1 to 10 |
| `components_3` | Includes visual references, audio references or both from slot 3. (default: `All`) | COMBO | Yes | `"All"`<br>`"Visual"`<br>`"Audio"` |
| `mod_4` | Selects the RefMod bundle for slot 4, or None to leave the slot empty. (default: `(none)`) | COMBO | Yes | choose from the list |
| `visual_strength_4` | Multiplier for visual references in slot 4, combined with the slot strength. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `audio_strength_4` | Multiplier for audio references in slot 4, combined with the slot strength. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `strength_4` | Multiplier for all included components in slot 4, with 0 skipping the slot. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_4` | Number of times to include each selected reference in slot 4, multiplying its token cost. (default: 1) | INT | Yes | 1 to 10 |
| `components_4` | Includes visual references, audio references or both from slot 4. (default: `All`) | COMBO | Yes | `"All"`<br>`"Visual"`<br>`"Audio"` |
| `retention` | Multiplies each reference strength, with lower values blending toward a blurred latent and 0 omitting references. (default: 0.85) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `max_total_tokens` | Maximum total reference tokens across selected components and copies, with 0 disabling the limit. (default: 0) | INT | Yes | 0 to 1.04858e+06 |
| `curve_direction` | Selects which part of each temporal reference receives the most influence. (default: `constant`) | COMBO | Yes | `"constant"`<br>`"concept_at_start"`<br>`"concept_at_end"`<br>`"concept_at_middle"`<br>`"concept_at_ends"` |
| `curve_shape` | Easing function used to shape the strength curve over the reference. (default: `linear`) | COMBO | Yes | `"linear"`<br>`"ease"`<br>`"sigmoid"`<br>`"tanh"`<br>`"quadratic"`<br>`"cubic"`<br>`"exponential"`<br>`"stair"`<br>`"elastic"`<br>`"bump"`<br>`"dip"` |
| `curve_value` | Scales the temporal curve and caps still-reference strength for nonconstant directions. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `scramble_seed` | Seed for reordering or selecting reference blocks, with -1 preserving their original order. (default: -1) | INT | Yes | -1 to 2.14748e+09 |
| `scramble_mode` | Chooses whether scrambling shuffles all references or retains a subset. (default: `shuffle`) | COMBO | Yes | `"shuffle"`<br>`"subset"`<br>`"legacy_subset"` |
| `scramble_keep` | Number of shuffled reference blocks to retain in subset mode. (default: 1) | INT | Yes | 1 to 80 |
| `extra_mods` | Additional weighted references appended to the selected slots before applying the token budget and retention. | H3_REF_MODS | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `conditioning` | Conditioning with the reference blocks appended, or the original conditioning when no blocks are applied. | CONDITIONING |
| `prompt_hint` | Prompt hints assembled from the selected reference descriptions and concept types. | STRING |
| `info` | Reference summary with strengths, token counts and the number of injected blocks when applied. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **RefMod Bake, Loader and Apply** page of the JezzWTF Documentation window (Alt+Shift+D).
