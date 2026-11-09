# Workflow PNG Baker

Embed a workflow or prompt into a PNG.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `image` | The input image. | IMAGE | Yes |  |
| `json_text` | Json text. | STRING | Yes |  |
| `filename_prefix` | Prefix for the saved file; a sub-folder can be included, for example `gifs/clip`. (default: Workflow_PNG/workflow) | STRING | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `saved_path` | Saved path. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Character card bakers** page of the JezzWTF Documentation window (Alt+Shift+D).
