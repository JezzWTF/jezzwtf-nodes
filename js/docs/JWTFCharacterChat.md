# Character Chat

Chat with V1, V2 and V3 character cards (PNG, JSON or refmod `.safetensors`) on Qwen3.5 through ComfyUI's text generation, with lorebooks, a chat panel and Save chat.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `clip` | Text-generation CLIP model used to tokenize the chat prompt, generate tokens and decode the reply. | CLIP | Yes |  |
| `character` | Character card to load from the available cards unless a card path overrides it. | COMBO | Yes | choose from the list |
| `user_name` | Participant name used for user placeholders and the transcript, with blank falling back to User. (default: User) | STRING | Yes |  |
| `max_length` | Maximum number of tokens requested for each generated reply. (default: 512) | INT | Yes | 1 to 32768 |
| `temperature` | Controls how strongly token probabilities are weighted during sampling, with higher values allowing more variation. (default: 0.7) | FLOAT | Yes | 0.01 to 2 (step 0.01) |
| `top_p` | Nucleus sampling cutoff based on the cumulative probability of the most likely tokens. (default: 0.95) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `top_k` | Maximum number of highest-ranked tokens considered at each sampling step. (default: 64) | INT | Yes | 0 to 1000 |
| `min_p` | Minimum sampling probability relative to the most likely token. (default: 0.05) | FLOAT | Yes | 0 to 1 (step 0.01) |
| `repetition_penalty` | Factor applied to discourage reuse of previously generated tokens, with 1 leaving their scores unchanged. (default: 1.05) | FLOAT | Yes | 0 to 5 (step 0.01) |
| `seed` | Random seed passed to the generator when sampling is enabled. (default: 0) | INT | Yes |  |
| `thinking` | Requests a reasoning block before the reply when enabled. (default: false) | BOOLEAN | Yes |  |
| `context_messages` | Number of most recent messages included in the model prompt, while the full history is retained. (default: 40) | INT | Yes | 2 to 400 |
| `card_path` | Optional card path overriding the picker, restricted to ComfyUI's input, output and RefMod directories. | STRING | No |  |
| `action` | Queued chat operation written by the chat UI, with none loading history without generating a reply. (default: none) | STRING | No |  |
| `user_message` | Message text supplied by the chat UI for the next send action. | STRING | No |  |
| `history_json` | JSON list of role and content pairs written by the chat UI to carry the conversation between runs. (default: []) | STRING | No |  |
| `presence_penalty` | Penalty for tokens that already appeared, with 0 disabling the penalty. (default: 0.0) | FLOAT | No | 0 to 5 (step 0.01) |
| `mtp` | Selects the model's multi-token prediction mode when the generator supports it. (default: `auto`) | COMBO | No | `"auto"`<br>`"off"`<br>`"2"`<br>`"3"`<br>`"4"`<br>`"5"`<br>`"tree2s1"`<br>`"tree2s2"`<br>`"tree3s1"`<br>`"tree4s1m8"` |
| `video_max_frames` | Maximum number of frames sampled from the attached video for the model. (default: 8) | INT | No | 1 to 64 |
| `image` | Images supplied to the tokenizer as visual context for the reply. | IMAGE | No |  |
| `audio` | Audio supplied to the tokenizer when the model supports audio input. | AUDIO | No |  |
| `video` | Video sampled into images for visual context. | VIDEO | No |  |
| `system_prompt` | Optional replacement for the card's system instructions. | STRING | No |  |
| `sampling_mode` | Switches between sampling with the chosen parameters and greedy generation. (default: `on`) | COMBO | No | `"on"`<br>`"off"` |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `reply` | Newly generated reply or the last assistant message when no new reply is generated and the history ends with one. | STRING |
| `chat_log` | Full conversation formatted as a transcript with speaker names. | STRING |
| `character_name` | Name of the loaded character. | STRING |
| `description` | Card description after substituting character and user placeholders. | STRING |
| `avatar` | Image used as the loaded character's avatar. | IMAGE |
| `history_json` | Updated conversation as a JSON list of role and content pairs. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Welcome** page of the JezzWTF Documentation window (Alt+Shift+D).
