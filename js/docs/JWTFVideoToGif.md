# Video to GIF (Optimised)

Two-pass palette, auto dither, duplicate-frame merging, and a target-size mode that searches width, fps and colours for the best-looking GIF under your budget.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `mode` | Chooses a quality, balanced or smallest preset, or searches for settings that fit the target file size. (default: `balanced`) | COMBO | Yes | `"quality"`<br>`"balanced"`<br>`"smallest"`<br>`"target_size"` |
| `filename_prefix` | Relative to the output folder. Put a subfolder in the prefix, e.g. gifs/clip saves to output/gifs/clip_00001.gif. (default: gifs/clip) | STRING | Yes |  |
| `images` | Image batch to encode, taking precedence over a connected video. | IMAGE | No |  |
| `video` | Video source used when no image batch is connected. | VIDEO | No |  |
| `source_fps` | Frame rate of the IMAGE batch (ignored for VIDEO). (default: 24.0) | FLOAT | No | 0.1 to 1000 (step 0.1) |
| `fps` | Output frame rate; 0 = keep the source rate (capped at 50). 25, 20 and 12.5 give an even GIF cadence. (default: 20.0) | FLOAT | No | 0 to 1000 (step 0.5) |
| `trim_start` | Seconds cut from the start (source time). (default: 0.0) | FLOAT | No | 0 to 36000 (step 0.05) |
| `trim_end` | Seconds where the clip stops (0 = to the end). (default: 0.0) | FLOAT | No | 0 to 36000 (step 0.05) |
| `speed` | Playback speed multiplier after trimming, with 1 preserving the original timing. (default: 1.0) | FLOAT | No | 0.1 to 10 (step 0.05) |
| `max_width` | 0 = no limit. Never upscales. (default: 0) | INT | No | 0 to 8192 |
| `max_height` | Maximum output height in pixels, with 0 leaving height unconstrained and no upscaling. (default: 0) | INT | No | 0 to 8192 |
| `resize_filter` | Interpolation filter used when shrinking frames to fit the dimension limits. (default: `lanczos`) | COMBO | No | `"lanczos"`<br>`"bicubic"`<br>`"bilinear"`<br>`"box"`<br>`"nearest"` |
| `crop_left` | Pixels removed from the left edge before resizing. (default: 0) | INT | No | 0 to 8192 |
| `crop_top` | Pixels removed from the top edge before resizing. (default: 0) | INT | No | 0 to 8192 |
| `crop_right` | Pixels removed from the right edge before resizing. (default: 0) | INT | No | 0 to 8192 |
| `crop_bottom` | Pixels removed from the bottom edge before resizing. (default: 0) | INT | No | 0 to 8192 |
| `loop_count` | 0 = forever, 1 = play once, n = play n times. (default: 0) | INT | No | 0 to 65535 |
| `colors` | 0 = by mode, otherwise 16-256. (default: 0) | INT | No | 0 to 256 |
| `palette` | Chooses a shared palette based on all or changed pixels, a per-frame palette, or automatic selection. (default: `auto`) | COMBO | No | `"auto"`<br>`"global_full"`<br>`"global_diff"`<br>`"per_frame"` |
| `dither` | Controls how palette quantisation distributes colour errors, with auto choosing a method for the clip and preset. (default: `auto`) | COMBO | No | `"auto"`<br>`"none"`<br>`"bayer_1"`<br>`"bayer_2"`<br>`"bayer_3"`<br>`"bayer_4"`<br>`"bayer_5"`<br>`"sierra2_4a"`<br>`"floyd_steinberg"` |
| `dedupe_threshold` | -1 = by mode, 0 = exact duplicates only, else mean pixel difference (0-255) under which a frame merges into the previous one. (default: -1.0) | FLOAT | No | -1 to 20 (step 0.05) |
| `transparency_opt` | Store only the changed rectangle of each frame. (default: true) | BOOLEAN | No |  |
| `denoise` | Applies optional noise reduction before palette quantisation, with auto using the preset. (default: `auto`) | COMBO | No | `"auto"`<br>`"off"`<br>`"light"`<br>`"strong"` |
| `delay_mode` | exact keeps real-time speed with mixed 10 ms steps; even snaps fps to a whole 10 ms period. (default: `exact`) | COMBO | No | `"exact"`<br>`"even"` |
| `target_size_mb` | Used by target_size mode. (default: 2.0) | FLOAT | No | 0.05 to 512 (step 0.05) |
| `max_trials` | Encode attempts the target_size search may spend. (default: 10) | INT | No | 2 to 40 |
| `time_budget_s` | Time in seconds after which target-size search stops scheduling more trials. (default: 120.0) | FLOAT | No | 5 to 3600 (step 5) |
| `compare_naive` | Also encode a naive one-liner GIF to report the saving. (default: true) | BOOLEAN | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `gif_path` | Full path to the saved GIF. | STRING |
| `preview` | Decoded output frames, sampled evenly when the GIF contains more than 240 frames. | IMAGE |
| `report` | Encoding summary with dimensions, timing, size and any quality measurements or warnings. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **GIF Tools** page of the JezzWTF Documentation window (Alt+Shift+D).
