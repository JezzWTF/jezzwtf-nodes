"""In-memory record of prompts whose Run Timer node has executed.

It answers one question after a page reload: when did the running prompt reach its timer node?
That lets the stopwatch resume even if the browser lost its own bookkeeping. Bounded and pruned.
"""
from __future__ import annotations

import threading
from typing import Final, TypedDict

MAX_LIVE: Final = 64
MAX_AGE_MS: Final = 48 * 3600 * 1000


class LiveRun(TypedDict):
    prompt_id: str
    executed_at: int
    label: str


class LiveRuns:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, LiveRun] = {}

    def mark(self, prompt_id: str | None, label: str, now_ms: int) -> None:
        """Remember when the first Run Timer node of `prompt_id` executed (later nodes do not move it)."""
        if not prompt_id:
            return
        with self._lock:
            existing = self._runs.get(prompt_id)
            if existing is None:
                self._runs[prompt_id] = {"prompt_id": prompt_id, "executed_at": now_ms, "label": label[:120]}
            elif label and not existing["label"]:
                existing["label"] = label[:120]
            self._prune(now_ms)

    def _prune(self, now_ms: int) -> None:
        for key in [k for k, v in self._runs.items() if now_ms - v["executed_at"] > MAX_AGE_MS]:
            del self._runs[key]
        while len(self._runs) > MAX_LIVE:
            del self._runs[next(iter(self._runs))]

    def snapshot(self, now_ms: int) -> list[LiveRun]:
        with self._lock:
            self._prune(now_ms)
            return [{"prompt_id": v["prompt_id"], "executed_at": v["executed_at"], "label": v["label"]} for v in self._runs.values()]


LIVE = LiveRuns()
