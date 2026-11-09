# Video Compare

Compare two videos or image batches in the UI, frame-locked.

## Inputs

`video_a` and `video_b` (VIDEO), or `image_a` and `image_b` (IMAGE batches), optional audio, and a `frame_rate` for image inputs. `b_offset` shifts B in time.

## The panel

**A** is the first input and **B** the second. Choose wipe, side by side or difference, drag the divider, scrub, and loop. Playback is muted by default.

## Good to know

- The previews are H.264 files in ComfyUI's temp folder. Image inputs are padded by at most one pixel so the size is even.
- Wire Duration to Frames' `fps` (FLOAT) into `frame_rate`.
