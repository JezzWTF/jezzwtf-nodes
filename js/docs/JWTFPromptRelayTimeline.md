# Prompt Relay Timeline

Prompt Relay with a drag-and-drop timeline editor for the segments.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | The model to use. | MODEL | Yes |  |
| `clip` | The CLIP / text encoder to use. | CLIP | Yes |  |
| `latent` | Empty video latent; its shape sets the frame count. | LATENT | Yes |  |
| `global_prompt` | Global prompt. | STRING | Yes |  |
| `max_frames` | Max frames. (default: 129) | INT | Yes | 1 to 10000 |
| `timeline_data` | Timeline data. | STRING | Yes |  |
| `local_prompts` | Local prompts. | STRING | Yes |  |
| `segment_lengths` | Segment lengths. | STRING | Yes |  |
| `epsilon` | Epsilon. (default: 0.001) | FLOAT | Yes | 1e-06 to 0.99 (step 0.0001) |
| `fps` | Frames per second. (default: 24.0) | FLOAT | No | 0.1 to 240 (step 0.1) |
| `time_units` | Time units. (default: `frames`) | COMBO | No | `"frames"`<br>`"seconds"` |
| `relay_options` | Relay options. | RELAY_OPTIONS | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `model` | The model to use. | MODEL |
| `positive` | Positive. | CONDITIONING |

Notes:

- More detail, including how this node fits with the others, is in the **Prompt Relay** page of the JezzWTF Documentation window (Alt+Shift+D).
