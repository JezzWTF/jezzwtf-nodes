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
