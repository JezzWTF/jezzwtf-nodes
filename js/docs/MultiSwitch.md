# Multi Switch

Route several values by one switch.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `switch` | Selects the true inputs when enabled and the false inputs when disabled, routing each slot to its corresponding output. (default: false) | BOOLEAN | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `output_1` | Passes through true_1 when the switch is true or false_1 when it is false, returning no value if that input is disconnected. | * |
| `output_2` | Passes through true_2 when the switch is true or false_2 when it is false, returning no value if that input is disconnected. | * |
| `output_3` | Passes through true_3 when the switch is true or false_3 when it is false, returning no value if that input is disconnected. | * |
| `output_4` | Passes through true_4 when the switch is true or false_4 when it is false, returning no value if that input is disconnected. | * |
| `output_5` | Passes through true_5 when the switch is true or false_5 when it is false, returning no value if that input is disconnected. | * |
| `output_6` | Passes through true_6 when the switch is true or false_6 when it is false, returning no value if that input is disconnected. | * |

Notes:

- More detail, including how this node fits with the others, is in the guide of the JezzWTF Documentation window (Alt+Shift+D).
