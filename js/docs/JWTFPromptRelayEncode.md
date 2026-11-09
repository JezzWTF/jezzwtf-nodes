# Prompt Relay Encode

Global prompt plus time-segmented local prompts; each segment's text dominates its own frames.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | The model to use. | MODEL | Yes |  |
| `clip` | The CLIP / text encoder to use. | CLIP | Yes |  |
| `latent` | Empty video latent; its shape sets the frame count. | LATENT | Yes |  |
| `global_prompt` | Global prompt. | STRING | Yes |  |
| `local_prompts` | Segments separated by \| | STRING | Yes |  |
| `segment_lengths` | Comma-separated pixel-frame lengths; blank = equal | STRING | Yes |  |
| `epsilon` | Epsilon. (default: 0.001) | FLOAT | Yes | 1e-06 to 0.99 (step 0.0001) |
| `relay_options` | Relay options. | RELAY_OPTIONS | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `model` | The model to use. | MODEL |
| `positive` | Positive. | CONDITIONING |

Notes:

- More detail, including how this node fits with the others, is in the **Prompt Relay** page of the JezzWTF Documentation window (Alt+Shift+D).
