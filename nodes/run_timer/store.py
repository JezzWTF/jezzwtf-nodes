"""Run Timer history: record validation and the persistent, bounded, corruption-safe store.

Pure Python with no ComfyUI imports, so it can be tested on its own. The store keeps at most
`MAX_RUNS` records, writes them atomically (unique temp file in the same folder, fsync, replace),
and never overwrites a file it could not parse: the unreadable file is copied to a
`run_history.corrupt-*.json` backup first, and if that copy fails the store goes read-only.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Final, TypedDict

log = logging.getLogger("jezzwtf.run_timer")

MAX_RUNS: Final = 500
MAX_BACKUPS: Final = 5
MAX_LABEL: Final = 120
MAX_WORKFLOW: Final = 200
MAX_TITLE: Final = 120
MAX_SLOWEST: Final = 5
MAX_NODE_COUNT: Final = 1_000_000
MAX_DURATION_MS: Final = 30 * 24 * 3600 * 1000
MIN_STARTED_AT: Final = 946_684_800_000  # 2000-01-01
MAX_STARTED_AT: Final = 4_102_444_800_000  # 2100-01-01, the bound for records already on disk
FUTURE_SLOP_MS: Final = 24 * 3600 * 1000
FORMAT_VERSION: Final = 1
STATUSES: Final = ("ok", "error", "interrupted", "unknown")

_PROMPT_ID = re.compile(r"^[A-Za-z0-9_.:\-]{1,128}$")
_RECORD_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


class SlowNode(TypedDict):
    title: str
    ms: int


class RunRecord(TypedDict):
    id: str
    prompt_id: str
    label: str
    started_at: int
    duration_ms: int | None
    status: str
    workflow: str
    node_count: int
    slowest: list[SlowNode]
    approx: bool
    recorded_at: int


class RecordError(ValueError):
    """A record failed validation; the message names the offending field."""


class StoreUnavailable(RuntimeError):
    """The history file is protected (unreadable and could not be backed up) or could not be written."""


def now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------- validation

def _clean_text(value: object, name: str, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RecordError(f"{name} must be a string")
    cleaned = "".join(ch for ch in value if ch.isprintable()).strip()
    return cleaned[:limit]


def _whole_number(value: object, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecordError(f"{name} must be a number")
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")) or not value.is_integer():
            raise RecordError(f"{name} must be a whole number")
        value = int(value)
    if value < low or value > high:
        raise RecordError(f"{name} is out of range")
    return value


def _slowest(value: object) -> list[SlowNode]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RecordError("slowest must be a list")
    out: list[SlowNode] = []
    for item in value[:MAX_SLOWEST]:
        if not isinstance(item, Mapping):
            raise RecordError("slowest entries must be objects")
        title = _clean_text(item.get("title"), "slowest.title", MAX_TITLE)
        ms = _whole_number(item.get("ms"), "slowest.ms", 0, MAX_DURATION_MS)
        out.append({"title": title or "node", "ms": ms})
    return out


def parse_record(body: Mapping[str, object], now: int | None = None, *, trusted: bool = False) -> RunRecord:
    """Validate an incoming (or, with `trusted`, previously stored) record into its canonical form.

    Untrusted input never chooses its own `id` or `recorded_at`; the server assigns both.
    """
    stamp = now_ms() if now is None else now
    prompt_id = body.get("prompt_id")
    if not isinstance(prompt_id, str) or not _PROMPT_ID.match(prompt_id):
        raise RecordError("prompt_id must be 1-128 characters of letters, digits and _ . : -")
    status = body.get("status")
    if not isinstance(status, str) or status not in STATUSES:
        raise RecordError("status must be one of " + ", ".join(STATUSES))
    upper = MAX_STARTED_AT if trusted else stamp + FUTURE_SLOP_MS  # a clock that moved must not erase stored history
    started_at = _whole_number(body.get("started_at"), "started_at", MIN_STARTED_AT, upper)
    raw_duration = body.get("duration_ms")
    duration: int | None
    if raw_duration is None:
        if status != "unknown":
            raise RecordError("duration_ms is required unless status is unknown")
        duration = None
    else:
        duration = _whole_number(raw_duration, "duration_ms", 0, MAX_DURATION_MS)
    approx = body.get("approx", False)
    if not isinstance(approx, bool):
        raise RecordError("approx must be a boolean")
    record_id: str
    recorded_at: int
    if trusted:
        stored_id = body.get("id")
        if not isinstance(stored_id, str) or not _RECORD_ID.match(stored_id):
            raise RecordError("id is invalid")
        record_id = stored_id
        recorded_at = _whole_number(body.get("recorded_at"), "recorded_at", 0, MAX_STARTED_AT)
    else:
        record_id = uuid.uuid4().hex[:16]
        recorded_at = stamp
    return {
        "id": record_id,
        "prompt_id": prompt_id,
        "label": _clean_text(body.get("label"), "label", MAX_LABEL),
        "started_at": started_at,
        "duration_ms": duration,
        "status": status,
        "workflow": _clean_text(body.get("workflow"), "workflow", MAX_WORKFLOW),
        "node_count": _whole_number(body.get("node_count", 0), "node_count", 0, MAX_NODE_COUNT),
        "slowest": _slowest(body.get("slowest")),
        "approx": approx,
        "recorded_at": recorded_at,
    }


# ---------------------------------------------------------------- store

class HistoryStore:
    """Thread-safe, bounded run history persisted as JSON at `path`."""

    def __init__(self, path: Path | str, max_runs: int = MAX_RUNS) -> None:
        self._path = Path(path)
        self._max = max(1, int(max_runs))
        self._lock = threading.RLock()
        self._runs: list[RunRecord] | None = None  # oldest first
        self._locked_reason: str | None = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def locked_reason(self) -> str | None:
        return self._locked_reason

    # -- loading

    def _backup_bad_file(self, reason: str) -> None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = self._path.with_name(f"{self._path.stem}.corrupt-{stamp}-{uuid.uuid4().hex[:6]}{self._path.suffix}")
        try:
            target.write_bytes(self._path.read_bytes())
        except OSError as exc:
            self._locked_reason = f"{reason}; backup failed: {exc}"
            log.error("run_timer: %s. Could not back up %s, history is read-only: %s", reason, self._path, exc)
            return
        log.warning("run_timer: %s. Backed up %s to %s", reason, self._path.name, target.name)
        backups = sorted(self._path.parent.glob(f"{self._path.stem}.corrupt-*{self._path.suffix}"))
        for old in backups[:-MAX_BACKUPS]:
            try:
                old.unlink()
            except OSError:
                pass

    def _read_file(self) -> list[RunRecord]:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except (OSError, UnicodeDecodeError) as exc:
            self._backup_bad_file(f"history is unreadable ({exc})")
            return []
        if not raw.strip():
            return []
        try:
            doc = json.loads(raw)
        except (json.JSONDecodeError, RecursionError) as exc:
            self._backup_bad_file(f"history is not valid JSON ({exc})")
            return []
        entries = doc.get("runs") if isinstance(doc, dict) else None
        if not isinstance(entries, list):
            self._backup_bad_file("history has an unexpected shape")
            return []
        runs: list[RunRecord] = []
        seen: set[str] = set()
        seen_ids: set[str] = set()
        dropped = max(0, len(entries) - self._max * 4)
        for entry in entries[-self._max * 4:]:
            try:
                if not isinstance(entry, Mapping):
                    raise RecordError("entry is not an object")
                record = parse_record(entry, trusted=True)
            except RecordError:
                dropped += 1
                continue
            if record["prompt_id"] in seen or record["id"] in seen_ids:
                dropped += 1
                continue
            seen.add(record["prompt_id"])
            seen_ids.add(record["id"])
            runs.append(record)
        if dropped:
            self._backup_bad_file(f"{dropped} invalid history entries were dropped")
        return runs[-self._max:]

    def _load(self) -> list[RunRecord]:
        if self._runs is None:
            self._runs = self._read_file()
        return self._runs

    # -- writing

    def _write(self, runs: list[RunRecord]) -> None:
        if self._locked_reason is not None:
            raise StoreUnavailable(self._locked_reason)
        payload = json.dumps({"version": FORMAT_VERSION, "runs": runs}, separators=(",", ":"))
        tmp_path: str | None = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=self._path.parent, prefix=".run_history.", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self._path)
            tmp_path = None
        except OSError as exc:
            raise StoreUnavailable(f"could not write history: {exc}") from exc
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    # -- public API

    def snapshot(self, limit: int | None = None) -> list[RunRecord]:
        """Newest first (by start time)."""
        with self._lock:
            ordered = sorted(self._load(), key=lambda r: (r["started_at"], r["recorded_at"]), reverse=True)
        return ordered if limit is None else ordered[: max(0, limit)]

    def add(self, record: RunRecord) -> tuple[RunRecord, bool]:
        """Append a record. A record for an already-stored prompt_id is not added again: (existing, False)."""
        with self._lock:
            current = self._load()
            for existing in current:
                if existing["prompt_id"] == record["prompt_id"]:
                    return existing, False
            updated = (current + [record])[-self._max:]
            self._write(updated)
            self._runs = updated
            return record, True

    def delete(self, record_id: str) -> bool:
        with self._lock:
            current = self._load()
            updated = [r for r in current if r["id"] != record_id]
            if len(updated) == len(current):
                return False
            self._write(updated)
            self._runs = updated
            return True

    def clear(self) -> int:
        with self._lock:
            count = len(self._load())
            if count:
                self._write([])
                self._runs = []
            return count


def default_history_path() -> Path:
    """`<ComfyUI user dir>/jezzwtf/run_history.json`; a temp folder when ComfyUI is not importable."""
    try:
        import folder_paths  # type: ignore[import-not-found]

        base = Path(str(folder_paths.get_user_directory()))
    except Exception:  # noqa: BLE001 - tests and linters
        base = Path(tempfile.gettempdir()) / "jezzwtf_user"
    return base / "jezzwtf" / "run_history.json"


_store: HistoryStore | None = None
_store_lock = threading.Lock()


def get_store() -> HistoryStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = HistoryStore(default_history_path())
        return _store
