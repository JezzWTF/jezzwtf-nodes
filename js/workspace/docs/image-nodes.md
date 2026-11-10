# Image nodes

## Match Image Size

Resizes or pads one image to the size of another (or a size you give). Several fit modes cover stretch, fit, fill and pad. Its `mask` output is the first channel of the result.

## Get Image

Grabs an image from elsewhere in the graph and outputs it as IMAGE and MASK (from alpha, luminance, or blank).

## Draw Image

A layered sketch pad that loads like Load Image. It supports pen pressure, zoom and pan, undo (25 steps), up to 12 layers and a colour wheel. Drawings are saved to `input/jezzwtf_draw/`.

## Multi Load Image

Up to 16 image slots, each with its own output. Upload, paste or drop images, hover to peek, and click for a full-screen view.

## Image Aspect Size

Outputs a size that keeps an image's aspect ratio inside a target.

## Mask Composite

Combines two masks. The `source` is placed on the `destination` with its top-left corner at `x`, `y` (negative values move it off the top or left), and the parts that fall outside the destination are cut off. The result is the destination's size.

- `operation`: *replace*, *add*, *subtract* (destination minus source), *multiply*, *min*, *max*, *difference* or *xor*. Values always stay between 0 and 1.
- `opacity` controls how much of the combined result replaces the destination; 0 leaves it unchanged.
- `invert_source` flips the source first, and `feather` blurs its edges by about that many pixels so the join is soft.
- A batch on either side repeats against a shorter one, so one source mask can be applied to every mask in a batch.
