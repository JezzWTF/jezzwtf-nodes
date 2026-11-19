# Face refinement validation

Checked on 15 November 2026 with native WeVisOne-VL 2B, Flux.2 Klein Base 4B, Qwen3-4B, the full Flux.2 VAE and one saved reference. This is a one-image diagnostic, not a quality benchmark.

## Problem and correction

The original example passed the fractional segmentation matte into Set Latent Noise Mask and then used the same matte at pasteback. The resulting face looked nearly unchanged. A successful run and unchanged pixels outside the crop established execution and containment, but did not establish useful detail improvement.

ComfyUI's `KSamplerX0Inpaint` blends toward the original latent through the noise mask at every sampling step. The tested matte was substantially gray over scalp and beard. This repeatedly restricted redraw before the compositor attenuated the result again.

The corrected example samples the whole padded, VAE-encoded RGB crop. The recorded selection matte controls pasteback only. Separate Image Compare panels show the enlarged input against the decoded crop and the original image against the final composite.

## Controlled runs

All runs used seed 7, Euler, CFG 5, the same source, prompt and crop. A 1024×768 source produced a 656×768 working crop. Flux2Scheduler used a 100-step schedule and the low-sigma output of SplitSigmasDenoise: 20 sampling steps at 0.20 or 35 at 0.35.

| Run | Mean absolute RGB difference from enlarged crop, 0–255 scale | Observation |
| --- | ---: | --- |
| VAE encode/decode only | 1.36 | Reconstruction itself changes pixels; differences alone cannot prove refinement. |
| Original soft-mask sampling, 0.20, references | 2.45 | Very weak visible change. |
| Full-crop sampling, 0.20, references | 6.23 | More visible redraw with the same sampling strength and seed. |
| Full-crop sampling, 0.35, references | 9.80 | Stronger changes, including facial markings; not necessarily more accurate detail. |
| Full-crop sampling, 0.35, no references | 9.75 | Face and tattoo lettering change substantially relative to the reference-conditioned result. References have a visible effect. |

These difference measurements quantify change, not sharpness, identity similarity or restoration quality. In particular, the two 0.35 runs have similar difference magnitudes but visibly different features.

## Limits

- The output retains the input resolution. The enlarged crop is reduced to its recorded source region at pasteback; this can discard working-resolution detail. Enlarge the whole input first when a larger final image is required.
- This is generative refinement. It cannot guarantee recovery of original skin, beard or tattoo details, and stronger denoise can change identity.
- The conservative default remains 0.20. The controlled runs do not establish a universally better strength or a reliable facial restoration method.
- Regression checks enforce full-crop sampling, reference conditioning, crop-scale comparison and pasteback into the original source. Visual quality still requires inspection.

Core behavior: [masked sampling](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/samplers.py), [Flux.2 schedule](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_flux.py), [sigma splitting](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_custom_sampler.py).
