# Workflow PNG Baker

Embed a workflow or prompt into a PNG.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `image` | Images to save as PNGs with the supplied workflow metadata embedded in each one. | IMAGE | Yes |  |
| `json_text` | ComfyUI workflow JSON, API prompt JSON or a wrapper containing one or both. | STRING | Yes |  |
| `filename_prefix` | Relative subfolder and filename prefix under ComfyUI's output directory. (default: Workflow_PNG/workflow) | STRING | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `saved_path` | Paths to all saved workflow PNGs, one per line. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Character card bakers** page of the JezzWTF Documentation window (Alt+Shift+D).
