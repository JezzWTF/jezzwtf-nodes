# Batch Timer

Counts finished items across queued prompts, with progress and ETA.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `total_images` | Number of images expected in the run, used as the target for the progress counter. (default: 1) | INT | Yes | 1 to 999999 |
| `trigger` | Optional upstream connection that makes the timer tick after the connected work completes. | * | No |  |

Notes:

- More detail, including how this node fits with the others, is in the **Batch Timer and Refresh Page** page of the JezzWTF Documentation window (Alt+Shift+D).
