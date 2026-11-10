"""Batch Timer: counts completed items across queued prompts for the canvas stopwatch.

The node ticks once per execution (wire `trigger` from the end of the workflow so the
tick fires after that step). The server only keeps the counters; the clock itself is
drawn by the frontend. Runs are keyed by `str(unique_id)`, which inside a subgraph is the
full execution path such as `a:b`. Keys are matched exactly: the frontend resolves which
paths belong to which node and sends them back for resets.

Run lifecycle: a run starts at the first tick of a batch (its `started_at` is the batch's
first `execution_start` when the frontend armed it, so item 1 is included) and ends when
`completed >= total`. A run abandoned by an error or interrupt is dropped by the frontend's
reset; `/state` also flags a run `stale` when ComfyUI's queue is idle and no tick arrived for
`STALE_AFTER` seconds, so a reloaded page never resumes it as RUNNING.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from comfy_api.latest import io

from ._comfy import queue_busy, read_json_object, send_sync

if TYPE_CHECKING:
    from aiohttp import web

EVENT = "jezzwtf.timer_update"
MAX_STAMPS = 64
STALE_AFTER = 15.0
MAX_ARM_AGE = 24 * 3600.0


@dataclass
class Run:
    active: bool
    completed: int
    total: int
    started_at: float
    stamps: list[float] = field(default_factory=list)
    run_id: str = ""
    last_tick: float = 0.0


class TimerRuns:
    """Thread-safe store of per-node batch runs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, Run] = {}
        self._armed_at: float | None = None

    def arm(self, now: float | None = None) -> bool:
        """Note that a prompt started executing. Ignored while a run is active (later prompts of a batch)."""
        stamp = time.time() if now is None else now
        with self._lock:
            if any(r.active for r in self._runs.values()):
                return False
            self._armed_at = stamp
            return True

    def tick(self, node_id: str, total: int, now: float | None = None) -> tuple[Run, float]:
        """Count one finished item. Returns a copy of the run and the timestamp used."""
        stamp = time.time() if now is None else now
        with self._lock:
            run = self._runs.get(node_id)
            if run is None or not run.active or run.total != total:
                armed = self._armed_at
                begun = armed if armed is not None and 0 <= stamp - armed <= MAX_ARM_AGE else stamp
                run = Run(active=True, completed=0, total=total, started_at=begun, run_id=uuid.uuid4().hex[:12])
                self._runs[node_id] = run
            run.completed += 1
            run.stamps.append(stamp)
            del run.stamps[:-MAX_STAMPS]
            run.last_tick = stamp
            if run.completed >= run.total:
                run.active = False
            return Run(run.active, run.completed, run.total, run.started_at, list(run.stamps),
                       run.run_id, run.last_tick), stamp

    def reset(self, node_ids: str | list[str] | None = None) -> int:
        """Drop the runs under exactly these keys (execution paths), or all runs. Returns how many went."""
        with self._lock:
            self._armed_at = None
            if node_ids is None:
                count = len(self._runs)
                self._runs.clear()
                return count
            doomed = [node_ids] if isinstance(node_ids, str) else node_ids
            return sum(1 for k in doomed if self._runs.pop(k, None) is not None)

    def snapshot(self, now: float | None = None, busy: bool | None = None) -> dict[str, dict[str, object]]:
        """Runs by key. `busy` is ComfyUI's queue state (None = unknown); with it, idle + silent runs are `stale`."""
        stamp = time.time() if now is None else now
        with self._lock:
            out: dict[str, dict[str, object]] = {}
            for k, v in self._runs.items():
                d: dict[str, object] = asdict(v)
                d["stale"] = bool(v.active and busy is False and stamp - v.last_tick > STALE_AFTER)
                out[k] = d
            return out


RUNS = TimerRuns()


class JWTFTimer(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="JWTFTimer",
            display_name='Batch Timer',
            category='JezzWTF/utils',
            inputs=[
                io.Int.Input("total_images", default=1, min=1, max=999999, tooltip="Number of images expected in the run, used as the target for the progress counter."),
                io.AnyType.Input("trigger", optional=True, tooltip="Optional upstream connection that makes the timer tick after the connected work completes."),
            ],
            outputs=[],
            hidden=[io.Hidden.unique_id],
            is_output_node=True,
        )

    @classmethod
    def fingerprint_inputs(cls, **_: object) -> float:
        return float("nan")

    @classmethod
    def execute(cls, total_images: int, trigger: object = None) -> io.NodeOutput:
        unique_id = cls.hidden.unique_id
        node_id = "" if unique_id is None else str(unique_id)
        run, now = RUNS.tick(node_id, int(total_images))
        send_sync(EVENT, {"node_id": node_id, "current": run.completed, "total": run.total,
                          "started_at": run.started_at, "now": now, "run_id": run.run_id})
        return io.NodeOutput()


def register_routes(routes: "web.RouteTableDef") -> None:
    from aiohttp import web

    @routes.get("/jezzwtf/timer/state")
    async def _state(_request: web.Request) -> web.Response:
        now = time.time()
        return web.json_response({"now": now, "runs": RUNS.snapshot(now, queue_busy())})

    @routes.post("/jezzwtf/timer/arm")
    async def _arm(_request: web.Request) -> web.Response:
        RUNS.arm()
        return web.json_response({"status": "ok"})

    @routes.post("/jezzwtf/timer/reset")
    async def _reset(request: web.Request) -> web.Response:
        body = await read_json_object(request)
        ids: list[str] | None = None
        if body is not None:
            raw_many = body.get("node_ids")
            if isinstance(raw_many, list):
                ids = [str(x) for x in raw_many[:256]]
            elif body.get("node_id") is not None:
                ids = [str(body["node_id"])]
        RUNS.reset(ids)
        return web.json_response({"status": "ok"})


NODES = [JWTFTimer]
