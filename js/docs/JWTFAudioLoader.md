# Audio Loader

Load an audio file from the input folder (subfolders included) with optional start, length and mono mix.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `audio` | Audio. | COMBO | Yes | choose from the list |
| `start` | Seconds to skip from the start. (default: 0.0) | FLOAT | No | 0 to 36000 (step 0.01) |
| `length` | Seconds to keep; 0 = the rest of the file. (default: 0.0) | FLOAT | No | 0 to 36000 (step 0.01) |
| `mono` | Mix all channels down to one. (default: false) | BOOLEAN | No |  |
| `path` | Optional file path (input, output or temp folder). Overrides the picker. | STRING | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `audio` | Audio. | AUDIO |
| `duration` | Duration. | FLOAT |
| `sample_rate` | Sample rate. | INT |
| `file_path` | File path. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Audio Loader and Album Cover** page of the JezzWTF Documentation window (Alt+Shift+D).
