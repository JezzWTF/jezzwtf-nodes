# Image comparison, saving and mask editing

## Smart Select (WeVisOne)

Describe a region such as `face`, `person` or `hair`. The node uses ComfyUI's native WeVisOne-VL support. Install `wevisone_vl_2b_int8_convrot.safetensors` from [Comfy-Org/WeVisOne-VL](https://huggingface.co/Comfy-Org/WeVisOne-VL) in `models/text_encoders`, refresh the model list and load it with CLIPLoader. Keep the loader type at `stable_diffusion`: current core detects the architecture from the weights. This perception model is separate from the generation text encoder. Older ComfyUI versions need an update for native support.

Segmentation returns the model's alpha mattes; detection returns rectangular masks. Largest selects the largest valid box per frame, All combines every match, and Index selects the native detector's zero-based detection index. The report includes the native answer and match counts. Review the mask: detection does not identify a specific person and may select background faces. No match yields empty boxes and a black mask.

Each image in a batch is detected separately. Feed the output into Mask Editor for corrections. Click **Use input mask** to restore automatic selection after painting; Clear saves an all-black painting. See `Smart_Select_Mask_Editor.json` for a standalone example.

## Region Crop (Refine)

Connect the original image, selected boxes and selection mask. Choose the source frame and region index. Padding adds context on each side as a fraction of the box dimensions. The long edge defaults to 768 pixels, with both crop dimensions rounded to a 16-pixel grid. The node outputs the enlarged RGB crop, its mask and a region context that records the original position and mask.

Boxes determine the bounds when connected. To derive bounds entirely from a painted mask, disconnect the boxes. An empty selection stops execution. This node processes one region at a time; All in Smart Select does not automatically refine every detected face.

## Region Composite (Refine)

Feed the refined crop and the crop node's region context into Region Composite, alongside the **same original image**. The node restores the crop to its original size and blends through the original selection mask. Feather is measured in source-image pixels and softens both selection and crop boundaries; opacity controls the blend. Other frames, pixels outside the padded crop and original alpha channels are retained. Feathering can affect pixels just outside the original selection, within the crop.

`Smart_Select_Face_Refine_Flux_2.json` VAE-encodes the enlarged crop and refines the whole padded crop with Flux.2 Klein Base 4B and a matching saved RefMod bundle. The selection mask is used only at pasteback. Feeding the soft matte into Set Latent Noise Mask repeatedly blends toward the original latent during sampling and suppresses the effect, especially in gray areas such as beard and scalp.

Denoise 0.20 is a conservative redraw. A same-seed comparison at 0.35 produces stronger changes, including changes to facial markings; it is not a guaranteed detail improvement. Use the original scene prompt and inspect the crop-scale comparison as well as the final composite. A successful run, changed pixels or sharper-looking lines do not establish identity preservation or recovered original detail.

The composite retains the input resolution. Enlarge the whole input first when a larger final image is needed; crop refinement alone improves the working resolution of the selected face.

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
