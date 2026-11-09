# Title Font

Styled title banner for organising workflows.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `text` | Text. (default: TITLE) | STRING | Yes |  |
| `font_size` | Font size. (default: 56) | INT | Yes | 8 to 240 |
| `bold` | Bold. (default: true) | BOOLEAN | Yes |  |
| `glow` | Glow. (default: true) | BOOLEAN | Yes |  |
| `style` | Style. (default: `Gradient`) | COMBO | Yes | `"Solid"`<br>`"Gradient"`<br>`"Neon"`<br>`"Rainbow"`<br>`"Outline"`<br>`"Chrome"` |
| `color_a` | Color a. (default: #ff3d7f) | STRING | Yes |  |
| `color_b` | Color b. (default: #3da5ff) | STRING | Yes |  |
| `animate` | Animate. (default: `None`) | COMBO | Yes | `"None"`<br>`"Pulse"`<br>`"Float"`<br>`"Shimmer"`<br>`"Rainbow Shift"`<br>`"Glow Pulse"` |
| `url` | Url. | STRING | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `TEXT` | Text. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Text nodes** page of the JezzWTF Documentation window (Alt+Shift+D).
