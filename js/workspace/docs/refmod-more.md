# Tail and Image RefMod

## Tail RefMod, Tail Capture and Tail Load

Carry a character or look from the end of one clip into the next. **Tail Capture** saves the last frames of a clip, **Tail Load** reads them back, and **Tail RefMod** applies them as a reference when you continue a video.

## Image RefMod Bake

Bake encodes references through the model's own VAE into a reusable `.safetensors` bundle. Each file records its model family and reference dimensions. Use the VAE matching the family and checkpoint.

## Image RefMod Apply

Apply detects the family from the bundle and uses its conditioning path. Bundles from different families cannot be mixed. Existing Qwen Image 2.1, Fibo 2 and Flux 3 bundles continue to work.

| Family | Apply inputs and requirements |
|---|---|
| Qwen Image 2.1 / Fibo 2 | The matching CLIP. Prompts and saved RGB references are encoded together. |
| Flux 3 / Flux.2 / Flux.1 Kontext | Connect upstream positive conditioning; negative is optional. References are attached as raw VAE latents. Kontext uses the 16-channel Flux VAE, Flux.2/3 the matching 128-channel VAE. |
| MOSS-Image Edit | Connect the matching CLIP and edit LoRA. The official ComfyUI adapter uses **Moss-Image-Edit**; ai-toolkit adapters need their own trained layout. |
| Krea 2 Edit | Connect Krea 2 CLIP and use a reference-image edit LoRA. Choose the ai-toolkit cache setting used for training. The VAE uses 16 channels and 8× spatial compression; saved single-image latents retain their temporal dimension. Current ComfyUI has a native Krea reference path; older builds need updating or the matching Ostris edit patch. |
| LTX Video | Saved **single-image guides**, using the 128-channel LTX VAE. Connect `positive`, `negative`, `vae` and the target video `latent_in`. Requires a ComfyUI build with **LTXV Add Latent Guide**. |

For image families, `ref_strength` is the fraction of the denoising schedule during which references are active. It is not a multiplier on the saved latent pixels. `ref_on_negative` controls whether negative conditioning also receives references. MOSS and generic ai-toolkit vision references are capped at 384×384 pixels of area. The native Krea style layout scales vision references to that area, including small inputs, matching Qwen Edit Plus. Full encoded references remain in the bundle.

### LTX guide workflow

1. Bake reference images with model `ltxv`, using the LTX VAE.
2. Apply them to an existing video latent through `latent_in`, with both conditionings and the VAE connected.
3. Set `latent_idx` in **latent frames**, and `guide_strength` between 0 and 1. Multiple saved images are attached at that location. Strength 0 leaves the target unchanged.
4. Sample using the returned latent and conditionings.
5. Use ComfyUI's **LTXV Crop Guides** before decoding to remove appended guide frames.

Guide placement delegates to the native node, which carries the position and guide-attention metadata. Spatial guide sizes must divide the target by the same integer on both axes. Split combined audio/video latents before applying guides, then use the appropriate AV workflow to join them. This handler stores still references; temporal guide clips and IC-LoRA-specific controls are not exposed here.

## Reference Audition

Use a controlled comparison to see what each reference contributes. Connect a **clean, batch-one target latent**, the matching model and VAE, and choose a saved RefMod bundle. Do not apply references upstream. Image families and LTX appear under their normal library names; H3 bundles are prefixed `H3:`.

The baseline uses every reference. Following trials omit reference 1, reference 2, and so on, while keeping the prompt, seed, sampler settings and original target latent fixed. Image-aware prompt conditioning is encoded again for each subset. A one-reference bundle produces a full-reference baseline and a text-only omission.

`max_renders` includes the baseline. `time_budget_seconds` is a **soft limit**, checked between trials: a render already running finishes, then no further trial starts. Zero disables the time limit. The report lists skipped omissions explicitly; it never invents results for them. User cancellation stops execution immediately through ComfyUI's normal cancellation path.

The labeled contact sheet shows every completed case. Video cases show the first, middle and last decoded frames, rather than full playback. **Change measures influence, not improvement, identity fidelity or image quality.** It is mean absolute RGB change on the preview strips, including letterboxing. Compare visually before choosing references to keep. Audio is not scored or previewed; H3 audio references may influence the rendered video, but this node does not evaluate their sound.

For Qwen/Fibo/MOSS/Krea, connect `clip` and use the prompt widgets inside Audition. For Flux, connect clean positive/negative text conditioning. MOSS/Krea also need a matching edit LoRA in the model path; `edit_format` must match its training. Use matching model components and target channels for each family.

Connect `sigmas` to preserve the exact schedule from a working workflow. It overrides Audition's steps, scheduler and denoise widgets for every trial. The Flux.2 example uses native **Flux2Scheduler**, with dimensions matching the fixed target. Choose the schedule's steps for your exact dev/Klein/base/distilled checkpoint. Replace or disconnect that schedule when adapting the example to another model family.

The shipped Flux.2 Apply and Audition examples specifically target **Klein Base 4B**, using `qwen_3_4b.safetensors`, Euler, Flux2Scheduler at **20 steps**, and **CFG 5**, matching ComfyUI's Base 4B edit template. **CFG 1 disables classifier-free guidance**; it is not the Base preset. Distilled Klein and Flux.2 dev have different sampling and/or text-encoder requirements. A text encoder loading successfully does not establish that it is the checkpoint's intended encoder.

The other Apply examples also target named variants: **Qwen Image 2.1** at 25 steps/CFG 1; **Fibo 2 Dev** at 50/5; **Flux 3 Klein Base** at 50/1; **Krea2 Turbo Style Reference** at 8/1; **MOSS SFT Edit** at 30/4; and **Kontext Dev** at 20/1 with embedded Flux guidance 2.5. The Krea style preset uses `krea2_style_reference.safetensors`, **Krea2 style reference** conditioning and a 1024×1024 ModelSamplingFlux patch. This layout follows the native Qwen Edit Plus template used by ComfyUI's Krea blueprint; the existing ai-toolkit layouts remain available for separately trained adapters. Krea's preset transfers style and does not promise character identity.

At the default bake resolution 1024, Fibo references use the native trained-size/crop policy, and Kontext uses native FluxKontextImageScale buckets. To match those corrected defaults, rebake existing Fibo/Kontext bundles produced with the earlier generic resize. Other resolutions remain custom settings. Fibo negative text follows the native chat template, with an empty negative retaining its trained null caption.

The LTX examples target **ltx-video-2b-v0.9.5.safetensors**, sharing the checkpoint's own VAE between Bake and Apply. They use **LTXVScheduler**, 30 steps, CFG 3, shifts 2.05/0.95, stretch enabled and terminal 0.1. The clean 512×512/49-frame target drives the schedule; appended guides are cropped before decode. This video-only preset is separate from LTX-2 AV workflows.

MOSS requires current native **Text Encode MOSS-Image Edit** support; older installs stop with an actionable error. The shipped MOSS Apply graph uses ComfyUI's official `moss_image_edit_lora_rank_64_bf16.safetensors` through **LoraLoaderModelOnly**, at strength 1.0, with **Moss-Image-Edit**. This adapter's metadata identifies the `moss-edit-lora` format and `ref-prefix-only-t0__target-text-original-moss-v1` contract. Either ai-toolkit layout is a mismatch for these weights. Use ai-toolkit layouts only with adapters trained for them; changing the conditioning format does not convert the weights. The official adapter is trained for instruction editing, rather than guaranteed identity transfer into arbitrary scenes.

For LTX, connect clean video prompt conditioning and a target video latent. Guides are cropped before decode. Audition uses **Euler** and generates the target noise independently of the appended guide frames, keeping target noise identical as guide counts change. `latent_idx` and `ref_strength` control guide placement and strength. For H3, connect H3 prompt conditioning and a plain video target; split nested AV latents first. `ref_strength` is H3 retention, applied to positive and optionally negative conditioning.

The Flux.2 setup in **RefMod_Reference_Audition.json** is a complete starting workflow with loader placeholders, fixed target, contact sheet, report and selection saver. Adapt the model components and target latent together for other families. Low-step screening results can change with seed, scene or production sampling settings.

## Save Audition Selection

Connect the `audition` output, enter the **1-based source reference numbers to keep**, and choose a new bundle name. `all` keeps everything; `1,3` keeps the first and third references in that order. Saving starts disabled. Enable `save` after inspecting the contact sheet; overwrite is also off by default.

This node only reads and saves encoded reference tensors. Changing its selection does not change the upstream Audition inputs, so ComfyUI can reuse the completed trials while their cache is retained. Cache eviction or changing upstream inputs can require another audition.

The source file is always preserved. Its content and any legacy metadata sidecar are checked against the audition fingerprint before saving. If either changed, run the audition again. Selected tensors and per-reference metadata are renumbered into a compatible image/LTX or H3 bundle; no VAE re-encoding is performed. A non-image bundle thumbnail is removed if its original first reference is no longer first. Refresh node definitions if the saved bundle does not appear in another node's picker yet.

## H3 Clip Doctor

Connect an H3 video or nested AV latent to check channels, batch size, finite values, frame mapping and FPS metadata. Optional decoded `images` and `audio` are checked against the latent's expected size and duration. A plain 32-channel H3 AV placeholder is accepted with a warning: the H3 sampler expands it into the two streams.

H3 maps **5k+2 latent frames to 17k+5 pixel frames**; a single still uses 1→1. For example T=2 means 5 decoded frames, T=7 means 22, and T=12 means 39. Intermediate token lengths are reported as invalid. `spatial_compression` defaults to 16 and must match the VAE.

By default this is a strict preflight check. Disable `strict` to return the report without stopping execution. Enable `auto_fix` to correct mismatched FPS metadata, resize/trim/pad decoded images to the latent, and trim/zero-pad decoded audio to its duration. The encoded samples are kept intact; malformed encoded latents must be fixed upstream. Optional media outputs are empty when their inputs are absent.
