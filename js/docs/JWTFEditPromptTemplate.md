# Edit Prompt Template

Edit instruction plus optional suffix and separator.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `edit_instruction` | Edit instruction. (default: Change the [subject] into [new subject].) | STRING | Yes |  |
| `enable_suffix` | Enable suffix. (default: true) | BOOLEAN | No |  |
| `suffix` | Suffix. | STRING | No |  |
| `separator` | Separator. (default: `newline`) | COMBO | No | `"newline"`<br>`"space"`<br>`"comma"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `prompt` | The text prompt. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Text nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
