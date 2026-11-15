# RefMod workflow audit

Reviewed 2026-11-12: the 11 RefMod workflows added in this change, plus the two personalized corrected copies extracted from the reported MOSS/Flux runs. Existing tracked examples, including the older H3 workflow, were outside this change's scope.

## Source comparison

Primary reference: [ComfyUI workflow templates at a8bc07a](https://github.com/Comfy-Org/workflow_templates/tree/a8bc07a76478dfada740fa8fa49ac87be1bff519/templates), checked against the corresponding native node implementations in ComfyUI revision `74eb0c4`. A compact record of the source presets is in `tests/refmod_h3/fixtures/workflow_presets.json`.

| Example | Explicit target and checked preset | Primary template |
|---|---|---|
| RefMod_Apply_Qwen_Image_2_1 | Qwen Image 2.1; Qwen3-VL-8B; Qwen 2.1 VAE; Euler/simple, 25 steps, CFG 1 | [Qwen 2.1 edit](https://github.com/Comfy-Org/workflow_templates/blob/a8bc07a76478dfada740fa8fa49ac87be1bff519/templates/image_qwen_image_2_1_image_edit.json) |
| RefMod_Apply_Fibo_2 | Fibo 2 Dev; Qwen3-VL-4B; Flux.2 VAE; Euler/simple, 50 steps, CFG 5; native negative template and trained reference sizes | [Fibo Dev edit](https://github.com/Comfy-Org/workflow_templates/blob/a8bc07a76478dfada740fa8fa49ac87be1bff519/templates/image_fibo2_edit_dev_pe.json) |
| RefMod_Apply_Flux_3 | Flux 3 Klein Base; Qwen3-VL-4B in flux3 mode; Flux.2 VAE; Euler/simple, 50 steps, CFG 1 | [Flux 3 Base edit](https://github.com/Comfy-Org/workflow_templates/blob/a8bc07a76478dfada740fa8fa49ac87be1bff519/templates/image_flux3_klein_image_edit.json) |
| RefMod_Apply_MOSS_Image | MOSS SFT; Qwen3.5-9B; Flux.2 small VAE; official rank-64 edit LoRA, Moss-Image-Edit; SLG layer 22; Euler/normal, 30 steps, CFG 4 | [MOSS Edit](https://github.com/Comfy-Org/workflow_templates/blob/a8bc07a76478dfada740fa8fa49ac87be1bff519/templates/image_moss_image_edit.json) |
| RefMod_Apply_Krea_2 | Krea2 Turbo; Qwen3-VL-4B; Qwen image VAE; official style LoRA; native edit-prompt template and index_timestep_zero; ModelSamplingFlux 1.15/0.5 at 1024 square; Euler/simple, 8 steps, CFG 1 | [Krea Turbo style reference](https://github.com/Comfy-Org/workflow_templates/blob/a8bc07a76478dfada740fa8fa49ac87be1bff519/templates/image_krea2_turbo_int8_image_style_reference.json) |
| RefMod_Apply_Flux_Kontext | Kontext Dev; CLIP-L + T5; Flux VAE; native reference size buckets; embedded guidance 2.5; Euler/simple, 20 steps, CFG 1 | [Kontext Dev](https://github.com/Comfy-Org/workflow_templates/blob/a8bc07a76478dfada740fa8fa49ac87be1bff519/templates/flux_kontext_dev_basic.json) |
| RefMod_Apply_Flux_2 | Klein Base 4B; Qwen3-4B; Flux.2 VAE; native Flux2Scheduler, Euler, 20 steps, CFG 5 | [Klein Base 4B edit](https://github.com/Comfy-Org/workflow_templates/blob/a8bc07a76478dfada740fa8fa49ac87be1bff519/templates/image_flux2_klein_image_edit_4b_base.json) |
| RefMod_Apply_LTX_Video | ltx-video-2b-v0.9.5 checkpoint and its VAE; T5; native LTXVScheduler, 30 steps, shifts 2.05/0.95, stretch, terminal 0.1; CFG 3; crop guides before decode | [LTXV image-to-video](https://github.com/Comfy-Org/workflow_templates/blob/a8bc07a76478dfada740fa8fa49ac87be1bff519/templates/ltxv_image_to_video.json) |
| RefMod_Bake_Image_Families | MOSS default paired with Flux.2 small VAE; instructions name each other family's matching VAE; overwrite disabled; typed bundle validation | Matching native encoders above |
| RefMod_Bake_LTX_Guide | Same 0.9.5 checkpoint VAE as Apply; explicit 512-square guide; resolution 0 avoids a second resize; overwrite disabled | Native LTXVAddLatentGuide geometry |
| RefMod_Reference_Audition | Klein Base 4B/Qwen3-4B; CFG 5, Euler and native Flux2Scheduler; fixed target/noise, rebuilt subset conditioning, bounded sweep and separate subset saver | Klein Base preset plus native sampling/conditioning paths |

## Corrections made

- Replaced generic sampling defaults with named checkpoint presets, including Qwen's CFG 1, Fibo Dev's 50/5, Flux 3 Base's 50/1 and Krea Turbo's 8/1.
- Fixed the official MOSS adapter's format, exposed its SLG patch, and aligned its sampler with the official template.
- Fixed Flux.2 Base guidance, text encoder selection and sigma schedule. The preset uses the full Base checkpoint and full Flux.2 VAE; the upstream template uses an FP8 Base checkpoint and full-encoder/small-decoder VAE. These are explicit precision/decoder choices within the same model and latent families, not a switch to distilled Klein.
- Added a Krea style-reference format that uses the native Qwen Edit Plus conditioning template. Existing ai-toolkit formats remain available for separately trained adapters.
- Matched Fibo's negative chat template and default trained reference resize/crop, and Kontext's native default reference buckets.
- Used one named LTX checkpoint's VAE for both bake and apply, plus LTXVScheduler and an explicit crop-before-decode path.
- Named expected model files, documented variant boundaries, and removed claims that arbitrary edit/style references guarantee character identity.

## Deliberate differences and limits

- Prompt enhancers and optional caches are omitted. Users write their own edit instruction or detailed scene prompt.
- Krea transfers style. It is not presented as a character-identity adapter.
- LTX uses a smaller 512x512, 49-frame, 24fps target. This respects the spatial and temporal grids. The schedule reads the clean target, and output FPS matches conditioning. This is a video-only 0.9.5 example, not an LTX-2 audio/video preset.
- Audition defaults to a 512-square screening target and a soft time budget. Its source-preset guidance is preserved, but screening results are not production-quality validation. Skipped trials are reported explicitly.
- Existing Fibo/Kontext bundles retain their encoded dimensions. To use the corrected default sizing, rebake under a new name, or deliberately enable overwrite. MOSS's format and Flux's sampling corrections alone do not require rebaking.
- A saved RefMod records its model family and dimensions, not a cryptographic identity for the VAE weights. Matching VAE selection remains necessary.

## Verification performed

Graph tests check every shipped JSON against real node schemas, positional widgets, connected socket types, required inputs, topological order and output paths. Separate preset tests compare model/encoder/VAE choices, sampling settings and adapter formats against the reviewed source snapshot. Native parity tests compare saved-reference conditioning for Qwen, Fibo, MOSS's three layouts and Krea style against the native encoders; native bucket tests cover Kontext. LTX tests cover guide metadata, target noise preservation and crop-before-decode behavior.

The two personalized copies preserve their original prompts, seeds and output dimensions. The MOSS copy fixes its adapter format; the Flux copy uses the corrected Base encoder, CFG and schedule. Their actual saved graphs are checked against the current schemas.

**Full checkpoint generation has not been run for every workflow.** These are source-checked and mechanically tested presets, not a claim that all generated images were visually verified. Structural tests and fake encoder parity do not establish perceptual quality or identity fidelity.
