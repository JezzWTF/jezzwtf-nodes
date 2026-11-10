# Paste Stack

A floating clipboard history for text, images and files.

- Click the panel to save what you copied. Text and images use the browser clipboard; files copied in Explorer or Finder are read by a small local helper.
- Click a saved card to copy it back. Images are copied as PNG.
- Drag an image card onto a Load Image node to upload it and select it.
- Reorder, edit text cards, delete or clear. Duplicates are merged and the oldest cards go first when the limit is reached.
- The stack survives reloads and minimises to a chip.

The helper only answers requests from your own machine and never writes clipboard contents to disk.

## Backdrop

Behind the cards there is a slowly drifting teal and violet backdrop with a soft glow that follows the pointer, a ripple where you click, paste or drop, and a brightness that rises as the stack fills. It is only decoration. It uses WebGL2 at half resolution, at most 30 frames a second, and pauses when the tab is hidden or the panel is minimised; with reduced motion it draws still frames only. Turn it off in Settings → JezzWTF Paste Stack: animated backdrop. Without WebGL2 the panel keeps its plain gradient.
