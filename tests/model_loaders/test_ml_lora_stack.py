from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
import torch

from model_loaders.lora_stack_logic import (
    LoraEntry,
    PlannedLora,
    apply_planned,
    StateDictCache,
    applied_summary,
    compact_float,
    folder_files,
    folder_listing,
    human_size,
    list_subfolders,
    parse_lora_data,
    plan_stack,
    resolve_in_folder,
    sanitize_subfolder,
)


def test_parse_object_and_list_forms() -> None:
    a = parse_lora_data('{"loras": [{"on": true, "name": "x.safetensors", "model": 0.5, "clip": 0.25}]}')
    b = parse_lora_data('[{"lora": "x.safetensors", "model": 0.5, "clip": 0.25}]')
    assert a == b == [LoraEntry(name="x.safetensors", on=True, model=0.5, clip=0.25)]


def test_parse_lenient_rules() -> None:
    raw = json.dumps({"loras": [
        "not a dict", {"name": ""}, {"name": "None"}, {"name": "NONE"},
        {"name": "legacy", "strength": 0.7, "model": 3, "clip": 4},
        {"name": "clipdefault", "model": 0.3},
        {"name": "off", "on": False},
        {"name": "nan", "model": float("nan"), "clip": "abc"},
        {"name": "split", "split": True, "model": 1, "clip": 0.5},
    ]})
    out = parse_lora_data(raw)
    assert [e.name for e in out] == ["legacy", "clipdefault", "off", "nan", "split"]
    assert (out[0].model, out[0].clip) == (0.7, 0.7)
    assert (out[1].model, out[1].clip) == (0.3, 0.3)
    assert out[2].on is False
    assert (out[3].model, out[3].clip) == (1.0, 1.0)
    assert out[4].split is True


@pytest.mark.parametrize("raw", ["", "{not json", "42", "null", '{"loras": 5}'])
def test_parse_invalid_is_empty(raw: str) -> None:
    assert parse_lora_data(raw) == []


def test_plan_stack_skips_clamps_dedupes(tmp_path: Path) -> None:
    f1 = tmp_path / "a.safetensors"
    f1.write_bytes(b"x")
    f2 = tmp_path / "b.safetensors"
    f2.write_bytes(b"x")
    files = {"a.safetensors": str(f1), "b.safetensors": str(f2)}
    entries = [
        LoraEntry("a.safetensors", model=25, clip=-30),
        LoraEntry("b.safetensors", on=False),
        LoraEntry("missing.safetensors"),
        LoraEntry("a.safetensors"),  # duplicate path
        LoraEntry("b.safetensors", model=0, clip=0.5),
    ]
    logs: list[str] = []
    plan = plan_stack(entries, files.get, has_clip=False, log=logs.append)
    assert [(p.entry.name, p.model, p.clip) for p in plan] == [("a.safetensors", 10.0, -10.0)]
    assert any("missing" in m for m in logs) and any("duplicate" in m for m in logs)
    plan_clip = plan_stack(entries, files.get, has_clip=True)
    assert [p.entry.name for p in plan_clip] == ["a.safetensors", "b.safetensors"]
    assert applied_summary(plan_clip) == "a.safetensors@10, b.safetensors@0"
    assert applied_summary([]) == "(none)"


def test_formatting() -> None:
    assert compact_float(1.0) == "1"
    assert compact_float(0.75) == "0.75"
    assert compact_float(-0.0) == "0"
    assert human_size(512) == "512 B"
    assert human_size(1024) == "1.0 KB"
    assert human_size(int(1.5 * 1024 ** 2)) == "1.5 MB"
    assert human_size(3 * 1024 ** 3) == "3.0 GB"


def test_state_dict_cache_lru_mtime_and_copies(tmp_path: Path) -> None:
    calls: list[str] = []

    def loader(p: str) -> dict[str, torch.Tensor]:
        calls.append(p)
        return {"w": torch.ones(1)}

    paths = []
    for i in range(3):
        p = tmp_path / f"{i}.safetensors"
        p.write_bytes(b"x")
        paths.append(str(p))
    cache = StateDictCache(max_entries=2)
    sd = cache.get(paths[0], loader)
    sd.pop("w")  # consumer mutates its copy
    assert "w" in cache.get(paths[0], loader)
    assert len(calls) == 1
    cache.get(paths[1], loader)
    cache.get(paths[2], loader)  # evicts paths[0]
    assert len(cache) == 2
    cache.get(paths[0], loader)
    assert len(calls) == 4
    # overwriting the file (new mtime) reloads and replaces the stale entry
    t = time.time() + 10
    os.utime(paths[0], (t, t))
    cache.get(paths[0], loader)
    assert len(calls) == 5 and len(cache) == 2


@pytest.mark.parametrize("bad", ["../x", "a/../../b", "/abs", "C:/x"])
def test_sanitize_rejects_traversal(bad: str) -> None:
    with pytest.raises(ValueError):
        sanitize_subfolder(bad)


def test_sanitize_normalises() -> None:
    assert sanitize_subfolder("") == ""
    assert sanitize_subfolder(" krea\\style/ ") == "krea/style"
    assert sanitize_subfolder("./a/./b") == "a/b"


def test_folder_files_and_listing(tmp_path: Path) -> None:
    r1, r2 = tmp_path / "r1", tmp_path / "r2"
    (r1 / "pack").mkdir(parents=True)
    (r2 / "pack").mkdir(parents=True)
    (r1 / "pack" / "B.safetensors").write_bytes(b"12")
    (r1 / "pack" / "a.safetensors").write_bytes(b"1")
    (r1 / "pack" / "ignore.ckpt").write_bytes(b"1")
    (r2 / "pack" / "a.safetensors").write_bytes(b"other root")
    (r2 / "pack" / "c.safetensors").write_bytes(b"1")
    (r1 / "top.safetensors").write_bytes(b"1")
    files = folder_files([str(r1), str(r2)], "pack")
    assert list(files) == ["a.safetensors", "B.safetensors", "c.safetensors"]
    assert files["a.safetensors"].startswith(str(r1))
    assert resolve_in_folder(files, "../../evil/a.safetensors") == files["a.safetensors"]
    assert resolve_in_folder(files, "nope.safetensors") is None
    rows = folder_listing(files)
    assert rows[1] == {"index": 2, "filename": "B.safetensors", "present": True, "size": 2, "size_str": "2 B"}
    assert list_subfolders([str(r1), str(r2)]) == ["", "pack"]
    assert list(folder_files([str(r1)], "")) == ["top.safetensors"]


def test_apply_planned_passes_none_for_zero_strength_sides() -> None:
    calls: list[tuple[object, object]] = []

    def load(m: object, c: object, sd: object, sm: float, sc: float) -> tuple[object, object]:
        calls.append((m, c))
        return ("M2" if m is not None else None), ("C2" if c is not None else None)

    entry = LoraEntry(name="x")
    assert apply_planned(load, "M", "C", {}, PlannedLora(entry, "p", 0.0, 0.5)) == ("M", "C2")
    assert apply_planned(load, "M", "C", {}, PlannedLora(entry, "p", 0.7, 0.0)) == ("M2", "C")
    assert apply_planned(load, "M", None, {}, PlannedLora(entry, "p", 0.7, 0.4)) == ("M2", None)
    assert calls == [(None, "C"), ("M", None), ("M", None)]
