from __future__ import annotations

import math

import pytest

import utility_core.timer as timer
from utility_core.timer import JWTFTimer, TimerRuns
from v3_helpers import hidden, legacy, overrides


def test_tick_counts_and_finishes() -> None:
    runs = TimerRuns()
    first, t0 = runs.tick("5", 3, now=100.0)
    assert (first.completed, first.total, first.active, first.started_at) == (1, 3, True, 100.0) and t0 == 100.0
    runs.tick("5", 3, now=101.0)
    last, _ = runs.tick("5", 3, now=102.0)
    assert last.completed == 3 and not last.active and last.stamps == [100.0, 101.0, 102.0]


def test_tick_restarts_when_inactive_or_total_changes() -> None:
    runs = TimerRuns()
    runs.tick("1", 1, now=10.0)  # completes immediately -> inactive
    again, _ = runs.tick("1", 1, now=20.0)
    assert again.completed == 1 and again.started_at == 20.0
    runs.tick("2", 5, now=30.0)
    runs.tick("2", 5, now=31.0)
    changed, _ = runs.tick("2", 8, now=40.0)
    assert changed.completed == 1 and changed.total == 8 and changed.started_at == 40.0


def test_stamps_keep_the_last_64() -> None:
    runs = TimerRuns()
    for i in range(100):
        run, _ = runs.tick("n", 1000, now=float(i))
    assert len(run.stamps) == 64 and run.stamps[0] == 36.0 and run.stamps[-1] == 99.0


def test_returned_run_is_a_copy() -> None:
    runs = TimerRuns()
    run, _ = runs.tick("n", 5, now=1.0)
    run.stamps.append(99.0)
    run.completed = 42
    assert runs.snapshot()["n"]["stamps"] == [1.0] and runs.snapshot()["n"]["completed"] == 1


def test_reset_matches_exact_execution_paths_only() -> None:
    runs = TimerRuns()
    for key in ("5", "12:5", "7:5", "50", "12"):
        runs.tick(key, 5, now=1.0)
    assert runs.reset("5") == 1  # a root id never takes subgraph instances with it
    assert set(runs.snapshot()) == {"12:5", "7:5", "50", "12"}
    assert runs.reset(["12:5", "nope"]) == 1
    assert runs.reset() == 3 and runs.snapshot() == {}


def test_run_start_uses_armed_execution_start() -> None:
    runs = TimerRuns()
    assert runs.arm(now=100.0)
    first, _ = runs.tick("n", 3, now=130.0)
    assert first.started_at == 100.0  # item 1 (30 s) is part of the run
    assert not runs.arm(now=131.0)  # later prompts of a running batch don't move the start
    assert runs.tick("n", 3, now=140.0)[0].started_at == 100.0
    runs.tick("n", 3, now=150.0)  # finished
    assert runs.arm(now=200.0)
    assert runs.tick("n", 3, now=210.0)[0].started_at == 200.0
    fresh = TimerRuns()
    assert fresh.tick("n", 3, now=5.0)[0].started_at == 5.0  # never armed: first tick


def test_run_ids_and_stale_flag() -> None:
    runs = TimerRuns()
    a, _ = runs.tick("n", 5, now=10.0)
    assert a.run_id and runs.tick("n", 5, now=11.0)[0].run_id == a.run_id
    runs.reset("n")
    assert runs.tick("n", 5, now=12.0)[0].run_id != a.run_id
    assert runs.snapshot(now=100.0, busy=False)["n"]["stale"] is True
    assert runs.snapshot(now=100.0, busy=True)["n"]["stale"] is False
    assert runs.snapshot(now=100.0, busy=None)["n"]["stale"] is False
    assert runs.snapshot(now=13.0, busy=False)["n"]["stale"] is False  # fresh tick


def test_validate_inputs_does_not_disable_link_type_checks() -> None:
    from utility_core._types import ANY

    # ComfyUI skips link type validation when VALIDATE_INPUTS declares `input_types`.
    assert not overrides(JWTFTimer, "validate_inputs")
    assert not ("IMAGE" != ANY)  # the wildcard trigger still accepts any link


def _run_timer(total: int, **kw: object) -> object:
    with hidden(JWTFTimer, unique_id="a:4"):
        return legacy(JWTFTimer.execute(total, **kw))


def test_node_shape_and_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(timer, "send_sync", lambda event, data: sent.append((event, data)))
    monkeypatch.setattr(timer, "RUNS", TimerRuns())
    spec = JWTFTimer.INPUT_TYPES()
    total_images = dict(spec["required"]["total_images"][1])
    assert total_images.pop("tooltip")
    assert total_images == {"default": 1, "min": 1, "max": 999999}
    assert "trigger" in spec["optional"] and spec["hidden"]["unique_id"] == ("UNIQUE_ID",)
    assert JWTFTimer.OUTPUT_NODE and not JWTFTimer.RETURN_TYPES
    assert math.isnan(JWTFTimer.fingerprint_inputs())
    assert _run_timer(2) == ()
    assert _run_timer(2, trigger=object()) == ()
    assert [e for e, _ in sent] == ["jezzwtf.timer_update"] * 2
    assert sent[1][1]["node_id"] == "a:4" and sent[1][1]["current"] == 2 and sent[1][1]["total"] == 2
    assert set(sent[1][1]) == {"node_id", "current", "total", "started_at", "now", "run_id"}
    assert not timer.RUNS.snapshot()["a:4"]["active"]
