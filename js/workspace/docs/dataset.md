# Dataset captioning nodes

## Folder Image Batch and Folder Video Batch

Load one file per run from a folder. With `auto_run_folder` on, a single Run walks the whole folder and stops at the end. Turn it off to take one file per run using `index`.

Outputs include the image, mask, file name, full `path`, and the `index` and `total` so you can show progress.

## Save Caption (Match Image)

Saves a caption as a `.txt` named after the image it came from. Wire the loader's `path` into `image_path` and the caption into `text`.

- `save_location`: **next to image**, or a **custom folder**.
- `extension`: the file extension, `txt` by default. Executable extensions are refused.
- `overwrite`: on by default; turn it off to keep existing captions.

See the *Dataset Captioning* example workflow for the full chain with Qwen3.5.
