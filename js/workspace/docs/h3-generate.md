# H3 Image Edit, samplers and upscale

## MiniMax H3 Image Edit

A one-node H3 image edit or generate. It uses the core H3 conditioning nodes, including the p-h3-image path when you load that VAE.

## Ultimate KSampler and H3 KSampler

Samplers with a live preview while sampling: tiny-VAE video preview, audio spectrogram, and a progress strip. If the preview cannot start, sampling continues without it.

## H3 Upscale Picker

Finds a same-scale target size for the H3 latent upscaler and previews the result.

## Model Preview Mirror

Shows a sampler's live preview in its own panel, so you can watch it away from the sampler node (or on a second copy of the graph area). It passes any value through unchanged.

- Connect the model the sampler uses to `any` and the panel follows that sampler. With nothing connected it follows whichever preview arrives.
- Under the picture: the step, the sigma and how much the picture changed since the last step.
- It listens to the preview the Ultimate KSampler and H3 KSampler send, and to KJNodes' Model Preview Override.
