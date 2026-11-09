# LM Studio Bridge

Streaming chat, vision, audio and video through any model in LM Studio.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `server_url` | Server url. (default: http://127.0.0.1:1234) | STRING | Yes |  |
| `model_name` | Model name. (default: local-model) | STRING | Yes |  |
| `system_prompt` | System prompt. | STRING | Yes |  |
| `generate_prompt` | Generate prompt. | STRING | Yes |  |
| `max_tokens` | Max tokens. (default: 512) | INT | Yes | -1 to 65536 |
| `temperature` | Temperature. (default: 0.7) | FLOAT | Yes | 0 to 2 (step 0.01) |
| `top_p` | Top p. (default: 0.95) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `stream` | Stream. (default: true) | BOOLEAN | Yes |  |
| `seed` | Random seed; the same seed gives the same result. (default: 0) | INT | Yes |  |
| `image_size` | Image size. (default: `1024`) | COMBO | Yes | `"1024"`<br>`"768"`<br>`"512"` |
| `video_frames` | Video frames. (default: 8) | INT | Yes | 1 to 32 |
| `image` | The input image. | IMAGE | No |  |
| `audio` | Audio. | AUDIO | No |  |
| `video` | Video. | * | No |  |
| `prompt_override` | Prompt override. | STRING | No |  |
| `embedded_image` | Embedded image. | STRING | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `RESPONSE` | Response. | STRING |
| `PROMPT` | Prompt. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **LM Studio nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
