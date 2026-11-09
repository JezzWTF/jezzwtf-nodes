# Album Cover

Embed an image as the cover art of an mp3, flac or m4a file; optionally set title, artist and album.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `image` | The first frame of the batch (or the chosen index) becomes the cover. | IMAGE | Yes |  |
| `audio_path` | An audio file in the input, output or temp folder, e.g. from Audio Loader. | STRING | Yes |  |
| `save_mode` | Save mode. (default: `save a copy in output`) | COMBO | Yes | `"save a copy in output"`<br>`"replace the original"` |
| `filename_prefix` | Sub-folder of output for the copy. (default: covers) | STRING | No |  |
| `cover_size` | Longest edge in pixels; 0 keeps the image size. (default: 1000) | INT | No | 0 to 4096 (step 10) |
| `image_index` | Image index. (default: 0) | INT | No | 0 to 4096 |
| `title` | Title. | STRING | No |  |
| `artist` | Artist. | STRING | No |  |
| `album` | Album. | STRING | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `file_path` | File path. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Audio Loader and Album Cover** page of the JezzWTF Documentation window (Alt+Shift+D).
