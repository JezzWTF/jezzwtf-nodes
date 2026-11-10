# Prompt Relay

Per-segment temporal prompts for LTX video: give different parts of a clip different prompts.

## Nodes

- **Prompt Relay Encode** takes one prompt per segment (separated by `|`) and the segment lengths.
- **Prompt Relay Timeline** is the same with a draggable timeline editor: drag boundaries, add, duplicate, equalise and delete segments, undo and redo, and set the length in frames or seconds.
- **Prompt Relay Options** tunes epsilon, strength and window per stream.

## Good to know

- A segment needs a prompt. Empty segments are rejected with a clear error.
- The pipe character is replaced inside a prompt, because it separates segments.
- The relay only biases text attention, so audio and video attention are untouched.
