# Tail Load

Read back the tail saved by Tail Capture as references for a continuing clip.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `enabled` | Loads the latest matching capture when enabled, otherwise returning an empty reference list. (default: true) | BOOLEAN | Yes |  |
| `strength` | Strength assigned to each loaded tail reference. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `save_name` | Base name matching the Tail Capture node's alternating save slots. (default: tail_latest) | STRING | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `mods` | References from the newest capture with the requested strength, or an empty list when disabled or missing. | H3_REF_MODS |
| `info` | Loaded reference details and source path, or a status message when loading is disabled or no capture exists. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Tail and Image RefMod** page of the JezzWTF Documentation window (Alt+Shift+D).
