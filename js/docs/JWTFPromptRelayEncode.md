# Prompt Relay Encode

Global prompt plus time-segmented local prompts; each segment's text dominates its own frames.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | Diffusion model to patch for time-segmented attention. | MODEL | Yes |  |
| `clip` | Text encoder used to tokenize and encode the combined prompts. | CLIP | Yes |  |
| `latent` | Empty video latent; its shape sets the frame count. | LATENT | Yes |  |
| `global_prompt` | Prompt applied across all frames alongside the segment prompts. | STRING | Yes |  |
| `local_prompts` | Segments separated by \| | STRING | Yes |  |
| `segment_lengths` | Comma-separated pixel-frame lengths; blank = equal | STRING | Yes |  |
| `epsilon` | Controls how quickly a segment's influence falls off outside its time window, with smaller values reducing spillover. (default: 0.001) | FLOAT | Yes | 1e-06 to 0.99 (step 0.0001) |
| `relay_options` | Optional settings for attention strength and time windows in the video and audio streams. | RELAY_OPTIONS | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `model` | Model patched so segment tokens have less influence outside their assigned time windows. | MODEL |
| `positive` | Positive conditioning encoded from the global and segment prompts. | CONDITIONING |

Notes:

- More detail, including how this node fits with the others, is in the **Prompt Relay** page of the JezzWTF Documentation window (Alt+Shift+D).
