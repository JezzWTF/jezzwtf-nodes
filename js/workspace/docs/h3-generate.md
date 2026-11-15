# H3 Image Edit, samplers and upscale

## MiniMax H3 Image Edit

A one-node H3 image edit or generate. It uses the core H3 conditioning nodes, including the p-h3-image path when you load that VAE.

## Ultimate KSampler and H3 KSampler

Samplers with a live preview while sampling: tiny-VAE video preview, audio spectrogram, and a progress strip. If the preview cannot start, sampling continues without it.

Both nodes use the same sampling backend and return `latent`, `denoised`, decoded `image` frames and `audio`. Decoding is optional; connect the matching video/image and audio VAEs for the decoded outputs.

**Ultimate KSampler** supports built-in samplers and RES4LYF/Clown samplers. Its optional advanced inputs work with built-in samplers:

- `noise` replaces seeded noise; `sampler` replaces the sampler picker.
- `guider` carries the sampling model and conditioning, so `model` and `positive` may be left disconnected. The guider owns guidance; the node's positive/negative and CFG controls are ignored.
- `sigmas` replaces the widget-generated schedule, including `scheduler`, `steps` and `denoise`. `steps_to_run` still limits how many initial schedule steps execute. Without explicit sigmas, the schedule uses the connected `model`, or the model discovered inside the guider when no model is connected.
- Without a guider, connect `model` and `positive`. Disable **CFG enabled**, or omit `negative`, for positive-only sampling. **CFG=0 retains its numeric meaning**; the toggle selects positive-only operation.

RES4LYF supports its existing `sigmas`, options, eta, sampler mode and bongmath controls. It cannot use external noise, guider or sampler objects; disconnect those inputs before selecting a `clown:` algorithm. Unsupported combinations report an error instead of silently ignoring connections.

**H3 KSampler** is the compatibility preset: it keeps its existing sockets, widget order and eight-step default, and builds a positive-only guider when no external guider is supplied. Saved H3 workflows retain their interface. A connected guider owns its own guidance behaviour.

The `preview_tiny_vae` picker lists installed files from `models/vae_approx`. Choose a decoder matching the model family; `none` uses the normal preview fallback. Preview wrapping follows the guider's own model, including its LoRA/RefMod patches, without modifying the original guider. Overridden widgets are hidden while their values remain saved. `denoise=0` with no explicit sigmas passes the latent through and can still decode it.

## H3 Upscale Picker

Finds a same-scale target size for the H3 latent upscaler and previews the result.

## Model Preview Mirror

Shows a sampler's live preview in its own panel, so you can watch it away from the sampler node (or on a second copy of the graph area). It passes any value through unchanged.

- Connect the model the sampler uses to `any` and the panel follows that sampler. With nothing connected it follows whichever preview arrives.
- Under the picture: the step, the sigma and how much the picture changed since the last step.
- It listens to the preview the Ultimate KSampler and H3 KSampler send, and to KJNodes' Model Preview Override.
