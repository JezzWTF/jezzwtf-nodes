# Run Timer and history

Times every workflow run. The node is only a display: runs are recorded whether or not one is on the canvas, so a timer added mid-run shows the run already in progress.

## The node

A big clock card with a status dot in the corner. The colon and the dot beat once per second while a run is in progress. Idle, it shows the last run. Hover the card for the average and best times.

Rename the node to label its runs in the history; a labelled node shows only runs filed under its label. The node keeps a fixed shape (2:1, or square for the circular face), so it cannot be squashed into something unreadable.

## Floating timer

It is on by default, so you get a timer without adding a node. Turn it off in **Settings → JezzWTF → Run Timer → Floating timer** or with *Run Timer: toggle floating timer* in the command palette. It is the same clock in its own window with no frame, so the circular face is a true circle. Drag it anywhere, resize it by the corner handle (the shape stays fixed), and click **style** to restyle it. Its place, size and look are remembered and it comes back after a reload. It shows every run; use the node when you want a labelled timer saved inside a workflow.

## Look

Hover the card and click **style**:

- **Skin**: *Glass* (a lit bezel, gloss and a gradient ring, the default), *Neon* (black with a glowing accent) or *Flat* (the plain card).
- **Face**: Digital; Circular, a ring around the clock; or Analog, a stopwatch dial with 60 ticks, a sweeping hand and a small 30-minute sub-dial.
- **Motion** (Circular face only): *Laps* fills a ring, and when it completes it goes round again in a second colour (the accent with its hue turned) while the finished lap stays drawn behind it. *Ticks* lights 60 watch ticks, and *Comet* sends a dot with a fading tail round the ring. When no run is going the ring is full.
- **Lap**: how long one turn takes: 10 s, 30 s, 1 min, or the average of your past successful runs.
- **Colour**: seven presets or any custom colour.
- **Font**: Mono, Sans, Rounded, Serif, Thin or Condensed (system fonts, so the exact look depends on your machine).
- **Back**: Dark, Black, Clear or Light.
- **Result**: tint the clock red or amber for failed or interrupted runs, or always use the accent colour.

On a node the style is saved in the workflow; the floating timer keeps its own style in your browser.

## The history window

Click **history** on the card, or use the command palette ("toggle history panel").

- Newest first, with the label, how long ago, the duration and the status.
- Stats: count, average, median, best and worst. Filter by label and status.
- Delete one run, or clear all. Export as **CSV** or **JSON**.
- Drag and resize it, and minimise it to a chip that shows the running time.

## Good to know

- Runs are recorded from ComfyUI's execution events. A run that finished while the browser tab was closed is kept as *unknown* with no duration, never an invented one.
- Runs queued from outside the ComfyUI page (scripts, other clients) are only seen if they use this browser tab's client id.
- History is saved on the server (the newest 500 runs), so it survives reloads and is shared between browsers.
