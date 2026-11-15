# Image tools validation

The regular pytest families cover image encoding, SSIM and alpha preservation, comparison batches, saved mask loading, waveform extraction/routes, H3 preflight, and reference-family bundle/conditioning behavior. They use the same ComfyUI checkout and CPU dependencies as the repository's CI.

For the editor interaction smoke check, install the optional test dependencies and Chromium:

```powershell
python -m pip install Pillow playwright
python -m playwright install chromium
python tools/check_image_tools_browser.py
```

The script runs the actual frontend modules against a small local fixture server and checks comparison modes, mask painting/upload/undo/fill, failed-upload queue blocking, returning to the input mask, and waveform trim dragging. It writes a screenshot to the printed result directory. Pass a directory as its first argument to choose where the screenshot goes.

This is a simulated ComfyUI API, not a full application run. In ComfyUI, also check saved/reloaded workflows, the active renderer and theme, and the audio player's codec support. New RefMod families require generation with the matching model weights and edit LoRAs; the CPU contract tests do not establish generation quality.
