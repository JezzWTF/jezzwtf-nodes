# Folder Video Batch

One file per run from a folder, with whole-folder auto-run.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `folder_path` | Path to the folder. | STRING | Yes |  |
| `sort_mode` | Sort mode. | COMBO | Yes | `"numeric (001, 002, 10...)"`<br>`"alphabetical"` |
| `index` | Index. (default: 0) | INT | Yes | 0 to 1.67772e+07 |
| `auto_run_folder` | Auto run folder. (default: true) | BOOLEAN | Yes |  |
| `force_rate` | Force rate. (default: 0.0) | FLOAT | No | 0 to 120 (step 0.5) |
| `frame_load_cap` | Frame load cap. (default: 0) | INT | No | 0 to 100000 |
| `skip_first_frames` | Skip first frames. (default: 0) | INT | No | 0 to 1e+06 |
| `select_every_nth` | Select every nth. (default: 1) | INT | No | 1 to 1000 |
| `resize_longest_side` | Resize longest side. (default: 0) | INT | No | 0 to 8192 (step 2) |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `frames` | Frames. | IMAGE |
| `audio` | Audio. | AUDIO |
| `filename` | Filename. | STRING |
| `path` | File path, overriding the picker. | STRING |
| `index` | Index. | INT |
| `total` | Total. | INT |
| `fps` | Frames per second. | FLOAT |
| `video` | Video. | VIDEO |

Notes:

- More detail, including how this node fits with the others, is in the **Dataset captioning nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
