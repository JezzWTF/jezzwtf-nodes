# Prompt Relay Options

Experimental strength / window controls for Prompt Relay (video and audio streams).

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `video_strength` | Video strength. (default: 1.0) | FLOAT | Yes | 0 to 10 (step 0.05) |
| `video_window_scale` | Video window scale. (default: 1.0) | FLOAT | Yes | 0 to 4 (step 0.05) |
| `audio_epsilon` | Audio epsilon. (default: 0.0) | FLOAT | Yes | 0 to 0.99 (step 0.0001) |
| `audio_strength` | Audio strength. (default: 1.0) | FLOAT | Yes | 0 to 10 (step 0.05) |
| `audio_window_scale` | Audio window scale. (default: 1.0) | FLOAT | Yes | 0 to 4 (step 0.05) |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `relay_options` | Relay options. | RELAY_OPTIONS |

Notes:

- More detail, including how this node fits with the others, is in the **Prompt Relay** page of the JezzWTF Documentation window (Alt+Shift+D).
