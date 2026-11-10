# Folder Image Batch

One file per run from a folder, with whole-folder auto-run.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `folder_path` | Directory to scan for supported images. | STRING | Yes |  |
| `sort_mode` | Sorts filenames by embedded numbers or alphabetically before applying the index. | COMBO | Yes | `"numeric (001, 002, 10...)"`<br>`"alphabetical"` |
| `index` | Zero-based position in the sorted list, wrapping in single-image mode and stopping at the end in folder mode. (default: 0) | INT | Yes | 0 to 1.67772e+07 |
| `auto_run_folder` | Lets the frontend run the workflow once per image instead of loading a single selected image. (default: true) | BOOLEAN | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `image` | RGB pixels of the selected image. | IMAGE |
| `mask` | Transparency mask of the selected image, with white marking transparent areas. | MASK |
| `filename` | Selected image's filename without its extension. | STRING |
| `path` | Full path of the selected image, suitable for naming a matching caption. | STRING |
| `index` | Zero-based position of the loaded image after resolving the requested index. | INT |
| `total` | Number of supported images found in the folder. | INT |

Notes:

- More detail, including how this node fits with the others, is in the **Dataset captioning nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
