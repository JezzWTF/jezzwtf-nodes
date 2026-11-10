# RefMod Bake, Loader and Apply

## RefMod Bake (Character)

Inputs: a `name`, the H3 video `vae`, and any of `images`, `video_frames`, a `folder` of images, and `audio` with the H3 audio VAE.

It saves to `models/refmods/<subfolder>/<name>.safetensors` (subfolder defaults to `characters`). The full path comes out as `saved_path`, and a toast shows it when the bake finishes. Its `mods` output can go straight into Apply's `extra_mods`, so one run can bake and use a character.

## RefMod Loader

Loads up to four RefMod files by name with a strength and a copy count each, and outputs them as `mods` for Apply.

## RefMod Apply

Takes H3 conditioning and injects references into it.

- `retention` sets how strongly the reference holds.
- `curve_direction`, `curve_shape` and `curve_value` shape when it applies across the clip (constant, strongest at the start, or at the end).
- `scramble_seed` and `scramble_mode` shuffle or subsample several references.
- `max_total_tokens` caps the token cost.

Pick a saved file in `mod_1`, or feed `extra_mods` from a Bake or Loader.

## Tips

- More images of the character give a stronger reference than a single portrait.
- The *RefMod Bake and Apply (H3)* example workflow wires a whole generation around these nodes.
