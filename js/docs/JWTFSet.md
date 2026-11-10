# Set (Remote)

Pass any value across the graph by key, no wires.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `key` | Name under which the value is stored and matched by Get nodes. (default: lora) | STRING | Yes |  |
| `value` | Data from any socket type to store under the chosen key. | * | Yes |  |
| `color` | Canvas colour theme associated with the named value. (default: `Default`) | COMBO | Yes | choose from the list |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `pass_through` | The same value that was stored under the chosen key. | * |

Notes:

- More detail, including how this node fits with the others, is in the **Set and Get (Remote)** page of the JezzWTF Documentation window (Alt+Shift+D).
