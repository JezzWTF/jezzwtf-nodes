# LM Studio Prompt Box

A prompt box that can combine its text with an incoming prompt: append, prepend, replace, or pass the incoming one through.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `text` | Text. | STRING | Yes |  |
| `mode` | Mode. (default: `APPEND`) | COMBO | Yes | `"APPEND"`<br>`"PREPEND"`<br>`"REPLACE (local wins)"`<br>`"PASSTHROUGH (incoming wins)"` |
| `separator` | Separator. (default:   ) | STRING | Yes |  |
| `prompt_in` | Prompt in. | STRING | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `PROMPT_OUT` | Prompt out. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **LM Studio nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
