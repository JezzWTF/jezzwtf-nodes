# Folder Video Batch

One file per run from a folder, with whole-folder auto-run.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `folder_path` | Directory to scan for supported videos. | STRING | Yes |  |
| `sort_mode` | Sorts filenames by embedded numbers or alphabetically before applying the index. | COMBO | Yes | `"numeric (001, 002, 10...)"`<br>`"alphabetical"` |
| `index` | Zero-based position in the sorted list, wrapping in single-video mode and stopping at the end in folder mode. (default: 0) | INT | Yes | 0 to 1.67772e+07 |
| `auto_run_folder` | Lets the frontend run the workflow once per video instead of loading a single selected video. (default: true) | BOOLEAN | Yes |  |
| `force_rate` | Resamples the video to this many frames per second before frame selection, with 0 using the source rate. (default: 0.0) | FLOAT | No | 0 to 120 (step 0.5) |
| `frame_load_cap` | Maximum number of selected frames to return, with 0 allowing all selected frames. (default: 0) | INT | No | 0 to 100000 |
| `skip_first_frames` | Number of frames to skip at the start of the rate-adjusted frame sequence. (default: 0) | INT | No | 0 to 1e+06 |
| `select_every_nth` | Keeps one frame per interval after skipping, with 1 keeping every frame. (default: 1) | INT | No | 1 to 1000 |
| `resize_longest_side` | Target longest edge in pixels, with 0 preserving the decoded dimensions. (default: 0) | INT | No | 0 to 8192 (step 2) |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `frames` | Selected RGB frames as an image batch. | IMAGE |
| `audio` | Stereo audio cropped to the selected time window, with silence when audio is unavailable. | AUDIO |
| `filename` | Selected video's filename without its extension. | STRING |
| `path` | Full path of the selected video. | STRING |
| `index` | Zero-based position of the loaded video after resolving the requested index. | INT |
| `total` | Number of supported videos found in the folder. | INT |
| `fps` | Effective playback rate in frames per second after rate conversion and frame striding. | FLOAT |
| `video` | Video assembled from the selected frames, effective rate and available audio. | VIDEO |

Notes:

- More detail, including how this node fits with the others, is in the **Dataset captioning nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
