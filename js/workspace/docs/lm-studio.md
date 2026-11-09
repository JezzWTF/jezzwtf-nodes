# LM Studio nodes

## LM Studio Bridge

Streaming chat, vision, audio and video through any model loaded in LM Studio (or another OpenAI-compatible server). Set `server_url`, pick a model, and wire an image, video or audio if the model supports them.

- Images pasted onto the node are uploaded to `input/jezzwtf_lms/` with unique names.
- A single image batch is capped at 16 images; longer batches are sampled evenly.
- The Stop button and ComfyUI's Cancel both interrupt a request.

## LM Studio Prompt Box

A live reader and editor for model output that can combine it with an incoming prompt (append, prepend, replace or pass through).
