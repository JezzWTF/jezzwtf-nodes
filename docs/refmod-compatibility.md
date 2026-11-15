# Reference-family compatibility

Implementation references checked against ComfyUI `74eb0c4` on 11 November 2026. The existing minimum ComfyUI version does not guarantee that every optional model family is available; handlers report missing core functionality when used.

| Handler | Encoded reference | Apply path |
|---|---|---|
| Qwen Image 2.1 | 64-channel image latent and RGB image | Existing Qwen vision/text encoding plus reference latents |
| Fibo 2 | 128-channel image latent and RGB image | Existing Fibo vision/text encoding plus reference latents |
| Flux 3 | 128-channel image latent | Existing reference attachment to upstream conditioning |
| Flux.2 | 128-channel image latent, 16× spatial | Reference attachment to upstream conditioning |
| Flux.1 Kontext | 16-channel image latent, 8× spatial | Reference attachment to upstream conditioning |
| MOSS-Image Edit | 128-channel image latent and RGB image | Format-specific reference method, optionally vision tokens, and an edit LoRA |
| Krea 2 Edit | 16-channel single-frame video-shaped latent, 8× spatial, plus RGB image | Krea text template, vision references, training-specific reference method and an edit LoRA |
| LTX Video | 128-channel single-image video latent, 32× spatial | Native LTXVAddLatentGuide with a target latent, placement and guide strength |

The image handlers use separate metadata keys and validate tensor ranks/channels. A bundle is reusable within its compatible family and VAE setup; its latents are not converted between families. LTX target video length, guide positions and denoise masks are handled by core rather than an image-conditioning approximation.

## Source contracts

- [MOSS edit layouts and vision preprocessing](https://github.com/Comfy-Org/ComfyUI/blob/74eb0c4/comfy_extras/nodes_moss_image.py): cached ai-toolkit, uncached ai-toolkit and Moss-Image-Edit have distinct reference methods. The latter omits reference images from text encoding.
- [Core Krea/MOSS reference conditioning](https://github.com/Comfy-Org/ComfyUI/blob/74eb0c4/comfy/model_base.py) and [Krea model reference path](https://github.com/Comfy-Org/ComfyUI/blob/74eb0c4/comfy/ldm/krea2/model.py): current core accepts reference latents and their attention method. Older Krea installations may require the [Ostris model patch](https://github.com/ostris/ComfyUI-Krea2-Ostris-Edit). The edit LoRA must match the chosen layout.
- [Flux reference methods and Kontext sizing](https://github.com/Comfy-Org/ComfyUI/blob/74eb0c4/comfy_extras/nodes_flux.py) and [model latent formats](https://github.com/Comfy-Org/ComfyUI/blob/74eb0c4/comfy/latent_formats.py): Kontext and Flux.2 have different channel counts and spatial compression.
- [Native LTX latent guides](https://github.com/Comfy-Org/ComfyUI/blob/74eb0c4/comfy_extras/nodes_lt.py): guide placement changes both conditioning and latent data, carries keyframe and guide-attention metadata, and requires cropping appended guides before decoding.
- [H3 VAE mappings](https://github.com/Comfy-Org/ComfyUI/blob/74eb0c4/comfy/sd.py): legal video lengths map 17k+5 pixel frames to 5k+2 latent frames; still images use one latent frame.

## Further candidates

- **Wan VACE / HuMo:** core has reference-latent paths, but they accompany variant-specific concat latents, masks, audio or negative-reference policies. Add a separate variant-aware adapter rather than exposing one generic “Wan” option. See [core Wan conditioning](https://github.com/Comfy-Org/ComfyUI/blob/74eb0c4/comfy_extras/nodes_wan.py).
- **LTX temporal clips and IC-LoRA:** the initial handler covers still-image guides. Temporal chunks need explicit frame ranges and causal handling; IC-LoRA adds guide downscale and attention controls. Those require bundle metadata and controls beyond the current single-image contract.
- **SDXL/SD1.5 adapter families:** assess IP-Adapter or style-model embeddings separately. A model-specific adapter and its trained weights form the reference path; attaching a generic `reference_latents` field does not provide that integration.

Verification includes bundle round trips with deterministic VAEs, conditioning checks, cross-family rejection, and the actual core LTX latent-guide operation on CPU tensors. Generation with full model weights remains a separate integration check.
