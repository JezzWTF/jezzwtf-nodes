# LM Studio Prompt Box

A prompt box that can combine its text with an incoming prompt: append, prepend, replace, or pass the incoming one through.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `text` | Local prompt text to combine with the incoming text. | STRING | Yes |  |
| `mode` | Chooses the order for joining prompts or which nonempty source takes precedence. (default: `APPEND`) | COMBO | Yes | `"APPEND"`<br>`"PREPEND"`<br>`"REPLACE (local wins)"`<br>`"PASSTHROUGH (incoming wins)"` |
| `separator` | Text inserted between the two prompts when appending or prepending. (default:   ) | STRING | Yes |  |
| `prompt_in` | Optional upstream prompt to combine with the text typed here. | STRING | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `PROMPT_OUT` | Resulting prompt after applying the selected combination mode. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **LM Studio nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
