# Refresh Page (VRAM Cleaner)

Pass-through node that frees VRAM and reloads on demand.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `clean_vram` | Clean vram. (default: true) | BOOLEAN | Yes |  |
| `clear_cache` | Clear cache. (default: true) | BOOLEAN | Yes |  |
| `clear_node_cache` | Clear node cache. (default: false) | BOOLEAN | Yes |  |
| `kitchen_backend` | Kitchen backend. (default: `leave as is`) | COMBO | Yes | `"leave as is"`<br>`"auto"`<br>`"cuda"`<br>`"triton"`<br>`"eager"` |
| `anything` | Anything. | * | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `anything` | Anything. | * |

Notes:

- More detail, including how this node fits with the others, is in the **Batch Timer and Refresh Page** page of the JezzWTF Documentation window (Alt+Shift+D).
