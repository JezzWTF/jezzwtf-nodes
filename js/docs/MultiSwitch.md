# Multi Switch

Switch several values at once: each true/false pair feeds its own output, and one switch flips them all. Only the chosen side of each pair is computed.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `switch` | false passes every pair's false input through, true passes every pair's true input. Can also be wired in from another node. (default: false) | BOOLEAN | Yes |  |
| `false_1` | Pair 1: passed to output 1 while the switch is false. | ANY (matches what is connected) | No |  |
| `true_1` | Pair 1: passed to output 1 while the switch is true. | ANY (matches what is connected) | No |  |
| `false_2` | Pair 2: passed to output 2 while the switch is false. | ANY (matches what is connected) | No |  |
| `true_2` | Pair 2: passed to output 2 while the switch is true. | ANY (matches what is connected) | No |  |
| `false_3` | Pair 3: passed to output 3 while the switch is false. | ANY (matches what is connected) | No |  |
| `true_3` | Pair 3: passed to output 3 while the switch is true. | ANY (matches what is connected) | No |  |
| `false_4` | Pair 4: passed to output 4 while the switch is false. | ANY (matches what is connected) | No |  |
| `true_4` | Pair 4: passed to output 4 while the switch is true. | ANY (matches what is connected) | No |  |
| `false_5` | Pair 5: passed to output 5 while the switch is false. | ANY (matches what is connected) | No |  |
| `true_5` | Pair 5: passed to output 5 while the switch is true. | ANY (matches what is connected) | No |  |
| `false_6` | Pair 6: passed to output 6 while the switch is false. | ANY (matches what is connected) | No |  |
| `true_6` | Pair 6: passed to output 6 while the switch is true. | ANY (matches what is connected) | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `output 1` | The chosen side of pair 1; it has the type of what is connected. | ANY (matches what is connected) |
| `output 2` | The chosen side of pair 2; it has the type of what is connected. | ANY (matches what is connected) |
| `output 3` | The chosen side of pair 3; it has the type of what is connected. | ANY (matches what is connected) |
| `output 4` | The chosen side of pair 4; it has the type of what is connected. | ANY (matches what is connected) |
| `output 5` | The chosen side of pair 5; it has the type of what is connected. | ANY (matches what is connected) |
| `output 6` | The chosen side of pair 6; it has the type of what is connected. | ANY (matches what is connected) |

Notes:

- More detail, including how this node fits with the others, is in the **Switch, Route and Multi Switch** page of the JezzWTF Documentation window (Alt+Shift+D).
