# Character card bakers

## Character Card PNG Baker

Embeds a Character Card V2 (JSON) into an image and saves a PNG. It accepts the JSON a model wrote, tolerating a code fence or a `<think>` block around it, and can fill missing V2 fields.

`save_to` chooses **characters folder** (default, so Character Chat lists the card straight away) or **output folder**.

## Refmod Character Card Baker

Stores a character card, an avatar and an optional system prompt inside a `.safetensors` file header, so Character Chat can use it as `refmod:<name>`.

- With no `base_refmod` it writes a character-only file.
- With a base refmod it copies the file and keeps its tensors byte for byte, so one file holds the look, the voice and the persona.

`save_to` chooses **refmods folder** (default) or **output folder**.

## Workflow PNG Baker

Embeds a workflow or prompt JSON into a PNG so ComfyUI can open it by dropping the image in.
