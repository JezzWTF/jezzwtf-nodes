# GIF Tools

Built to keep GIF quality up and file size down.

## Video to GIF (Optimised)

Takes an IMAGE batch or a VIDEO. Choose a `mode`:

| Mode | What it does |
|---|---|
| quality | Highest-quality settings |
| balanced | A sensible middle |
| smallest | Fewer colours and merged duplicate frames |
| target_size | Searches width, fps, colours and dither for the best-looking GIF under `target_size_mb` |

Other controls: trim, speed, size and crop, palette strategy, dither, duplicate-frame threshold, transparency optimisation and delay handling. The report ends with the saved path, and compares the result with a naive ffmpeg GIF of the same size.

## GIF Optimise

The same engine on an existing GIF. Pick a file, or wire a path in (for example from Load GIF); when a path is wired the picker shows **(use path input)** and is not used.

## Load GIF

Loads a GIF as `images`, `mask`, `fps`, `frame_count`, `delays_ms` and `gif_path`.

## GIF Analyse / Compare

Reports sizes, frame counts, SSIM and PSNR between two GIFs, and can output a side-by-side, split or difference image. For a visual A/B, wire the images into Video Compare.

## Frames to Animated WebP / APNG

Smaller animated formats, with a size-targeted lossy WebP mode.

## Saving

`filename_prefix` works like a Save Image node. See [Where files are saved](topic:saved-files). The preview sits at the top of each node.
