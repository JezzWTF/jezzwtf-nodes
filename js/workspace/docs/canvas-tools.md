# Canvas tools

Small helpers for tidying a graph. They work on the selected nodes (Tidy uses every node when fewer than two are selected). Everything is in the command palette, and the shortcuts below can be changed in ComfyUI's keybinding settings.

## Tidy by dependency (Alt+Shift+T)

Lays the nodes out in columns, left to right, by how far each is from the start of the chain: sources first, their consumers next, and so on. Within a column nodes sit in the order of the nodes feeding them, so wires cross as little as practical. The layout keeps the top-left corner of the selection where it was.

## Group selected nodes (Alt+Shift+G)

Draws a group box around the selection with a little padding and room for the title.

## Align and distribute

In the command palette: *Align left / right / top / bottom*, *Align centres (vertical line / horizontal line)* and *Distribute horizontally / vertically*. Align uses the outer edge of the selection; distribute makes the gaps between nodes equal and keeps the outer two nodes in place (it needs three or more).

## Bypass slash

Hold **Ctrl+Alt** and drag across the canvas: a red line follows the mouse, and every node it crosses is bypassed when you let go. Slash the same nodes again to switch them back on. If a mix of bypassed and normal nodes is crossed, they are all bypassed first.

The gesture can be turned off in Settings, under *JezzWTF → Canvas → Bypass slash*.

## Good to know

- Collapsed nodes are measured at their collapsed size.
