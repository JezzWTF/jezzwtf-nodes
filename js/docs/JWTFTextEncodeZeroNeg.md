# Text Encode (Zero Negative)

Encode the positive prompt and build a zeroed or empty negative in one node.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `clip` | The CLIP / text encoder to use. | CLIP | Yes |  |
| `positive` | Positive. | STRING | Yes |  |
| `negative_mode` | Negative mode. (default: `Zero Out`) | COMBO | Yes | `"Zero Out"`<br>`"Empty String"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `POSITIVE` | Positive. | CONDITIONING |
| `NEGATIVE` | Negative. | CONDITIONING |

Notes:

- More detail, including how this node fits with the others, is in the **Text nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
