# Troubleshooting

## A node is missing

Restart ComfyUI and hard-refresh the browser tab. Python changes need a restart; JavaScript changes only need a refresh. Check the console for a line naming the family that failed: each family loads on its own, so one failure does not take down the rest.

## "Value not in list" on a loader

A shared workflow carries a placeholder file name such as `your.gif` or `example.png`. Pick a real file in the loader node. GIF Optimise's own picker shows **(use path input)** when a path is wired in, so it never needs a file.

## Video Compare fails with an encoder error

The preview is H.264, which cannot encode an odd width or height. Image inputs are padded to even sizes automatically in this version. If you see the error, update the pack and restart ComfyUI.

## GIF Tools report "pillow fallback"

No ffmpeg was found. Install `imageio-ffmpeg` in ComfyUI's Python, or put ffmpeg on your PATH, or set the `JWTF_FFMPEG` environment variable to its path.

## Character Chat says "No character"

Add a character card to `input/characters` (PNG or JSON), or a refmod to `models/refmods`, then press the refresh button on the chat panel. A path wired into `card_path` is also accepted and shows after the first run.

## Qwen3.5 will not load

Update ComfyUI. Older builds do not know the quantisation format of some Qwen3.5 files.

## I cannot find the file a node saved

See [Where files are saved](topic:saved-files).
