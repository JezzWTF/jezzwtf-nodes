# Prompt Relay Options

Experimental strength / window controls for Prompt Relay (video and audio streams).

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `video_strength` | Multiplier for the out-of-window attention penalty in the video stream, with 0 disabling it. (default: 1.0) | FLOAT | Yes | 0 to 10 (step 0.05) |
| `video_window_scale` | Scales the video window around each segment midpoint in which no attention penalty is applied. (default: 1.0) | FLOAT | Yes | 0 to 4 (step 0.05) |
| `audio_epsilon` | Sets the falloff for audio attention outside each segment's window, with 0 inheriting the video setting. (default: 0.0) | FLOAT | Yes | 0 to 0.99 (step 0.0001) |
| `audio_strength` | Multiplier for the out-of-window attention penalty in the audio stream, with 0 disabling it. (default: 1.0) | FLOAT | Yes | 0 to 10 (step 0.05) |
| `audio_window_scale` | Scales the audio window around each segment midpoint in which no attention penalty is applied. (default: 1.0) | FLOAT | Yes | 0 to 4 (step 0.05) |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `relay_options` | Video and audio attention settings to connect to Prompt Relay Encode or Timeline. | RELAY_OPTIONS |

Notes:

- More detail, including how this node fits with the others, is in the **Prompt Relay** page of the JezzWTF Documentation window (Alt+Shift+D).
