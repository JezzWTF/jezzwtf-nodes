from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
import torch
from aiohttp.test_utils import make_mocked_request
from gallery import NODES, listing, routes
from gallery.gallery_load import JWTFGalleryLoad
from PIL import Image
from v3_helpers import legacy, overrides


@pytest.fixture()
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    d = {"input": str(tmp_path / "input"), "output": str(tmp_path / "output"), "temp": str(tmp_path / "temp")}
    for p in d.values():
        os.makedirs(p)
    monkeypatch.setattr(listing, "root_for", lambda kind: d[(kind or "input").lower()])
    return d


def save(root: str, rel: str, size: tuple[int, int] = (8, 6), mode: str = "RGB", colour: object = (255, 0, 0), mtime: int | None = None) -> str:
    full = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    Image.new(mode, size, colour).save(full)
    if mtime is not None:
        os.utime(full, (mtime, mtime))
    return full


def test_family_exports_the_loader() -> None:
    assert [n.GET_SCHEMA().node_id for n in NODES] == ["JWTFGalleryLoad"]


def test_parse_ref_and_labels() -> None:
    assert listing.parse_ref("a/b.png") == listing.ImageRef("input", "a/b.png")
    assert listing.parse_ref("a\\b.png [output]") == listing.ImageRef("output", "a/b.png")
    assert listing.parse_ref("x.png [OUTPUT]").kind == "output"
    assert listing.ImageRef("output", "x.png").label() == "x.png [output]" and listing.ImageRef("input", "x.png").label() == "x.png"


def test_selection_parsing_is_forgiving() -> None:
    assert listing.parse_selection('["a.png", "a.png", "", 3, "b.png"]') == ["a.png", "b.png"]
    assert listing.parse_selection("nope") == [] and listing.parse_selection('{"a": 1}') == [] and listing.parse_selection("") == []


def test_clean_folder_blocks_escapes() -> None:
    assert listing.clean_folder("a/../b\\c/./d") == "a/b/c/d" and listing.clean_folder("C:/x") == "x" and listing.clean_folder("..") == ""


def test_listing_folders_files_search_and_order(roots: dict[str, str]) -> None:
    save(roots["input"], "old.png", mtime=1000)
    save(roots["input"], "new.jpg", mtime=2000)
    save(roots["input"], "sub/inner.png", mtime=1500)
    save(roots["input"], ".hidden/x.png")
    open(os.path.join(roots["input"], "notes.txt"), "w").close()
    top = listing.list_folder("input")
    assert top["folders"] == ["sub"] and [f["name"] for f in top["files"]] == ["new.jpg", "old.png"]
    sub = listing.list_folder("input", "sub")
    assert [f["name"] for f in sub["files"]] == ["sub/inner.png"] and sub["folder"] == "sub"
    assert [f["name"] for f in listing.list_folder("input", "", "OLD")["files"]] == ["old.png"]
    assert listing.list_folder("input", "../../etc")["files"] == []
    assert listing.list_folder("temp")["type"] == "input"  # only input and output are browsable


def test_resolve_ref_checks_location_type_and_existence(roots: dict[str, str]) -> None:
    img = save(roots["input"], "ok.png")
    save(roots["output"], "o.png")
    open(os.path.join(roots["input"], "doc.txt"), "w").close()
    assert listing.resolve_ref("ok.png") == os.path.realpath(img)
    assert listing.resolve_ref("o.png [output]").endswith("o.png")
    with pytest.raises(ValueError, match="outside"):
        listing.resolve_ref("../output/o.png")
    with pytest.raises(ValueError, match="not an image"):
        listing.resolve_ref("doc.txt")
    with pytest.raises(FileNotFoundError):
        listing.resolve_ref("gone.png")
    with pytest.raises(ValueError):
        listing.resolve_ref("  ")


def test_node_batches_to_the_first_size_with_alpha_masks(roots: dict[str, str]) -> None:
    save(roots["input"], "a.png", (8, 6), "RGB", (255, 0, 0))
    save(roots["output"], "b.png", (4, 4), "RGBA", (0, 255, 0, 128))
    out = legacy(JWTFGalleryLoad.execute(json.dumps(["a.png", "b.png [output]"])))
    images, masks, names, count = out
    assert images.shape == (2, 6, 8, 3) and masks.shape == (2, 6, 8) and count == 2
    assert names == "a.png\nb.png [output]"
    assert torch.allclose(images[0, 0, 0], torch.tensor([1.0, 0.0, 0.0])) and float(masks[0].max()) == 0.0
    assert float(masks[1].mean()) == pytest.approx(1 - 128 / 255, abs=0.01)


def test_node_validation_and_fingerprint(roots: dict[str, str]) -> None:
    path = save(roots["input"], "a.png")
    assert "pick at least one" in JWTFGalleryLoad.validate_inputs("[]")
    assert "not found" in JWTFGalleryLoad.validate_inputs('["gone.png"]')
    assert JWTFGalleryLoad.validate_inputs('["a.png"]') is True
    before = JWTFGalleryLoad.fingerprint_inputs('["a.png"]')
    os.utime(path, (1, 1))
    assert JWTFGalleryLoad.fingerprint_inputs('["a.png"]') != before
    assert overrides(JWTFGalleryLoad, "fingerprint_inputs")
    with pytest.raises(ValueError, match="pick at least one"):
        JWTFGalleryLoad.execute("[]")


def test_list_route_returns_json(roots: dict[str, str]) -> None:
    save(roots["input"], "a.png")
    request = make_mocked_request("GET", "/jezzwtf/gallery/list?type=input&folder=")
    response = asyncio.run(routes.list_handler(request))
    body = json.loads(response.text)
    assert response.status == 200 and [f["name"] for f in body["files"]] == ["a.png"]
