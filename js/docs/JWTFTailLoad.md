# Tail Load

Read back the tail saved by Tail Capture as references for a continuing clip.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `enabled` | Enabled. (default: true) | BOOLEAN | Yes |  |
| `strength` | Strength. (default: 1.0) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `save_name` | Save name. (default: tail_latest) | STRING | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `mods` | Mods. | H3_REF_MODS |
| `info` | Info. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Tail and Image RefMod** page of the JezzWTF Documentation window (Alt+Shift+D).
