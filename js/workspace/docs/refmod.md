# What is a RefMod?

MiniMax H3 can take reference material for a video: portrait stills, a short clip and a voice sample. A **RefMod** is a reusable `.safetensors` file holding that material, already encoded through H3's own VAEs. You encode a character once and reuse it in every video.

## The pieces

- **Bake** encodes your references and saves the file. It is extraction only; there is no training.
- **Apply** injects a RefMod into the H3 conditioning as extra reference tokens, with controls for how strongly it holds.
- The file's header can also carry a character card, avatar and system prompt, which Character Chat reads. See [Character card bakers](topic:character-cards).

## Two kinds of file

- A **reference file** holds latents (images, video and audio members).
- A **character-only file** holds just the card in its header, with no latents. Chat can use it, but H3 video cannot.
- A **hybrid** is a reference file with a card added.

See [RefMod Bake, Loader and Apply](topic:refmod-nodes) for the nodes.
