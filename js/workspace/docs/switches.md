# Switch, Route and Multi Switch

## Switch

Pick one of two inputs with a true/false switch and send it on. A typical use is choosing between two prompts: connect one text to `true` and another to `false`, wire the output to the node that needs a prompt, and flip the switch.

- The output takes the type of whatever you connect, so a string stays a string and an image stays an image. Connect both sides with the same type.
- Only the chosen side is computed. Whatever feeds the other side does not run, so a slow or failing branch costs nothing while it is switched off.
- `switch` can be a widget or wired in from another node (for example a boolean from a comparison).
- The slot of the active side is coloured (blue for false, orange for true) and the other goes grey.
- If the chosen side has nothing connected, the node says which side is empty.

## Route

The opposite of Switch: one input goes to either the `true` or the `false` output. Use it to send a value down one of two paths, for example an image to a fast preview or to a slow upscale.

- Both outputs take the type of the input.
- The output that is not chosen is blocked: nodes connected only to it do not run for this run, and nothing is reported as an error.
- The active side's output is coloured like the Switch (blue false, orange true).
- `switch` can be a widget or wired in from another node.

## Multi Switch

Several true/false pairs behind one switch. Pair 1's chosen side goes to `output 1`, pair 2's to `output 2`, and so on, and the one `switch` flips them all together. Use it when several values change together, for example a positive and a negative prompt, or a model and its settings.

- **+ Add pair** and **− Remove pair** change how many pairs the node shows, from one to six. Removing a pair disconnects its wires. The number of pairs is saved with the workflow.
- Each output takes the type of its own pair, independent of the other pairs.
- Only the chosen side of each pair is computed, like the Switch.
- A pair with nothing connected on the chosen side sends nothing on its output.

## Good to know

- Workflows saved with the earlier Multi Switch keep working: the inputs and outputs have the same names.
