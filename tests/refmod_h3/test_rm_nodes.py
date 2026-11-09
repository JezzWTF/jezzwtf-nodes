"""RefMod library, Bake / Loader / Apply and the tail trio, end to end on CPU stand-ins."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import torch

from fakes import FakeAudioVAE, FakeH3VideoVAE
from refmod_h3 import bundle, h3_nodes, library, routes
from refmod_h3._types import RefModError
from refmod_h3.bundle import RefMod


def make_bundle(root: str, name: str, t: int = 5, audio_t: int = 0, description: str = "") -> str:
    mods = [RefMod(f"{name}_visual", "video" if t > 1 else "image",
                   torch.randn(1, 24, t, 20, 20).to(torch.float16), description=description)]
    if audio_t:
        mods.append(RefMod(f"{name}_audio", "audio", torch.randn(1, 32, 2, audio_t), concept_type="voice"))
    path = os.path.join(root, *name.split("/")) + ".safetensors"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bundle.write_bundle(path, name.split("/")[-1], mods)
    return path


# --------------------------------------------------------------------------- library

def test_name_normalisation_and_path_safety(refmod_root: str) -> None:
    for empty in (None, "", "None", "none", "(none)", "  (None) "):
        assert library.normalise_name(empty) == ""
    for bad in ("../x", "a/../../x", "C:/x", "C:\\x", "/abs", "\\abs", "graph_presets/x", ".git/x", ""):
        with pytest.raises(RefModError):
            library.check_rel(bad)
    assert library.resolve_stem("../etc") is None and library.resolve_stem("nope") is None
    make_bundle(refmod_root, "characters/alice")
    stem = library.resolve_stem("characters/alice")
    assert stem is not None and stem.endswith(os.path.join("characters", "alice"))
    assert library.resolve_stem("characters/alice.safetensors") == stem
    with pytest.raises(RefModError, match="not found"):
        library.resolve_path("missing")


def test_save_path_rules(refmod_root: str) -> None:
    p = library.mod_output_path("my/char", "characters")
    assert p == os.path.join(refmod_root, "characters", "my_char.safetensors")
    for sub in ("..", "../x", "C:\\x", "/abs", ".", "graph_presets"):
        with pytest.raises(RefModError):
            library.mod_output_path("x", sub)
    for name in ("", "   "):
        with pytest.raises(RefModError, match="empty"):
            library.sanitise_save_name(name)
    assert library.sanitise_save_name(" a/b\\c ") == "a_b_c"


def test_listing_skips_invalid_reserved_and_duplicate_names(refmod_root: str, tmp_path: Path) -> None:
    make_bundle(refmod_root, "alice")
    make_bundle(refmod_root, "characters/bob")
    make_bundle(refmod_root, "graph_presets/hidden")
    (Path(refmod_root) / "junk.safetensors").write_bytes(b"\x00" * 16)
    other = tmp_path / "second"
    other.mkdir()
    make_bundle(str(other), "alice")  # duplicate name: first dir wins
    make_bundle(str(other), "carol")
    found = library.list_library([refmod_root, str(other)])
    assert sorted(found) == ["alice", "carol", "characters/bob"]
    assert found["alice"].startswith(refmod_root)
    assert library.combo_choices() == ["(none)", "alice", "characters/bob"]
    make_bundle(refmod_root, "zed")  # cache signature changes with the file set
    assert "zed" in library.list_library([refmod_root])


def test_library_entry_fields(refmod_root: str) -> None:
    path = make_bundle(refmod_root, "characters/alice", t=5, audio_t=80, description="a calm voice")
    stem = path[: -len(".safetensors")]
    from refmod_h3.extract import write_sidecars
    write_sidecars(stem, torch.rand(1, 64, 64, 3), {"waveform": torch.rand(1, 1, 32000), "sample_rate": 32000}, 30.0)
    e = library.library_entry("characters/alice")
    assert e is not None
    assert e["bundle"] is True and e["faces"] == 5 and e["visual_tokens"] == 5 * 10 * 10
    assert e["audio_tokens"] == 160 and e["audio_seconds"] == 2.0 and e["description"] == "a calm voice"
    assert e["thumb"] is True and len(e["peaks"]) == 64 and e["path"] == path
    assert e["stamp"].isdigit() and library.library_entry("characters/alice") == e
    assert library.library_entry("nope") is None
    assert [x["name"] for x in library.library_entries()] == ["characters/alice"]


def test_h3_thumb_route_helper(refmod_root: str) -> None:
    path = make_bundle(refmod_root, "alice")
    assert routes.h3_thumb_bytes("alice") is None  # no sidecar yet
    from refmod_h3.extract import write_sidecars
    write_sidecars(path[: -len(".safetensors")], torch.rand(1, 64, 64, 3), None, 30.0)
    data = routes.h3_thumb_bytes("alice")
    assert data is not None and data[:2] == b"\xff\xd8"
    assert routes.h3_thumb_bytes("../alice") is None and routes.h3_thumb_bytes("") is None
    assert routes.register_routes() in (True, False)  # outside the server this must simply not raise


def test_mod_cache_validates_stamp_and_evicts(refmod_root: str) -> None:
    path = make_bundle(refmod_root, "alice")
    cache = library.ModCache(max_items=2, max_bytes=10 ** 9)
    first = cache.load(path)
    assert cache.load(path)[0] is first[0]
    make_bundle(refmod_root, "alice", t=1)  # rewritten: stamp changes
    assert cache.load(path)[0] is not first[0]
    for n in ("b", "c", "d"):
        cache.load(make_bundle(refmod_root, n))
    assert len(cache._items) == 2
    tiny = library.ModCache(max_items=24, max_bytes=10)
    assert len(tiny.load(path)) == 1 and not tiny._items


# --------------------------------------------------------------------------- bake

def test_bake_writes_bundle_sidecars_and_ui(refmod_root: str) -> None:
    node = h3_nodes.JWTFRefModBake()
    images = torch.rand(2, 400, 360, 3)
    wave = {"waveform": torch.zeros(1, 1, 64000), "sample_rate": 32000}
    out = node.bake("my char", FakeH3VideoVAE(), images=images, audio=wave, audio_vae=FakeAudioVAE(),
                    subfolder="characters", description="hello")
    rows, dest, details = out["result"]
    assert dest == os.path.join(refmod_root, "characters", "my char.safetensors") and os.path.isfile(dest)
    assert [m.kind for m, _ in rows] == ["video", "audio"] and all(s == 1.0 for _, s in rows)
    assert all(m.bundle_index is not None and m.path == dest for m, _ in rows)  # reloaded from disk
    assert os.path.isfile(dest[:-12] + ".jezzwtf.jpg") and os.path.isfile(dest[:-12] + ".jezzwtf.json")
    assert out["ui"]["text"] == [dest] and out["ui"]["refmod_entry"][0]["name"] == "characters/my char"
    import json
    info = json.loads(details)
    assert info["name"] == "my char" and len(info["members"]) == 2
    assert info["total_tokens"] == sum(m["tokens"] for m in info["members"])
    assert library.combo_choices()[-1] == "characters/my char"


def test_bake_validation_errors(refmod_root: str) -> None:
    node = h3_nodes.JWTFRefModBake()
    vae = FakeH3VideoVAE()
    with pytest.raises(RefModError, match="at least one source"):
        node.bake("x", vae)
    wave = {"waveform": torch.zeros(1, 1, 3200), "sample_rate": 32000}
    with pytest.raises(RefModError, match="audio_vae"):
        node.bake("x", vae, audio=wave)
    node.bake("x", vae, images=torch.rand(1, 64, 64, 3))
    with pytest.raises(RefModError, match="already exists"):
        node.bake("x", vae, images=torch.rand(1, 64, 64, 3), overwrite=False)
    node.bake("x", vae, images=torch.rand(1, 64, 64, 3), overwrite=True)
    with pytest.raises(RefModError):
        node.bake("../x", vae, images=torch.rand(1, 64, 64, 3), subfolder="..")


def test_bake_is_changed_only_depends_on_the_folder(tmp_path: Path) -> None:
    cls = h3_nodes.JWTFRefModBake
    assert cls.IS_CHANGED("") == "" and cls.IS_CHANGED("   ") == ""
    (tmp_path / "a.png").write_bytes(b"x")
    key = cls.IS_CHANGED(str(tmp_path), 8)
    assert key.startswith("a.png:1:")


def test_node_interfaces_match_spec() -> None:
    bake = h3_nodes.JWTFRefModBake.INPUT_TYPES()
    assert list(bake["required"]) == ["name", "vae"]
    assert bake["optional"]["audio_max_seconds"][1] == {"default": 30.0, "min": 0.025, "max": 600.0, "step": 0.5}
    assert bake["optional"]["max_visual_tokens"][1]["step"] == 512 and bake["optional"]["overwrite"][1]["default"] is True
    assert h3_nodes.JWTFRefModBake.RETURN_NAMES == ("mods", "saved_path", "details")
    assert h3_nodes.JWTFRefModBake.OUTPUT_NODE is True
    loader = h3_nodes.JWTFRefModLoader.INPUT_TYPES()
    assert {"mod_1", "strength_4", "copies_2"} <= set(loader["required"])
    assert {"show_info", "max_total_tokens", "components_3", "visual_strength_1", "audio_strength_4"} <= set(loader["optional"])
    apply = h3_nodes.JWTFRefModApply.INPUT_TYPES()
    assert apply["required"]["retention"][1]["default"] == 0.85
    assert apply["required"]["curve_value"][1]["default"] == 1.0 and apply["required"]["scramble_seed"][1]["min"] == -1
    assert apply["required"]["components_1"][0] == ["All", "Visual", "Audio"]
    assert list(apply["optional"]) == ["extra_mods"]
    assert apply["required"]["curve_shape"][0][0] == "linear" and len(apply["required"]["curve_shape"][0]) == 11
    assert h3_nodes.JWTFRefModLoader.VALIDATE_INPUTS() is True


# --------------------------------------------------------------------------- loader / apply

def slot_kwargs(**over: object) -> dict[str, object]:
    kw: dict[str, object] = {}
    for i in range(1, 5):
        kw.update({f"mod_{i}": "(none)", f"strength_{i}": 1.0, f"copies_{i}": 1,
                   f"visual_strength_{i}": 1.0, f"audio_strength_{i}": 1.0, f"components_{i}": "All"})
    kw.update(over)
    return kw


def test_loader_collects_components_copies_and_hint(refmod_root: str) -> None:
    make_bundle(refmod_root, "alice", t=5, audio_t=40, description="calm")
    make_bundle(refmod_root, "bob", t=1)
    node = h3_nodes.JWTFRefModLoader()
    rows, hint, info = node.load(**slot_kwargs(mod_1="alice", copies_1=2, strength_1=0.5, mod_2="bob",
                                              audio_strength_1=0.0))
    assert [(m.kind, s) for m, s in rows] == [("video", 0.5), ("video", 0.5), ("image", 1.0)]  # audio weight 0 skipped
    assert hint == "identity: calm"
    assert "x2" in info and f"total: {2 * 5 * 100 + 100} tokens" in info
    rows, _, _ = node.load(**slot_kwargs(mod_1="alice", components_1="Audio"))
    assert [m.kind for m, _ in rows] == ["audio"]
    rows, _, _ = node.load(**slot_kwargs(mod_1="alice", components_1="Visual", strength_1=0.0))
    assert rows == []  # master 0 skips the slot entirely
    with pytest.raises(RefModError, match="over the budget"):
        node.load(max_total_tokens=100, **slot_kwargs(mod_1="alice"))
    with pytest.raises(RefModError, match="not found"):
        node.load(**slot_kwargs(mod_1="ghost"))
    with pytest.raises(RefModError, match="finite number in \\[0, 1\\]"):
        node.load(**slot_kwargs(mod_1="alice", visual_strength_1=1.5))


def test_is_changed_stamps_files_and_flags_missing(refmod_root: str) -> None:
    make_bundle(refmod_root, "alice")
    a = h3_nodes.slots_is_changed(slot_kwargs(mod_1="alice"))
    assert len(a) == 1 and a[0][0].endswith("alice.safetensors")
    assert h3_nodes.slots_is_changed(slot_kwargs(mod_1="ghost")) == (("ghost", "missing"),)
    nan = h3_nodes.slots_is_changed(slot_kwargs(mod_1=None))
    assert len(nan) == 1 and nan[0] != nan[0]  # NaN never equals itself: always re-run
    assert h3_nodes.slots_is_changed(slot_kwargs()) == ()


def cond() -> list[list[object]]:
    return [[torch.zeros(1, 4), {"minimax_refs": []}]]


def test_apply_injects_blocks_and_merges_extra_mods(refmod_root: str) -> None:
    make_bundle(refmod_root, "alice", t=5, audio_t=40)
    extra = [(RefMod("tail_visual", "image", torch.randn(1, 24, 1, 8, 8).to(torch.float16), description="tail"), 0.5)]
    out, hint, info = h3_nodes.JWTFRefModApply().apply(cond(), extra_mods=extra, **slot_kwargs(mod_1="alice"))
    blocks = out[0][1]["minimax_refs"]
    assert [b["kind"] for b in blocks] == ["video", "audio", "image"] and all(b["refmod"] for b in blocks)
    assert hint == "identity: tail" and "(extra) tail_visual" in info and "injected 3 reference block(s)" in info
    same, _, _ = h3_nodes.JWTFRefModApply().apply(cond(), **slot_kwargs())
    assert same[0][1]["minimax_refs"] == []  # no rows: unchanged
    with pytest.raises(RefModError, match="over the budget"):
        h3_nodes.JWTFRefModApply().apply(cond(), max_total_tokens=10, extra_mods=extra, **slot_kwargs())


def test_apply_scramble_seed_is_reproducible(refmod_root: str) -> None:
    for n in ("a", "b", "c", "d"):
        make_bundle(refmod_root, n, t=1)
    kw = slot_kwargs(mod_1="a", mod_2="b", mod_3="c", mod_4="d")
    sizes = []
    for _ in range(2):
        out, _, _ = h3_nodes.JWTFRefModApply().apply(cond(), scramble_seed=3, scramble_mode="subset",
                                                    scramble_keep=2, **kw)
        sizes.append([b["latent"].float().sum().item() for b in out[0][1]["minimax_refs"]])
    assert len(sizes[0]) == 2 and sizes[0] == sizes[1]


# --------------------------------------------------------------------------- tails

def test_tail_frame_selection_follows_the_h3_grid() -> None:
    frames = torch.arange(100, dtype=torch.float32).view(100, 1, 1, 1).expand(100, 2, 2, 3)
    tail = h3_nodes.tail_frames(frames, 1.0, 24.0)
    assert tail.shape[0] == 22  # want 24 -> 17*1+5
    assert float(tail[-1, 0, 0, 0]) == 99.0 and float(tail[0, 0, 0, 0]) >= 76.0
    assert h3_nodes.tail_frames(frames, 0.25, 24.0).shape[0] == 5
    with pytest.raises(RefModError, match="at least 2"):
        h3_nodes.tail_frames(frames[:1], 1.0, 24.0)
    audio = h3_nodes.tail_audio({"waveform": torch.zeros(1, 2, 96000), "sample_rate": 32000}, 0.5)
    assert audio["waveform"].shape[-1] == 16000


def test_tail_capture_alternates_slots_and_load_reads_newest(refmod_root: str) -> None:
    vae = FakeH3VideoVAE()
    frames = torch.rand(30, 64, 64, 3)
    capture, load = h3_nodes.JWTFTailCapture(), h3_nodes.JWTFTailLoad()
    assert load.run(True, 1.0)[0] == [] and "no tail saved" in load.run(True, 1.0)[1]
    assert load.run(False, 1.0) == ([], "tail off")
    written = []
    for _ in range(3):
        res = capture.run(frames, vae, 1.0, 24.0)
        assert "tail saved" in res["ui"]["text"][0]
        newest = h3_nodes.newest_slot("tail_latest")
        written.append(os.path.basename(newest))
    assert written[0] != written[1] and written[0] == written[2]  # a/b alternate, never the newest file
    rows, info = load.run(True, 0.5)
    assert [s for _, s in rows] == [0.5] and rows[0][0].path.endswith(written[-1])
    assert load.IS_CHANGED(True, 0.5).startswith("True|0.5|")
    assert load.IS_CHANGED(True, 0.5) != load.IS_CHANGED(False, 0.5)


def test_tail_refmod_saves_and_scales_strength(refmod_root: str) -> None:
    mods, info, frames = h3_nodes.JWTFTailRefMod().run(torch.rand(30, 64, 64, 3), FakeH3VideoVAE(), 1.0, 24.0, 0.4)
    assert os.path.isfile(os.path.join(refmod_root, "_tail", "tail_latest.safetensors"))
    assert [s for _, s in mods] == [0.4] and frames.shape[0] == 22
    assert mods[0][0].latent.shape[2] == 22  # tails keep their grid length (the original collapsed them to 5)
