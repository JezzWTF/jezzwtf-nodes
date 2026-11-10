# Title Font

Styled title banner for organising workflows.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `text` | Text shown in the canvas title and returned to downstream nodes. (default: TITLE) | STRING | Yes |  |
| `font_size` | Canvas title size in pixels. (default: 56) | INT | Yes | 8 to 240 |
| `bold` | Draws the canvas title in bold when enabled. (default: true) | BOOLEAN | Yes |  |
| `glow` | Adds a glow to the canvas title when enabled. (default: true) | BOOLEAN | Yes |  |
| `style` | Visual treatment applied to the canvas title. (default: `Gradient`) | COMBO | Yes | `"Solid"`<br>`"Gradient"`<br>`"Neon"`<br>`"Rainbow"`<br>`"Outline"`<br>`"Chrome"` |
| `color_a` | Primary hex colour used to render the title. (default: #ff3d7f) | STRING | Yes |  |
| `color_b` | Secondary hex colour used by title styles with two colours. (default: #3da5ff) | STRING | Yes |  |
| `animate` | Canvas title animation, with None leaving it static. (default: `None`) | COMBO | Yes | `"None"`<br>`"Pulse"`<br>`"Float"`<br>`"Shimmer"`<br>`"Rainbow Shift"`<br>`"Glow Pulse"` |
| `url` | Optional link opened from the canvas title. | STRING | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `TEXT` | Title text passed through as a plain string. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Text nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
