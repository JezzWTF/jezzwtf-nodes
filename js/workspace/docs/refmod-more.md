# Tail and Image RefMod

## Tail RefMod, Tail Capture and Tail Load

Carry a character or look from the end of one clip into the next. **Tail Capture** saves the last frames of a clip, **Tail Load** reads them back, and **Tail RefMod** applies them as a reference when you continue a video.

## Image RefMod Bake and Apply

The same idea for image models. Handlers cover Qwen Image 2.1, Fibo 2 and Flux 3: Bake encodes references through the model's own VAE and Apply adds them to the conditioning as reference latents. Each file records which handler made it.
