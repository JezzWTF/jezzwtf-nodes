# Save Caption (Match Image)

Save a caption as a `.txt` named after the file just loaded.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `text` | Caption written as UTF-8 after trimming surrounding whitespace and normalising line endings. | STRING | Yes |  |
| `image_path` | Source file path whose basename is used to name the caption. | STRING | Yes |  |
| `save_location` | Chooses whether to write beside the source file or in a separate directory. | COMBO | Yes | `"next to image"`<br>`"custom folder"` |
| `custom_folder` | Destination directory used when custom folder is selected. | STRING | Yes |  |
| `extension` | Filename extension for the caption, defaulting to txt. (default: txt) | STRING | Yes |  |
| `overwrite` | Allows replacing an existing caption at the destination, with the file skipped when disabled. (default: true) | BOOLEAN | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `saved_path` | Resolved destination path, including when an existing caption was skipped. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Where files are saved** page of the JezzWTF Documentation window (Alt+Shift+D).
