# LoRA nodes

## LoRA Stack and LoRA Folder Stack

A stack editor over your LoRA folder: add, remove, reorder by dragging, toggle, set model and clip strength, favourites and a folder filter. **Roll** randomises the strengths of enabled rows. The Folder Stack variants read from a folder you choose inside `models/loras`; the Multi-Model variant shares one stack across several models.

## LoRA Inspector

Point it at a LoRA to see its trigger words, base model, sample images and stats, looked up on Civitai from the file hash. Results are cached in `<ComfyUI user folder>/jezzwtf_cache`. If you need an API key, set it with an environment variable or key file, never in the workflow.

## Regional Character LoRA

Two character LoRAs in one image, each confined to its own region so the identities do not blend. Draw the two regions on the editor, give each a prompt, and set the feather. It needs a model whose image tokens follow its text tokens.
