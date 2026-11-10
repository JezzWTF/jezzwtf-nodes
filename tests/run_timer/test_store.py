"""History store, record validation, live registry and the node itself (no ComfyUI needed)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from run_timer import store as S
from run_timer.live import MAX_LIVE, LiveRuns
from run_timer.node import JWTFRunTimer, NODES
from v3_helpers import legacy, legacy_spec, overrides

NOW = 1_800_000_000_000


def body(**over: object) -> dict[str, object]:
    base: dict[str, object] = {"prompt_id": "p-1", "status": "ok", "started_at": NOW - 5000, "duration_ms": 4200, "label": "  hero  "}
    base.update(over)
    return base


def record(i: int, **over: object) -> S.RunRecord:
    return S.parse_record(body(prompt_id=f"p-{i}", started_at=NOW - 100000 + i, **over), NOW)


# ---------------------------------------------------------------- validation

def test_parse_assigns_server_fields_and_cleans_text() -> None:
    rec = S.parse_record(body(id="evil", recorded_at=1), NOW)
    assert rec["id"] != "evil" and rec["recorded_at"] == NOW
    assert rec["label"] == "hero" and rec["workflow"] == "" and rec["node_count"] == 0 and rec["slowest"] == [] and rec["approx"] is False


def test_parse_strips_control_characters_and_truncates() -> None:
    rec = S.parse_record(body(label="a\nb\x00c" + "x" * 500, workflow="w" * 500), NOW)
    assert rec["label"].startswith("abc") and len(rec["label"]) == S.MAX_LABEL and len(rec["workflow"]) == S.MAX_WORKFLOW


@pytest.mark.parametrize(
    "over",
    [
        {"prompt_id": ""}, {"prompt_id": 5}, {"prompt_id": "a b"}, {"prompt_id": "x" * 200},
        {"status": "done"}, {"status": None},
        {"started_at": "now"}, {"started_at": True}, {"started_at": 5}, {"started_at": NOW + 10**10}, {"started_at": 1.5},
        {"duration_ms": -1}, {"duration_ms": S.MAX_DURATION_MS + 1}, {"duration_ms": None}, {"duration_ms": float("nan")}, {"duration_ms": "9"},
        {"label": 7}, {"workflow": []}, {"node_count": -1}, {"node_count": "3"}, {"approx": "yes"},
        {"slowest": "x"}, {"slowest": ["x"]}, {"slowest": [{"title": "t", "ms": -4}]}, {"slowest": [{"title": 3, "ms": 4}]},
    ],
)
def test_parse_rejects_bad_fields(over: dict[str, object]) -> None:
    with pytest.raises(S.RecordError):
        S.parse_record(body(**over), NOW)


def test_unknown_status_may_lack_a_duration_and_slowest_is_capped() -> None:
    rec = S.parse_record(body(status="unknown", duration_ms=None, slowest=[{"title": f"n{i}", "ms": i} for i in range(9)], approx=True), NOW)
    assert rec["duration_ms"] is None and len(rec["slowest"]) == S.MAX_SLOWEST and rec["approx"] is True


def test_integral_floats_are_accepted() -> None:
    assert S.parse_record(body(duration_ms=12.0, started_at=float(NOW - 1)), NOW)["duration_ms"] == 12


# ---------------------------------------------------------------- store

def test_add_persists_and_dedupes_by_prompt_id(tmp_path: Path) -> None:
    path = tmp_path / "jezzwtf" / "run_history.json"
    store = S.HistoryStore(path)
    first, created = store.add(record(1))
    again, created_again = store.add(S.parse_record(body(prompt_id="p-1", duration_ms=1), NOW))
    assert created and not created_again and again["id"] == first["id"] and again["duration_ms"] == 4200
    reloaded = S.HistoryStore(path).snapshot()
    assert [r["prompt_id"] for r in reloaded] == ["p-1"]
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["version"] == 1 and len(doc["runs"]) == 1


def test_history_is_bounded_to_newest_and_listed_newest_first(tmp_path: Path) -> None:
    store = S.HistoryStore(tmp_path / "h.json", max_runs=5)
    for i in range(12):
        store.add(record(i))
    shown = store.snapshot()
    assert [r["prompt_id"] for r in shown] == [f"p-{i}" for i in (11, 10, 9, 8, 7)]
    assert len(json.loads((tmp_path / "h.json").read_text(encoding="utf-8"))["runs"]) == 5
    assert len(store.snapshot(2)) == 2


def test_default_bound_is_500(tmp_path: Path) -> None:
    store = S.HistoryStore(tmp_path / "h.json")
    for i in range(S.MAX_RUNS + 8):
        store.add(record(i))
    assert len(store.snapshot()) == S.MAX_RUNS


def test_delete_and_clear(tmp_path: Path) -> None:
    store = S.HistoryStore(tmp_path / "h.json")
    a, _ = store.add(record(1))
    store.add(record(2))
    assert store.delete(a["id"]) and not store.delete(a["id"]) and not store.delete("nope")
    assert [r["prompt_id"] for r in S.HistoryStore(tmp_path / "h.json").snapshot()] == ["p-2"]
    assert store.clear() == 1 and store.clear() == 0 and S.HistoryStore(tmp_path / "h.json").snapshot() == []


def test_atomic_write_leaves_no_temp_files_and_old_content_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "h.json"
    store = S.HistoryStore(path)
    store.add(record(1))
    assert [p.name for p in tmp_path.iterdir()] == ["h.json"]
    before = path.read_text(encoding="utf-8")

    def boom(src: str, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(S.StoreUnavailable):
        store.add(record(2))
    monkeypatch.undo()
    assert path.read_text(encoding="utf-8") == before
    assert [p.name for p in tmp_path.iterdir()] == ["h.json"]  # the temp file was cleaned up
    assert [r["prompt_id"] for r in store.snapshot()] == ["p-1"]  # memory rolled back with the file


def test_concurrent_writers_use_unique_temp_files(tmp_path: Path) -> None:
    import threading

    store = S.HistoryStore(tmp_path / "h.json")
    errors: list[BaseException] = []

    def work(n: int) -> None:
        try:
            for i in range(10):
                store.add(record(n * 100 + i))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(store.snapshot()) == 40
    assert len(S.HistoryStore(tmp_path / "h.json").snapshot()) == 40


@pytest.mark.parametrize("content", ["{not json", "[1,2,3]", '{"runs": "nope"}', "\x00\x01 garbage"])
def test_corrupt_file_is_backed_up_not_overwritten_by_loading(tmp_path: Path, content: str) -> None:
    path = tmp_path / "run_history.json"
    path.write_text(content, encoding="utf-8")
    store = S.HistoryStore(path)
    assert store.snapshot() == []
    backups = list(tmp_path.glob("run_history.corrupt-*.json"))
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == content
    assert path.read_text(encoding="utf-8") == content  # loading alone never rewrites the file
    store.add(record(1))  # a later write starts fresh, the backup keeps the old bytes
    assert backups[0].read_text(encoding="utf-8") == content
    assert len(S.HistoryStore(path).snapshot()) == 1


def test_invalid_entries_are_dropped_but_backed_up(tmp_path: Path) -> None:
    good = record(1)
    path = tmp_path / "run_history.json"
    original = json.dumps({"version": 1, "runs": [good, {"junk": True}, "x"]})
    path.write_text(original, encoding="utf-8")
    store = S.HistoryStore(path)
    assert [r["prompt_id"] for r in store.snapshot()] == ["p-1"]
    assert [b.read_text(encoding="utf-8") for b in tmp_path.glob("run_history.corrupt-*.json")] == [original]


def test_store_goes_read_only_when_the_backup_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "run_history.json"
    path.write_text("{broken", encoding="utf-8")
    real = Path.write_bytes

    def fail(self: Path, data: bytes) -> int:
        if "corrupt" in self.name:
            raise OSError("no space")
        return real(self, data)

    monkeypatch.setattr(Path, "write_bytes", fail)
    store = S.HistoryStore(path)
    assert store.snapshot() == [] and store.locked_reason is not None
    with pytest.raises(S.StoreUnavailable):
        store.add(record(1))
    assert path.read_text(encoding="utf-8") == "{broken"


def test_old_backups_are_pruned(tmp_path: Path) -> None:
    path = tmp_path / "run_history.json"
    for _ in range(S.MAX_BACKUPS + 3):
        path.write_text("{bad", encoding="utf-8")
        S.HistoryStore(path).snapshot()
    assert len(list(tmp_path.glob("run_history.corrupt-*.json"))) == S.MAX_BACKUPS


def test_missing_and_empty_files_are_fine(tmp_path: Path) -> None:
    assert S.HistoryStore(tmp_path / "none.json").snapshot() == []
    (tmp_path / "empty.json").write_text("  ", encoding="utf-8")
    assert S.HistoryStore(tmp_path / "empty.json").snapshot() == []
    assert not list(tmp_path.glob("*.corrupt-*"))


# ---------------------------------------------------------------- live registry and node

def test_live_registry_keeps_first_mark_and_is_bounded() -> None:
    live = LiveRuns()
    live.mark("a", "", 1000)
    live.mark("a", "named", 2000)
    assert live.snapshot(3000) == [{"prompt_id": "a", "executed_at": 1000, "label": "named"}]
    live.mark(None, "x", 1)
    for i in range(MAX_LIVE + 10):
        live.mark(f"p{i}", "", 5000 + i)
    assert len(live.snapshot(6000)) == MAX_LIVE
    assert live.snapshot(5000 + 49 * 3600 * 1000) == []


def test_node_contract() -> None:
    schema = JWTFRunTimer.GET_SCHEMA()
    assert NODES == [JWTFRunTimer] and schema.node_id == "JWTFRunTimer" and schema.display_name == "Run Timer"
    spec = legacy_spec(JWTFRunTimer)
    assert not spec.get("required") and set(spec["optional"]) == {"label"}
    assert spec["optional"]["label"][0] == "STRING" and not JWTFRunTimer.RETURN_TYPES
    assert schema.category == "JezzWTF/utils" and JWTFRunTimer.OUTPUT_NODE is True
    assert not overrides(JWTFRunTimer, "fingerprint_inputs")


def test_node_has_no_pass_through_slots() -> None:
    assert legacy(JWTFRunTimer.execute(label="x")) == ()
    assert legacy(JWTFRunTimer.execute()) == ()