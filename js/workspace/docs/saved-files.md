# Where files are saved

Paths are relative to your ComfyUI folders. Most of them can be changed with a prefix or folder widget on the node.

| What | Where it goes | How to change it |
|---|---|---|
| GIFs from Video to GIF, GIF Optimise | `output/<filename_prefix>_00001.gif` | `filename_prefix`. A subfolder goes in the prefix: `gifs/clip` saves to `output/gifs/clip_00001.gif`. |
| Animated WebP or APNG | `output/<filename_prefix>_00001.webp` | Same as above. |
| RefMod Bake | `models/refmods/<subfolder>/<name>.safetensors` | `name` and `subfolder` on the node. The `saved_path` output holds the full path. |
| Refmod Character Card Baker | `models/refmods/<name>_00001_.safetensors` | `save_to` chooses the refmods folder or the output folder. |
| Character Card PNG Baker | `input/characters/<name>_00001_.png` | `save_to` chooses the characters folder or the output folder. |
| Character Chat, **Save chat** | `output/chats/<character>_<time>.txt` and `.json` | Fixed. |
| Save Caption (Match Image) | Next to the image, as `<image name>.txt` | `save_location` and `extension`. |
| Draw Image | `input/jezzwtf_draw/` | Fixed. |
| Run Timer history | `<ComfyUI user folder>/jezzwtf/run_history.json` | Fixed. The newest 500 runs are kept. |
| LoRA Inspector cache | `<ComfyUI user folder>/jezzwtf_cache/` | Fixed. |
| LM Studio pasted images | `input/jezzwtf_lms/` | Fixed. |
| Video Compare previews | ComfyUI's temp folder | Cleared with the temp folder. |

## Tips

- Nodes that save a file report the full path in a `saved_path` or `report` output. Wire it to a Preview Any node to see it.
- On a shared setup, `models` may resolve through your shared model folders. The path shown by the node is the real one.
