"""Write ComfyUI's per-node help pages (js/docs/<NodeId>.md) from a running ComfyUI that has this pack loaded.

usage: python tools/generate_node_docs.py [http://127.0.0.1:8188]

Each page lists the node's inputs (with their tooltips, defaults and ranges) and outputs, a one-line summary taken from
the node's description or the README table, and a pointer to the matching page of the JezzWTF Documentation window.
Run it again after changing a node's inputs; the files are generated, so edit the generator rather than the pages.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "js" / "docs"
TOPICS = ROOT / "js" / "workspace" / "docs"
MAX_OPTIONS = 12
CATEGORY_LINE = {
    "utils": "a utility node",
    "image": "an image node",
    "dataset": "a dataset node",
    "audio": "an audio node",
    "video": "a video node",
    "gif": "a GIF node",
    "lora": "a LoRA node",
    "loaders": "a loader node",
    "refmod": "a RefMod node",
    "sampling": "a sampler node",
    "LLM": "an LLM node",
    "cards": "a character card node",
}


def fetch(base: str) -> dict[str, dict]:
    with urllib.request.urlopen(f"{base.rstrip('/')}/object_info", timeout=60) as response:
        info = json.load(response)
    return {k: v for k, v in info.items() if "jezzwtf" in str(v.get("python_module", "")).lower()}


def readme_summaries() -> dict[str, str]:
    """Display name -> summary from the README node tables (a row can name several nodes, separated by ' / ')."""
    out: dict[str, str] = {}
    for line in (ROOT / "README.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 2 or set(cells[0]) <= {"-", " "} or cells[0] in ("Node", "Workflow"):
            continue
        for name in re.split(r"\s+/\s+", cells[0]):
            out[name.strip().lower()] = cells[1]
    return out


def topic_index() -> list[tuple[str, str, str]]:
    """(topic id, title, lower-cased text) for every Documentation window page."""
    index = json.loads((TOPICS / "index.json").read_text(encoding="utf-8"))
    pages = []
    for section in index["sections"]:
        for topic in section["topics"]:
            text = (TOPICS / topic["file"]).read_text(encoding="utf-8").lower()
            pages.append((topic["id"], topic["title"], text))
    return pages


def describe(spec: object) -> tuple[str, dict]:
    kind = spec[0] if isinstance(spec, list) and spec else spec
    opts = spec[1] if isinstance(spec, list) and len(spec) > 1 and isinstance(spec[1], dict) else {}
    return str(kind), opts


def _looks_dynamic(option: str) -> bool:
    """File names and placeholders come from the machine the page was generated on, so they are not listed."""
    return option.startswith("(") or "/" in option or bool(re.search(r"\.\w{2,5}$", option))


COMMON = {
    "seed": "Random seed; the same seed gives the same result.",
    "width": "Width in pixels.",
    "height": "Height in pixels.",
    "fps": "Frames per second.",
    "model": "The model to use.",
    "clip": "The CLIP / text encoder to use.",
    "vae": "The VAE to use.",
    "image": "The input image.",
    "images": "The input images (an image batch).",
    "mask": "The mask.",
    "prompt": "The text prompt.",
    "negative_prompt": "What the result should avoid.",
    "filename_prefix": "Prefix for the saved file; a sub-folder can be included, for example `gifs/clip`.",
    "folder_path": "Path to the folder.",
    "path": "File path, overriding the picker.",
    "label": "Label the runs are filed under.",
}


def humanise(name: str) -> str:
    return name.replace("_", " ").strip().capitalize() + "."


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def range_cell(kind: str, opts: dict) -> str:
    if kind == "COMBO":
        options = opts.get("options", [])
        if 2 <= len(options) <= MAX_OPTIONS and not any(_looks_dynamic(str(o)) for o in options):
            return "<br>".join(f"`\"{o}\"`" for o in options)
        return "choose from the list"
    if "min" in opts and "max" in opts and opts["max"] < 1e15:
        step = f" (step {opts['step']:g})" if isinstance(opts.get("step"), (int, float)) and opts["step"] not in (0, 1) else ""
        return f"{opts['min']:g} to {opts['max']:g}{step}"
    return ""


def input_row(name: str, spec: object, optional: bool) -> str:
    kind, opts = describe(spec)
    text = str(opts.get("tooltip") or COMMON.get(name) or humanise(name)).rstrip()
    if "default" in opts and opts["default"] not in ("", None, []):
        shown = opts["default"] if isinstance(opts["default"], str) else json.dumps(opts["default"])
        if len(str(shown)) <= 40 and kind != "COMBO":
            text += f" (default: {shown})"
        elif kind == "COMBO" and len(str(shown)) <= 40:
            text += f" (default: `{shown}`)"
    shown_kind = "ANY (matches what is connected)" if kind == "COMFY_MATCHTYPE_V3" else kind.upper()
    return f"| `{name}` | {cell(text)} | {shown_kind} | {'No' if optional else 'Yes'} | {cell(range_cell(kind, opts))} |"


def page(node_id: str, node: dict, summaries: dict[str, str], topics: list[tuple[str, str, str]]) -> str:
    display = node.get("display_name") or node_id
    category = str(node.get("category", ""))
    leaf = category.split("/")[-1]
    summary = (node.get("description") or "").strip() or summaries.get(display.lower()) or f"{display} is {CATEGORY_LINE.get(leaf, 'a node')} from the JezzWTF nodes."
    lines = [f"# {display}", "", summary.rstrip(".") + ".", ""]
    sections = node.get("input", {})
    rows = [input_row(n, s, False) for n, s in sections.get("required", {}).items()] +            [input_row(n, s, True) for n, s in sections.get("optional", {}).items()]
    if rows:
        lines += ["## Inputs", "", "| Parameter | Description | Data Type | Required | Range |", "|-----------|-------------|-----------|----------|-------|", *rows, ""]
    outputs = list(zip(node.get("output_name") or [], node.get("output") or [], node.get("output_tooltips") or [None] * 99))
    if outputs:
        lines += ["## Outputs", "", "| Output Name | Description | Data Type |", "|-------------|-------------|-----------|"]
        lines += [f"| `{n}` | {cell(str(tip) if tip else COMMON.get(n) or humanise(n))} | {'ANY (matches what is connected)' if str(t).upper() == 'COMFY_MATCHTYPE_V3' else str(t).upper()} |" for n, t, tip in outputs]
        lines.append("")
    needle = display.lower()
    match = next((t for t in topics if re.search(rf"^#+ .*{re.escape(needle)}", t[2], re.MULTILINE)), None)  # a page with a heading for this node
    pointer = f"the **{match[1]}** page" if match else "the guide"
    lines += ["Notes:", "", f"- More detail, including how this node fits with the others, is in {pointer} of the JezzWTF Documentation window (Alt+Shift+D).", ""]
    return "\n".join(lines)


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8188"
    nodes = fetch(base)
    OUT.mkdir(parents=True, exist_ok=True)
    summaries, topics = readme_summaries(), topic_index()
    for old in OUT.glob("*.md"):
        if old.stem not in nodes:
            old.unlink()
    for node_id, node in sorted(nodes.items()):
        (OUT / f"{node_id}.md").write_text(page(node_id, node, summaries, topics), encoding="utf-8", newline="\n")
    print(f"wrote {len(nodes)} pages to {OUT}")


if __name__ == "__main__":
    main()
