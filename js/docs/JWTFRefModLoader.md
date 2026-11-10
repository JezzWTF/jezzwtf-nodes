# RefMod Loader

Load up to four RefMod files by name, each with its own strength and copy count, and output them for RefMod Apply.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `mod_1` | Selects the RefMod bundle for slot 1, or None to leave the slot empty. (default: `(none)`) | COMBO | Yes | choose from the list |
| `strength_1` | Multiplier for all included components in slot 1, with 0 skipping the slot. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_1` | Number of times to include each selected reference in slot 1, multiplying its token cost. (default: 1) | INT | Yes | 1 to 10 |
| `mod_2` | Selects the RefMod bundle for slot 2, or None to leave the slot empty. (default: `(none)`) | COMBO | Yes | choose from the list |
| `strength_2` | Multiplier for all included components in slot 2, with 0 skipping the slot. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_2` | Number of times to include each selected reference in slot 2, multiplying its token cost. (default: 1) | INT | Yes | 1 to 10 |
| `mod_3` | Selects the RefMod bundle for slot 3, or None to leave the slot empty. (default: `(none)`) | COMBO | Yes | choose from the list |
| `strength_3` | Multiplier for all included components in slot 3, with 0 skipping the slot. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_3` | Number of times to include each selected reference in slot 3, multiplying its token cost. (default: 1) | INT | Yes | 1 to 10 |
| `mod_4` | Selects the RefMod bundle for slot 4, or None to leave the slot empty. (default: `(none)`) | COMBO | Yes | choose from the list |
| `strength_4` | Multiplier for all included components in slot 4, with 0 skipping the slot. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `copies_4` | Number of times to include each selected reference in slot 4, multiplying its token cost. (default: 1) | INT | Yes | 1 to 10 |
| `show_info` | Logs extra details for each distinct loaded reference when enabled. (default: false) | BOOLEAN | No |  |
| `max_total_tokens` | Maximum total reference tokens across selected components and copies, with 0 disabling the limit. (default: 0) | INT | No | 0 to 1.04858e+06 |
| `visual_strength_1` | Multiplier for visual references in slot 1, combined with the slot strength. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `audio_strength_1` | Multiplier for audio references in slot 1, combined with the slot strength. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `components_1` | Includes visual references, audio references or both from slot 1. (default: `All`) | COMBO | No | `"All"`<br>`"Visual"`<br>`"Audio"` |
| `visual_strength_2` | Multiplier for visual references in slot 2, combined with the slot strength. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `audio_strength_2` | Multiplier for audio references in slot 2, combined with the slot strength. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `components_2` | Includes visual references, audio references or both from slot 2. (default: `All`) | COMBO | No | `"All"`<br>`"Visual"`<br>`"Audio"` |
| `visual_strength_3` | Multiplier for visual references in slot 3, combined with the slot strength. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `audio_strength_3` | Multiplier for audio references in slot 3, combined with the slot strength. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `components_3` | Includes visual references, audio references or both from slot 3. (default: `All`) | COMBO | No | `"All"`<br>`"Visual"`<br>`"Audio"` |
| `visual_strength_4` | Multiplier for visual references in slot 4, combined with the slot strength. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `audio_strength_4` | Multiplier for audio references in slot 4, combined with the slot strength. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `components_4` | Includes visual references, audio references or both from slot 4. (default: `All`) | COMBO | No | `"All"`<br>`"Visual"`<br>`"Audio"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `mods` | Loaded references paired with their effective slot strengths, including requested copies. | H3_REF_MODS |
| `prompt_hint` | Prompt hints assembled from the selected reference descriptions and concept types. | STRING |
| `info` | Per-reference strengths and token counts, followed by the total token cost. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **RefMod Bake, Loader and Apply** page of the JezzWTF Documentation window (Alt+Shift+D).
