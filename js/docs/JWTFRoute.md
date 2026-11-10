# Route

Send one input to either the true or the false output with a true/false switch. Whatever hangs off the other output is skipped for this run.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `switch` | true sends the value out of the true output, false out of the false output. Can also be wired in from another node. (default: false) | BOOLEAN | Yes |  |
| `value` | The value to send on. | ANY (matches what is connected) | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `true` | The value while the switch is true. While it is false, nodes connected here do not run. | ANY (matches what is connected) |
| `false` | The value while the switch is false. While it is true, nodes connected here do not run. | ANY (matches what is connected) |

Notes:

- More detail, including how this node fits with the others, is in the **Switch, Route and Multi Switch** page of the JezzWTF Documentation window (Alt+Shift+D).
