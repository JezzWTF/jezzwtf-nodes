# RefMod Conditioning Check (MOSS)

Build saved-reference and native MOSS edit conditioning from the same bundle, prompt and format. Use the companion **RefMod Diagnose MOSS Image** example to render both with shared model components, seed, sampling settings and target.

The default task requests the same person in a new full-body pose, clothing, framing and setting. Output width and height default to an independent 1024×768 canvas. Preserving the original portrait and changing only its background fails this task. Neither this node nor its report can determine identity fidelity automatically.

Choose the saved MOSS bundle and connect the same CLIP and VAE used by generation. No original image upload or rebaking is needed. The native branch uses ComfyUI's own Text Encode MOSS-Image Edit and re-encodes the RGB references stored in the bundle. Both branches use all references, at full schedule strength, on positive and negative conditioning.

The report lists saved and freshly encoded reference shapes and maximum absolute differences. Small differences are expected because stored RGB images are 8-bit; a different VAE can cause larger differences. These numbers do not score identity or output quality. The reference preview shows only the first image in a multi-reference bundle.

If the saved branch fails while native editing works, investigate the bundle, bake settings and VAE compatibility. If both fail, the native path also reproduces the problem; investigate the model, adapter loading and ComfyUI runtime. The node does not alter or overwrite the bundle.

The native branch uses RGB images from the same bundle, so this comparison cannot establish that baking selected the intended original photos or preserved their original preprocessing. Replacing a bundle under the same name invalidates this node's cached result.
