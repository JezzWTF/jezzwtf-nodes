# Get (Remote)

Pass any value across the graph by key, no wires.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `key` | Name of the Set node value to retrieve, populated by the frontend. | COMBO | Yes | choose from the list |
| `set_link` | Optional link supplied by the frontend to use the matching Set node's current output directly. | * | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `value` | Value from the linked Set output or the named store entry when no link is present. | * |

Notes:

- More detail, including how this node fits with the others, is in the **Set and Get (Remote)** page of the JezzWTF Documentation window (Alt+Shift+D).
