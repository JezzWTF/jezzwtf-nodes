# GIF Optimise

Re-encode an existing GIF with the same engine.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `gif` | Gif. | COMBO | Yes | choose from the list |
| `mode` | Mode. (default: `balanced`) | COMBO | Yes | `"quality"`<br>`"balanced"`<br>`"smallest"`<br>`"target_size"` |
| `filename_prefix` | Relative to the output folder. Put a subfolder in the prefix, e.g. gifs/optimised saves to output/gifs/optimised_00001.gif. (default: gifs/optimised) | STRING | Yes |  |
| `path` | Optional GIF path (inside input, output or temp). Overrides the picker, e.g. the output of another GIF node. | STRING | No |  |
| `fps` | 0 = keep the GIF's own frame timing. (default: 0.0) | FLOAT | No | 0 to 1000 (step 0.5) |
| `trim_start` | Seconds cut from the start (source time). (default: 0.0) | FLOAT | No | 0 to 36000 (step 0.05) |
| `trim_end` | Seconds where the clip stops (0 = to the end). (default: 0.0) | FLOAT | No | 0 to 36000 (step 0.05) |
| `speed` | Speed. (default: 1.0) | FLOAT | No | 0.1 to 10 (step 0.05) |
| `max_width` | 0 = no limit. Never upscales. (default: 0) | INT | No | 0 to 8192 |
| `max_height` | Max height. (default: 0) | INT | No | 0 to 8192 |
| `resize_filter` | Resize filter. (default: `lanczos`) | COMBO | No | `"lanczos"`<br>`"bicubic"`<br>`"bilinear"`<br>`"box"`<br>`"nearest"` |
| `crop_left` | Crop left. (default: 0) | INT | No | 0 to 8192 |
| `crop_top` | Crop top. (default: 0) | INT | No | 0 to 8192 |
| `crop_right` | Crop right. (default: 0) | INT | No | 0 to 8192 |
| `crop_bottom` | Crop bottom. (default: 0) | INT | No | 0 to 8192 |
| `loop_count` | 0 = forever, 1 = play once, n = play n times. (default: 0) | INT | No | 0 to 65535 |
| `colors` | 0 = by mode, otherwise 16-256. (default: 0) | INT | No | 0 to 256 |
| `palette` | Palette. (default: `auto`) | COMBO | No | `"auto"`<br>`"global_full"`<br>`"global_diff"`<br>`"per_frame"` |
| `dither` | Dither. (default: `auto`) | COMBO | No | `"auto"`<br>`"none"`<br>`"bayer_1"`<br>`"bayer_2"`<br>`"bayer_3"`<br>`"bayer_4"`<br>`"bayer_5"`<br>`"sierra2_4a"`<br>`"floyd_steinberg"` |
| `dedupe_threshold` | -1 = by mode, 0 = exact duplicates only, else mean pixel difference (0-255) under which a frame merges into the previous one. (default: -1.0) | FLOAT | No | -1 to 20 (step 0.05) |
| `transparency_opt` | Store only the changed rectangle of each frame. (default: true) | BOOLEAN | No |  |
| `denoise` | Denoise. (default: `auto`) | COMBO | No | `"auto"`<br>`"off"`<br>`"light"`<br>`"strong"` |
| `delay_mode` | exact keeps real-time speed with mixed 10 ms steps; even snaps fps to a whole 10 ms period. (default: `exact`) | COMBO | No | `"exact"`<br>`"even"` |
| `target_size_mb` | Used by target_size mode. (default: 2.0) | FLOAT | No | 0.05 to 512 (step 0.05) |
| `max_trials` | Encode attempts the target_size search may spend. (default: 10) | INT | No | 2 to 40 |
| `time_budget_s` | Time budget s. (default: 120.0) | FLOAT | No | 5 to 3600 (step 5) |
| `compare_naive` | Also encode a naive one-liner GIF to report the saving. (default: true) | BOOLEAN | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `gif_path` | Gif path. | STRING |
| `preview` | Preview. | IMAGE |
| `report` | Report. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Where files are saved** page of the JezzWTF Documentation window (Alt+Shift+D).
