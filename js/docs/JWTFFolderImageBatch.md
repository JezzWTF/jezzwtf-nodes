# Folder Image Batch

One file per run from a folder, with whole-folder auto-run.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `folder_path` | Path to the folder. | STRING | Yes |  |
| `sort_mode` | Sort mode. | COMBO | Yes | `"numeric (001, 002, 10...)"`<br>`"alphabetical"` |
| `index` | Index. (default: 0) | INT | Yes | 0 to 1.67772e+07 |
| `auto_run_folder` | Auto run folder. (default: true) | BOOLEAN | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `image` | The input image. | IMAGE |
| `mask` | The mask. | MASK |
| `filename` | Filename. | STRING |
| `path` | File path, overriding the picker. | STRING |
| `index` | Index. | INT |
| `total` | Total. | INT |

Notes:

- More detail, including how this node fits with the others, is in the **Dataset captioning nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
