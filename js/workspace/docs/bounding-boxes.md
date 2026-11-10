# Bounding Boxes and Layout LLM Prompt

## Bounding Boxes

Draw layout boxes on a canvas. It outputs a preview image, `BOUNDING_BOX` data and prompt elements. It supports layers, snapping, a right-click menu and pasting or importing JSON.

If an upstream node supplies boxes, they replace your canvas edits until you change the incoming value.

## Layout LLM Prompt

Writes the instructions that make an LLM answer with box JSON on a 0 to 1000 grid. Wire the model's reply into Bounding Boxes so a local LLM can draw your layout.
