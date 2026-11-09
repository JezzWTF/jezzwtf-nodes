# Character Chat

Chat with V1, V2 and V3 character cards (PNG, JSON or refmod `.safetensors`) on Qwen3.5 through ComfyUI's text generation, with lorebooks, a chat panel and Save chat.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `clip` | The CLIP / text encoder to use. | CLIP | Yes |  |
| `character` | Character. | COMBO | Yes | choose from the list |
| `user_name` | User name. (default: User) | STRING | Yes |  |
| `max_length` | Max length. (default: 512) | INT | Yes | 1 to 32768 |
| `temperature` | Temperature. (default: 0.7) | FLOAT | Yes | 0.01 to 2 (step 0.01) |
| `top_p` | Top p. (default: 0.95) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `top_k` | Top k. (default: 64) | INT | Yes | 0 to 1000 |
| `min_p` | Min p. (default: 0.05) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `repetition_penalty` | Repetition penalty. (default: 1.05) | FLOAT | Yes | 0 to 5 (step 0.01) |
| `seed` | Random seed; the same seed gives the same result. (default: 0) | INT | Yes |  |
| `thinking` | Thinking. (default: false) | BOOLEAN | Yes |  |
| `context_messages` | Context messages. (default: 40) | INT | Yes | 2 to 400 |
| `card_path` | Card path. | STRING | No |  |
| `action` | Action. (default: none) | STRING | No |  |
| `user_message` | User message. | STRING | No |  |
| `history_json` | History json. (default: []) | STRING | No |  |
| `presence_penalty` | Presence penalty. (default: 0.0) | FLOAT | No | 0 to 5 (step 0.01) |
| `mtp` | Mtp. (default: `auto`) | COMBO | No | `"auto"`<br>`"off"`<br>`"2"`<br>`"3"`<br>`"4"`<br>`"5"`<br>`"tree2s1"`<br>`"tree2s2"`<br>`"tree3s1"`<br>`"tree4s1m8"` |
| `video_max_frames` | Video max frames. (default: 8) | INT | No | 1 to 64 |
| `image` | The input image. | IMAGE | No |  |
| `audio` | Audio. | AUDIO | No |  |
| `video` | Video. | VIDEO | No |  |
| `system_prompt` | System prompt. | STRING | No |  |
| `sampling_mode` | Sampling mode. (default: `on`) | COMBO | No | `"on"`<br>`"off"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `reply` | Reply. | STRING |
| `chat_log` | Chat log. | STRING |
| `character_name` | Character name. | STRING |
| `description` | Description. | STRING |
| `avatar` | Avatar. | IMAGE |
| `history_json` | History json. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Welcome** page of the JezzWTF Documentation window (Alt+Shift+D).
