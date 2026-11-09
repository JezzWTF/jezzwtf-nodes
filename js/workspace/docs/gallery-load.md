# Gallery Load

Pick images in a floating gallery window instead of a drop-down.

## Using it

1. Click **Open gallery** on the node. The window floats over the canvas like Paste Stack: it never blocks the graph, remembers its place and size, and hides with Esc.
2. Choose the **input** or **output** folder at the top, click folders to go in, and use the breadcrumbs or `..` to come back. The filter box matches file and folder names.
3. Click an image to pick it. **Ctrl/Cmd+click** adds or removes one, **Shift+click** picks everything between your last pick and the one you clicked. **Pick all** takes every image in the current folder.
4. Picked images show their order as a badge and appear in the strip at the bottom, where the ‹ › buttons move one earlier or later in the batch and × removes it.
5. **Use picks** closes the window. Double-clicking an image uses just that image.

The node updates as you pick, so you can leave the window open while you work.

## Outputs

- `images`: the picks as one batch, every image resized to the size of the first.
- `masks`: transparency of each pick (1 where transparent; all zeros for images without alpha).
- `names`: one line per pick, `name [output]` for files from the output folder.
- `count`: how many images are in the batch.

## Good to know

- Only image files are listed (png, jpg, webp, bmp, gif, tiff). Hidden folders are skipped.
- Files are read only from inside the chosen folder. The newest images come first; a folder with more than 1500 images shows the newest and asks you to filter.
- The node re-runs when a picked file changes on disk.
