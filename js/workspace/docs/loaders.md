# Model loaders

## Diffusers Loader

Loads a Diffusers folder or single file as MODEL, CLIP and VAE. It looks in `transformer/` and `unet/`, merges sharded weights, and prefers full-precision files over fp16. An incomplete shard set raises an error instead of silently dropping an encoder.

## Ultimate Model Loader

A diffusion model, two text encoders and two VAEs in one node, with options for the attention backend (including sparse and VSA attention on an H3 model) and quantisation formats. Choices are filtered to what your ComfyUI build supports.
