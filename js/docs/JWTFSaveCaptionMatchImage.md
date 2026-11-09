# Save Caption (Match Image)

Save a caption as a `.txt` named after the file just loaded.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `text` | Text. | STRING | Yes |  |
| `image_path` | Image path. | STRING | Yes |  |
| `save_location` | Save location. | COMBO | Yes | `"next to image"`<br>`"custom folder"` |
| `custom_folder` | Custom folder. | STRING | Yes |  |
| `extension` | Extension. (default: txt) | STRING | Yes |  |
| `overwrite` | Overwrite. (default: true) | BOOLEAN | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `saved_path` | Saved path. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Where files are saved** page of the JezzWTF Documentation window (Alt+Shift+D).
