# Duration to Frames and Resolution Picker

## Duration to Frames

Turns seconds into a frame count.

- Pick a **preset**: *MiniMax H3 (24 FPS)* uses the H3 rule of `17n + 5` frames, *24 FPS* and *30 FPS* use plain `seconds x fps`. **Custom** unlocks the expression and fps fields.
- The expression field accepts simple maths using `a` for the duration and `fps`. It is evaluated safely: no code can run.
- The card shows the result, the real duration it gives, and quick values for 2, 3, 4, 5, 6, 8, 10, 12 and 15 seconds.

Outputs: `frames` (INT), `seconds` (FLOAT), `fps` (FLOAT, for frame-rate inputs such as Video Compare and Create Video) and `fps_int` (INT, for nodes that want an integer).

## Resolution Picker

Choose an aspect ratio and megapixels, or a preset size, and get `width`, `height` and an empty latent. The preview animates the chosen shape.
