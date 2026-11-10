# LM Studio Bridge

Streaming chat, vision, audio and video through any model in LM Studio.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `server_url` | Base address of the LM Studio server, with blank falling back to the local address on port 1234. (default: http://127.0.0.1:1234) | STRING | Yes |  |
| `model_name` | Model identifier sent to the server, with blank falling back to local-model. (default: local-model) | STRING | Yes |  |
| `system_prompt` | System instructions sent with the completion request. | STRING | Yes |  |
| `generate_prompt` | User request text sent unless a nonblank prompt override is connected. | STRING | Yes |  |
| `max_tokens` | Maximum number of reply tokens to request, with zero or negative values using the server's limit. (default: 512) | INT | Yes | -1 to 65536 |
| `temperature` | Sampling temperature sent to the server, with higher values allowing more variation. (default: 0.7) | FLOAT | Yes | 0 to 2 (step 0.01) |
| `top_p` | Cumulative probability cutoff for nucleus sampling on the server. (default: 0.95) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `stream` | Streams partial text for the node's live preview when enabled. (default: true) | BOOLEAN | Yes |  |
| `seed` | Seed sent to the server when positive, with 0 leaving the choice to the server. (default: 0) | INT | Yes |  |
| `image_size` | Maximum long edge in pixels for images and sampled video frames sent to the server. (default: `1024`) | COMBO | Yes | `"1024"`<br>`"768"`<br>`"512"` |
| `video_frames` | Maximum number of video frames sampled across the clip and sent as images. (default: 8) | INT | Yes | 1 to 32 |
| `image` | Image batch attached to the user request as JPEGs. | IMAGE | No |  |
| `audio` | Audio attached to the user request as WAV data. | AUDIO | No |  |
| `video` | Video object, frame batch or file reference sampled into still images for the request. | * | No |  |
| `prompt_override` | Connected text that replaces the typed prompt when it contains non-whitespace characters. | STRING | No |  |
| `embedded_image` | JSON file reference written by the node's image picker for an additional image attachment. | STRING | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `RESPONSE` | Server reply text or an error message if the completion request fails. | STRING |
| `PROMPT` | Effective user prompt text after applying the optional override. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **LM Studio nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
