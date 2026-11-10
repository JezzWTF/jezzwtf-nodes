# Prompt Relay Timeline

Prompt Relay with a drag-and-drop timeline editor for the segments.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | Diffusion model to patch for time-segmented attention. | MODEL | Yes |  |
| `clip` | Text encoder used to tokenize and encode the combined prompts. | CLIP | Yes |  |
| `latent` | Empty video latent; its shape sets the frame count. | LATENT | Yes |  |
| `global_prompt` | Prompt applied across all frames alongside the segment prompts. | STRING | Yes |  |
| `max_frames` | Timeline length in video frames for the editor, compared against the latent's frame count during encoding. (default: 129) | INT | Yes | 1 to 10000 |
| `timeline_data` | JSON of segment prompts and frame lengths written by the timeline editor, taking precedence over the separate text fields when valid. | STRING | Yes |  |
| `local_prompts` | Pipe-separated segment prompts maintained by the editor and used as a fallback when timeline JSON is unavailable. | STRING | Yes |  |
| `segment_lengths` | Comma-separated segment lengths in video frames maintained by the editor, with blank dividing the latent into equal parts. | STRING | Yes |  |
| `epsilon` | Controls how quickly a segment's influence falls off outside its time window, with smaller values reducing spillover. (default: 0.001) | FLOAT | Yes | 1e-06 to 0.99 (step 0.0001) |
| `fps` | Playback rate in frames per second used by the editor to convert frame positions to displayed seconds. (default: 24.0) | FLOAT | No | 0.1 to 240 (step 0.1) |
| `time_units` | Displays timeline positions in frames or seconds while retaining frame-based segment lengths. (default: `frames`) | COMBO | No | `"frames"`<br>`"seconds"` |
| `relay_options` | Optional settings for attention strength and time windows in the video and audio streams. | RELAY_OPTIONS | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `model` | Model patched so segment tokens have less influence outside their assigned time windows. | MODEL |
| `positive` | Positive conditioning encoded from the global and segment prompts. | CONDITIONING |

Notes:

- More detail, including how this node fits with the others, is in the **Prompt Relay** page of the JezzWTF Documentation window (Alt+Shift+D).
