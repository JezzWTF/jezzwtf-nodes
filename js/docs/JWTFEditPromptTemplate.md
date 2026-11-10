# Edit Prompt Template

Edit instruction plus optional suffix and separator.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `edit_instruction` | Instruction describing the edit to request from the model. (default: Change the [subject] into [new subject].) | STRING | Yes |  |
| `enable_suffix` | Appends the preservation instruction when it contains text. (default: true) | BOOLEAN | No |  |
| `suffix` | Text appended to the edit instruction when enabled, defaulting to a request to preserve the rest of the image. | STRING | No |  |
| `separator` | Characters inserted between the edit instruction and the enabled suffix. (default: `newline`) | COMBO | No | `"newline"`<br>`"space"`<br>`"comma"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `prompt` | Combined prompt with surrounding whitespace trimmed. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Text nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
