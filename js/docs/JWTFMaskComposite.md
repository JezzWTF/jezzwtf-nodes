# Mask Composite

Combine two masks: place the source on the destination at an offset and add, subtract, multiply or compare them, with opacity and a soft edge.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `destination` | The mask that is drawn on and returned, at its own size. | MASK | Yes |  |
| `source` | The mask placed on the destination. Parts that fall outside the destination are cut off. | MASK | Yes |  |
| `operation` | How the two overlap: replace, add, subtract (destination minus source), multiply, min, max, difference, or xor. (default: `add`) | COMBO | Yes | `"replace"`<br>`"add"`<br>`"subtract"`<br>`"multiply"`<br>`"min"`<br>`"max"`<br>`"difference"`<br>`"xor"` |
| `x` | Horizontal position of the source's left edge on the destination, in pixels; negative moves it off the left. (default: 0) | INT | Yes | -16384 to 16384 |
| `y` | Vertical position of the source's top edge on the destination, in pixels; negative moves it off the top. (default: 0) | INT | Yes | -16384 to 16384 |
| `opacity` | How much of the combined result replaces the destination; 0 leaves it unchanged. (default: 1.0) | FLOAT | No | 0 to 1 (step 0.01) |
| `invert_source` | Flip the source (black becomes white) before combining. (default: false) | BOOLEAN | No |  |
| `feather` | Blur the source's edges by about this many pixels before combining; 0 keeps them hard. (default: 0) | INT | No | 0 to 256 |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `MASK` | The destination with the source combined into it. | MASK |

Notes:

- More detail, including how this node fits with the others, is in the guide of the JezzWTF Documentation window (Alt+Shift+D).
