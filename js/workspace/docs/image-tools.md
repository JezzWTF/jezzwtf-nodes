# Image comparison, saving and mask editing

## Image Compare

Connect `image_a` and `image_b`, then run. The node offers Wipe, Blend, Difference and Toggle modes. An optional `mask` enables Mask mode: white shows B, black shows A, and gray blends them. Drag the wipe or use its slider; the frame selector browses batches.

B is resized to A's dimensions. Shorter batches repeat to match the longer batch. The `difference` output is the full-resolution absolute RGB difference, and `metrics` contains per-frame MAE and PSNR in JSON. Identical images have infinite PSNR, represented as `null` in JSON and ∞ in the panel. The panel previews the first 32 frames at up to 1024px; the outputs and metrics cover the whole batch.

## Image Saver (Smart Squeeze)

Connect an image batch and choose PNG, WebP, JPEG, AVIF or TIFF. Files are written beneath ComfyUI's output folder using `filename_prefix`, with counters so existing files are kept. Outputs include the original images, saved paths and a JSON report.

With Smart Squeeze on, quality tiers 5–10 set local colour SSIM targets of 0.95, 0.97, 0.98, 0.99, 0.995 and 1.0. The bounded search keeps the smallest tested encoding meeting the target. Similarity is measured at up to 1024px with a 7×7 local window; inspect fine textures at full size if they matter to the output.

PNG and TIFF are lossless. PNG can use an exact palette when smaller. WebP also tries lossless encoding. JPEG or AVIF may be unable to meet the selected target even at maximum quality; `target_met: false` in the report makes this explicit. Tier 10 does not promise lossless JPEG or AVIF. With Smart Squeeze off, `quality` controls lossy encoding directly.

PNG, WebP, AVIF and TIFF retain alpha; JPEG composites transparent pixels over white. AVIF requires a Pillow build with AVIF writing support. `embed_workflow` embeds prompt and workflow metadata in PNG files only. Previewing the saved file uses ComfyUI's normal image preview.

## Mask Editor

Connect `images`, optionally an incoming `mask`, and run once to load the editor. Paint white to select a region or use Erase to paint black. White means masked/inpaint. Brush radius is measured in source pixels, and pen pressure changes its size.

The editor has Undo, Clear, Fill, Mask view and zoom. Use the viewport's scrollbars to move around a zoomed image. Edits save automatically as grayscale PNGs under `input/jezzwtf_masks/`; a pending save finishes before a workflow is queued. The saved mask is restored with the workflow. The image background is refreshed on the next run.

Until painting is saved, incoming masks are used and repeated across the image batch as needed. A saved painting overrides the incoming mask and applies to every image in the batch; it is resized to the images' dimensions if needed. `invert` and `feather` affect the returned mask without changing the raw painting. Outputs are the original images, the MASK and an RGB preview of the mask.

To return to the incoming mask, click **Use input mask** and run again. Clear in the painting toolbar produces a saved all-black mask.
