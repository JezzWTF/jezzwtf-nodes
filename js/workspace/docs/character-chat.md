# Character Chat

Chat with character cards inside ComfyUI, using the same LLM you load as a text encoder.

## Setup

1. Load Qwen3.5 with a Load CLIP node (type `stable_diffusion`).
2. Add Character Chat and connect `clip`.
3. Use the card upload button on the panel to add a card (PNG or JSON) or a refmod `.safetensors`, then press refresh.
4. Type a message and press **Enter**. Each message queues the workflow.

## The panel

| Control | What it does |
|---|---|
| Upload | Adds a card or refmod to `input/characters` |
| Refresh | Reloads the character list |
| Settings | Shows sampling settings |
| Edit, regenerate, delete | Hover a message |
| Swipe | Alternate greetings, before the chat starts |
| New chat | Restarts from the greeting (click twice) |
| Copy chat | Copies the conversation as text |
| **Save chat** | Writes the conversation to `output/chats` as `.txt` and `.json` |

## Cards

V1, V2 and V3 cards are supported, as PNG or JSON, with lorebooks (keyword, regex, constant and secondary keys) and `{{char}}` / `{{user}}` substitution. A character can also come from a refmod, see [Character card bakers](topic:character-cards).

`card_path` overrides the dropdown and accepts a path inside the input, output or refmods folders. After a run, the panel header shows the card that was actually used.

## Outputs

`reply`, `chat_log`, `character_name`, `description`, `avatar` and `history_json`.

## Good to know

- The chat is saved inside the workflow. Save the workflow (Ctrl+S) to resume later.
- The prompt uses Qwen's ChatML format, so other model families may not follow it.
- `mtp` uses speculative decoding where the model supports it.
