"""Every node the pack registers has a help page in js/docs (ComfyUI shows it in the node's help panel)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def registered_ids() -> set[str]:
    ids: set[str] = set()
    for path in (ROOT / "nodes").rglob("*.py"):
        ids.update(re.findall(r'node_id="(\w+)"', path.read_text(encoding="utf-8")))
    return ids


def test_every_node_has_a_help_page_and_no_page_is_orphaned() -> None:
    ids = registered_ids()
    pages = {p.stem for p in (ROOT / "js" / "docs").glob("*.md")}
    assert ids, "no nodes found"
    assert ids - pages == set(), f"missing help pages: {sorted(ids - pages)} (run tools/generate_node_docs.py)"
    assert pages - ids == set(), f"help pages for nodes that no longer exist: {sorted(pages - ids)}"


def test_help_pages_have_a_title_and_a_summary() -> None:
    for page in (ROOT / "js" / "docs").glob("*.md"):
        lines = page.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("# ") and lines[1] == "" and lines[2].strip(), page.name
