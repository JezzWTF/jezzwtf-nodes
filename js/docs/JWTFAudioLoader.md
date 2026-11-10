# Audio Loader

Load an audio file from the input folder (subfolders included) with optional start, length and mono mix.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `audio` | Audio file selected from ComfyUI's input folder, including subfolders, unless an explicit path overrides it. | COMBO | Yes | choose from the list |
| `start` | Seconds to skip from the start. (default: 0.0) | FLOAT | No | 0 to 36000 (step 0.01) |
| `length` | Seconds to keep; 0 = the rest of the file. (default: 0.0) | FLOAT | No | 0 to 36000 (step 0.01) |
| `mono` | Mix all channels down to one. (default: false) | BOOLEAN | No |  |
| `path` | Optional file path (input, output or temp folder). Overrides the picker. | STRING | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `audio` | Decoded audio after trimming and any mono mixdown. | AUDIO |
| `duration` | Length of the returned audio in seconds after trimming. | FLOAT |
| `sample_rate` | Sample rate of the returned waveform in samples per second. | INT |
| `file_path` | Resolved path to the original audio file, suitable for passing to Album Cover. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Audio Loader and Album Cover** page of the JezzWTF Documentation window (Alt+Shift+D).
