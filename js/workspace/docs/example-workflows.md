# Example workflows

**Smart_Select_Mask_Editor.json** uses a separate WeVisOne-VL perception checkpoint to select a subject described in words, with an editable mask and detection report. Current ComfyUI detects the architecture automatically with CLIPLoader type `stable_diffusion`.

**Smart_Select_Face_Refine_Flux_2.json** selects a face, enlarges its padded crop, VAE-encodes those pixels and samples the whole crop with a saved Flux.2 reference bundle, then blends through the selection mask into the original image. The soft matte is not used as a latent noise mask because it suppresses redraw repeatedly during sampling. Select the original scene prompt and matching Klein Base 4B components. It processes one region at a time and retains the source image's final resolution. Inspect both crop-scale and final-image comparisons. Denoise 0.20 is conservative; 0.35 makes stronger changes that may alter identity and markings. This is generative refinement, with no guarantee of recovered facial detail.

Open the **Workflows** window and pick the **JezzWTF examples** category, or drag a file from the repository's `example_workflows` folder into ComfyUI. ComfyUI also lists them in its Templates browser under this pack.

| Workflow | What it does | Needs |
|---|---|---|
| Character Creator | Qwen3.5 writes a Character Card V2 from a concept, bakes it with your portrait, then chats with it | Qwen3.5 |
| Character Chat | The minimal chat setup | Qwen3.5 and a character card |
| Video to GIF Optimised | Load a video and optimise it to a size budget | Nothing beyond core |
| GIF Optimise and Compare | Load a GIF, re-encode it, compare with the original in Video Compare | Nothing beyond core |
| Dataset Captioning | Caption a whole folder of images and save a `.txt` next to each | Qwen3.5 |
| RefMod Bake and Apply (H3) | Bake a portrait into a RefMod and use it in H3 reference-to-video | MiniMax H3 reference model, text encoder and VAEs |
| RefMod Bake Image Families | Bake a reusable bundle for Qwen 2.1, Fibo 2, Flux 3, Flux.2, Flux Kontext, MOSS or Krea 2 | Reference image and matching VAE |
| RefMod Bake LTX Guide | Fit and bake a 512×512 image guide | Reference image and LTX video VAE |
| RefMod Apply Qwen Image 2.1 / Fibo 2 | Encode prompts with saved references, sample and save | Qwen 2.1 at 25 steps/CFG 1; Fibo 2 Dev at 50/5; named encoder and VAE |
| RefMod Apply Flux Kontext / Flux 2 / Flux 3 | Attach saved references to text conditioning, sample and save | Kontext Dev at 20/1 plus guidance 2.5; Flux.2 Klein Base 4B at 20/5; Flux 3 Klein Base at 50/1 |
| RefMod Apply MOSS Image / Krea 2 | Reference-guided generation with the named adapter | MOSS SFT Edit at 30/4; Krea2 Turbo Style Reference at 8/1; matching reference format |
| RefMod Apply LTX Video | Apply a saved guide, sample, crop before decode, save a WebM | Saved 512×512 guide and ltx-video-2b-v0.9.5 checkpoint with bundled VAE |
| RefMod Reference Audition | Compare a full bundle against individual omissions, then save chosen references | Saved Flux.2 bundle, model, encoder and matching VAE |

Each workflow has a "How it works" note. Pick your own file in the loader node first: the shipped placeholder names (`your.gif`, `example.png`) will not exist on your machine.

## Reference person in a new scene

Open **RefMod_Character_New_Scene_Flux_2.json** for the character-reference task: use the person from saved references in a new pose, outfit, framing and environment. It targets **Flux.2 Klein Base 4B**, Qwen3-4B and the full Flux.2 VAE, with an independent 1024×768 canvas, Euler, 20-step Flux2Scheduler and CFG 5. This path has been checked in full-weight generation with a saved portrait. Choose a **Flux.2** bundle; a MOSS bundle must be baked separately for Flux.2 from the same source photos. The saved file does not convert between model families or add identity-training capabilities.

The tested saved-reference result matched native reference conditioning pixel-for-pixel and retained visible subject features that disappeared in the no-reference control. That is evidence for this specific setup, not a promise of exact identity for every scene. Inspect the face and the requested composition changes together. Keep output dimensions and scheduler dimensions matched when changing the canvas.

## Upscale with the saved references

**RefMod_Upscale_Refine_Flux_2.json**, **RefMod_Upscale_Refine_Flux_3.json** and **RefMod_Upscale_Refine_Flux_3_Distilled.json** start from a generated image, enlarge it, VAE-encode those enlarged pixels, then perform a low-denoise refinement while applying the saved references again. They use the original scene prompt and a bundle for the same model family. The unsuffixed Flux 3 example targets **Klein Base**. The **Distilled** example names `flux3-image-klein-int8-convrot.safetensors`, uses CFG 1 and 16 refinement steps, and still needs full-weight refinement validation with that checkpoint.

The default target area is 1.69 megapixels, approximately 1536×1152 for a 1024×768 source, with aspect ratio retained and dimensions snapped to a 16-pixel grid. Flux.2 schedule dimensions are connected to the actual resized image. Its 100-step full schedule is split at denoise 0.20; the **low_sigmas** output gives 20 refinement steps. Flux 3 uses its model's simple schedule with 20 Base or 16 Distilled refinement steps at denoise 0.20. Use a full scene caption for Flux 3, matching the original generated image; the official workflows expand short requests before sampling.

Keep `ref_strength=1` so references remain active throughout this late-schedule pass. Reducing a reference's schedule fraction can deactivate it before the refinement starts. Start with denoise 0.20 and adjust cautiously toward 0.30: more redraw can improve texture but change the face, tattoos or pose. Diffusion synthesizes plausible detail; it cannot guarantee recovery of original facial detail. If the face is small in the frame, consider a subsequent face-crop refinement rather than repeatedly enlarging the whole image.

## MOSS comparison

If MOSS ignores an edit instruction or reproduces the reference, open **RefMod_Diagnose_MOSS_Image.json**. Restart ComfyUI to load **RefMod Conditioning Check (MOSS)**, select the existing bundle and matching model files, then queue once. The graph renders both the saved-reference path and native MOSS editing from the bundle's stored RGB references. One prompt feeds both paths; model, LoRA, target latent, seed and sampling settings are shared. The report compares baked and freshly encoded reference tensors. This isolates reference handling from failures also reproduced by native editing; it does not establish identity quality or claim a fix.

## Running the new RefMod examples

1. Run the relevant **Bake** example first. For image families, change the model choice and choose its matching VAE. LTX has a separate bake example to match its guide dimensions to the video target.
2. Open the corresponding **Apply** example and choose your installed model files. `YOUR_*.safetensors` values are setup placeholders.
3. Refresh node definitions with **R** if needed, then choose the saved bundle in Image RefMod Apply, for example `moss_image/example_character`. Leave the model on **auto (from refmod)**. None deliberately stops execution until a reference is selected.
4. Set the prompt and run. Image examples save beneath `output/refmods/<family>/`; the LTX example saves a WebM.

The Flux.2 Apply and Audition examples target **Klein Base 4B**, with `qwen_3_4b.safetensors`, **CFG 5**, Euler and a **20-step Flux2Scheduler**. Keep scheduler dimensions matched to the target latent. Distilled Klein and Flux.2 dev require their own model and sampling setup; CFG 1 disables classifier-free guidance and is not the Base preset.

Match `edit_format` to the adapter's training. MOSS uses the official `moss_image_edit_lora_rank_64_bf16.safetensors` with **Moss-Image-Edit** and visible SLG layer 22. Krea uses `krea2_style_reference.safetensors` with **Krea2 style reference** and a visible ModelSamplingFlux patch. LTX uses a 512×512, 49-frame, 24fps target and **LTXVScheduler**; keep **LTXV Crop Guides** between sampling and decode. The Bake and Apply examples use the same checkpoint VAE. See the Tail and Image RefMod page for requirements, and `docs/refmod-workflow-audit.md` in the repository for the source audit and validation limits.
