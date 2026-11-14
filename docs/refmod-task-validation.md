# Reference-person generation validation

The intended task is to use saved references of a person to generate that person in substantially different poses, framing, clothing and environments. A background swap around the original portrait is insufficient evidence.

## What the implementation supplies

Image RefMod Bake stores model-specific VAE latents, plus RGB reference images for families that need them. Apply feeds these references into the target model's reference-conditioning path. There is no separate face-identity extraction, learned character representation or training stage in these image handlers. The encoded references can still carry the original backgrounds, clothing and poses.

The saved file provides a reusable reference library and avoids repeating VAE encoding. It does not add generation capabilities or identity quality beyond those available to the same model with references supplied through its normal nodes. Native reference-conditioned generation can use edit-trained models; that implementation detail alone does not establish whether a new-scene task will succeed.

## Separate acceptance checks

1. Mechanical correctness: bundle round trips, tensor layouts, model-specific conditioning, independent generation noise/target and file-change cache invalidation. CPU tests can check these.
2. Native equivalence: compare saved-reference and native conditioning with shared model, adapter, prompt, negative, format, seed, schedule and output canvas. This isolates differences between those paths; it does not establish task success.
3. Task success: inspect generated images for the same person's identity AND the requested changes to pose, framing, clothing and setting. Repeat with other scenes and seeds before claiming reliable character reuse. CPU stand-ins cannot establish this.

The MOSS diagnostic now requests a wide, full-body, side-on walking photograph at a snowy railway station, with a red coat and suitcase, on an independent 1024×768 target. It renders the saved and native paths together. Its report compares reference tensors, not identity or image quality. Both paths use the bundle's stored RGB images, so they do not independently verify original-photo selection or preprocessing before baking.

The stock MOSS SFT preset and modified checkpoints must be evaluated separately. Failure in both paths can reflect model capability, adapter loading or runtime behaviour; the comparison alone does not identify which. Existing source-checked workflow presets are not perceptual acceptance results.

## Local full-weight checks, 14 November 2026

Runtime: ComfyUI 0.45.0, RTX 4070, Qwen3.5-9B w4a8 text encoder, Flux.2 small VAE, rank-64 MOSS edit LoRA at strength 1, layer-22 negative-pass guidance. Tests used a saved close-up portrait, seed 42, 30 Euler/normal steps, CFG 4, and an independent 1024×768 output target.

| Check | Observed result |
|---|---|
| DeBand MOSS SFT: saved versus native conditioning | Saved and native decoded images were pixel-identical. Both followed the new station scene, but lost the source subject's bald head and beard. The reference-person task failed. |
| Stock MOSS SFT: saved versus native conditioning | Saved and native decoded images were again pixel-identical and again failed to preserve those subject features. |
| Stock MOSS SFT: references versus no references | Outputs differed (mean absolute 8-bit RGB difference approximately 34.38). References affected the output; that influence did not establish identity preservation. |
| Saved MOSS latents versus native re-encoding | Same shapes and maximum absolute tensor difference 0 for this bundle and VAE. |

These are observations for one prompt, reference and seed, not a universal limitation of MOSS. They establish that a native-equivalent path can still fail the requested character-generation task. A comparison report must not label native equivalence as feature success.

### Flux.2 Klein Base 4B

The same portrait was separately baked with the full Flux.2 VAE, then tested with Klein Base 4B, Qwen3-4B, Euler, a 20-step Flux2Scheduler, CFG 5, seed 42, and the same 1024×768 station-scene prompt. Saved-reference and native VAE Encode + Set Reference Latent paths produced pixel-identical decoded images. The result changed the pose, outfit, framing and setting while retaining the source's bald head, beard and visible facial markings. The no-reference control instead produced a subject with hair and no beard or those markings (8-bit RGB MAE approximately 23.24 versus the saved-reference result).

This is positive evidence for this reference-person task with this setup. It is not a calibrated identity score or a general guarantee. `RefMod_Character_New_Scene_Flux_2.json` uses this tested generation path and an explicit output target independent of reference dimensions.

A second saved-reference render used seed 7 and requested a seated café scene, blue linen shirt, visible hands and a coffee cup. It retained the bald head, beard and visible facial markings while producing the new clothing, hand interaction and environment. The face expression did not fully follow the requested relaxed smile. Thus even this successful reference path has prompt-adherence limits; visual review remains necessary.

### Reference-conditioned enlargement and refinement

A later full-weight test used a user's generated 1024×768 image and its four-reference Flux.2 bundle. The image was resized with Lanczos to a 1.69-megapixel target on a 16-pixel grid (1536×1152), encoded with the same Flux.2 VAE, and refined with the original scene prompt, CFG 5, Euler, seed 7 and all references active. A size-aware 100-step Flux2Scheduler fed the low-sigma tail of SplitSigmasDenoise at 0.20, giving 20 refinement steps. The sampler started from the enlarged image's encoded samples, not from an empty target.

The run completed in approximately 246.5 seconds on the RTX 4070. Visual comparison showed retained composition and main facial features with modest texture cleanup; facial tattoo lettering was not exact. This demonstrates that references can remain active during refinement, not guaranteed recovery of original face detail or a universal cure for cross-hatching.

The Flux 3 refinement examples have graph/schema checks. The Distilled example explicitly selects `flux3-image-klein-int8-convrot.safetensors`, CFG 1 and 16 refinement steps; its low-denoise generation quality has not been checked with full weights. It should not be described as a validated equivalent of the tested Flux.2 run.
