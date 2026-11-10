# Switch

Pick one of two inputs with a true/false switch. The output takes the type of what you connect, and only the chosen side is computed.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `switch` | true passes the true input through, false passes the false input. Can also be wired in from another node. (default: false) | BOOLEAN | Yes |  |
| `if_true` | Passed through when the switch is true. Not computed while the switch is false. | ANY (matches what is connected) | No |  |
| `if_false` | Passed through when the switch is false. Not computed while the switch is true. | ANY (matches what is connected) | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `output` | The chosen input, unchanged; it has the same type as what is connected. | ANY (matches what is connected) |

Notes:

- More detail, including how this node fits with the others, is in the **Switch, Route and Multi Switch** page of the JezzWTF Documentation window (Alt+Shift+D).
