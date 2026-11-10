# Text Encode (Zero Negative)

Encode the positive prompt and build a zeroed or empty negative in one node.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `clip` | Text encoder used to tokenize the prompt and produce scheduled conditioning. | CLIP | Yes |  |
| `positive` | Prompt text encoded into the positive conditioning. | STRING | Yes |  |
| `negative_mode` | Chooses between zeroing the positive conditioning tensors and encoding an empty prompt for negative conditioning. (default: `Zero Out`) | COMBO | Yes | `"Zero Out"`<br>`"Empty String"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `POSITIVE` | Scheduled conditioning encoded from the supplied prompt. | CONDITIONING |
| `NEGATIVE` | Conditioning built by zeroing the positive tensors or by encoding an empty string. | CONDITIONING |

Notes:

- More detail, including how this node fits with the others, is in the **Text nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
