# Install and requirements

## Install

Search for **JezzWTF QoL Nodes** in ComfyUI Manager, or clone the repository into `ComfyUI/custom_nodes` and restart ComfyUI. Then hard-refresh the browser tab.

## Requirements

- **ComfyUI 0.44.0 or newer.** That is the version the pack is tested on.
- Nothing else is required. Some features use optional packages when they are present.

| Package | Used for |
|---|---|
| `imageio-ffmpeg` or a system `ffmpeg` | GIF Tools (falls back to Pillow with a warning) |
| `opencv-python` | Video frame sampling for LM Studio and Character Chat |
| `soundfile` | Sending audio to LM Studio |
| `requests` | LM Studio streaming |

## Local only

The pack reads and writes local folders, talks to LM Studio and Civitai, keeps run history on disk and reads the OS clipboard. It is not meant for Comfy Cloud.

## Models

Model-specific nodes need the matching model: a Qwen3.5 text encoder for Character Chat, a MiniMax H3 checkpoint, text encoder and VAEs for the H3 nodes, and so on.
