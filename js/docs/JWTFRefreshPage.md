# Refresh Page (VRAM Cleaner)

Pass-through node that frees VRAM and reloads on demand.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `clean_vram` | Unloads models held by ComfyUI to release memory. (default: true) | BOOLEAN | Yes |  |
| `clear_cache` | Asks ComfyUI to empty its device cache and runs Python garbage collection. (default: true) | BOOLEAN | Yes |  |
| `clear_node_cache` | Requests a workflow execution cache reset through the ComfyUI queue when available. (default: false) | BOOLEAN | Yes |  |
| `kitchen_backend` | Changes the Comfy Kitchen backend preference, with leave as is preserving the current setting. (default: `leave as is`) | COMBO | Yes | `"leave as is"`<br>`"auto"`<br>`"cuda"`<br>`"triton"`<br>`"eager"` |
| `anything` | Optional upstream value to order cleanup after another node and pass its value through. | * | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `anything` | Connected upstream value passed through unchanged after cleanup. | * |

Notes:

- More detail, including how this node fits with the others, is in the **Batch Timer and Refresh Page** page of the JezzWTF Documentation window (Alt+Shift+D).
