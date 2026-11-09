// Run Timer: pure logic (formatting, stats, filtering, export, run tracking). No DOM, no ComfyUI imports,
// so it loads under plain Node for tests.

export const TIMER_CLASS = "JWTFRunTimer";
export const STATUSES = ["ok", "error", "interrupted", "unknown"];
export const MAX_SLOWEST = 5;
export const MAX_TRACKED = 32;
export const MAX_JOURNAL = 32;

const isNum = (v) => typeof v === "number" && Number.isFinite(v);

// ------------------------------------------------------------------ formatting (truncating, never rounding up)

/** "850 ms", "12.3s", "2m 05s", "1h 02m 03s"; "--" when there is no duration. */
export function formatDuration(ms) {
  if (!isNum(ms) || ms < 0) return "--";
  if (ms < 1000) return `${Math.floor(ms)} ms`;
  const tenths = Math.floor(ms / 100);
  if (tenths < 600) return `${Math.floor(tenths / 10)}.${tenths % 10}s`;
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  const two = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${h}h ${two(m)}m ${two(s)}s` : `${m}m ${two(s)}s`;
}

/** Stopwatch face: "00:12.3", or "1:02:03.4" from an hour up. */
export function formatClock(ms) {
  const safe = isNum(ms) && ms > 0 ? ms : 0;
  const tenths = Math.floor(safe / 100) % 10;
  const totalSec = Math.floor(safe / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  const two = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${two(m)}:${two(s)}.${tenths}` : `${two(m)}:${two(s)}.${tenths}`;
}

/** Short stopwatch for the minimized chip: "12s", "2:05", "1:02:03". */
export function formatChip(ms) {
  const safe = isNum(ms) && ms > 0 ? ms : 0;
  const totalSec = Math.floor(safe / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  const two = (n) => String(n).padStart(2, "0");
  if (h > 0) return `${h}:${two(m)}:${two(s)}`;
  return m > 0 ? `${m}:${two(s)}` : `${s}s`;
}

export function timeAgo(ts, now) {
  if (!isNum(ts) || !isNum(now)) return "";
  const sec = Math.floor((now - ts) / 1000);
  if (sec < 5) return "just now";
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.floor(hr / 24)}d ago`;
}

export const runName = (run) => run.label || run.workflow || "Untitled run";

// ------------------------------------------------------------------ stats and filters

/** count = every run given; timed = the ones with a usable duration (unknown runs have none). */
export function computeStats(runs) {
  const durations = runs.filter((r) => r.status !== "unknown" && isNum(r.duration_ms) && r.duration_ms >= 0).map((r) => r.duration_ms);
  const out = { count: runs.length, timed: durations.length, avg: null, median: null, best: null, worst: null, total: 0 };
  if (!durations.length) return out;
  const sorted = [...durations].sort((a, b) => a - b);
  const total = sorted.reduce((a, b) => a + b, 0);
  const mid = sorted.length >> 1;
  out.total = total;
  out.avg = total / sorted.length;
  out.median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  out.best = sorted[0];
  out.worst = sorted[sorted.length - 1];
  return out;
}

/** filter = { label: string | null, status: string | null }; null means "all", label "" means unlabeled. */
export function filterRuns(runs, filter = {}) {
  const { label = null, status = null } = filter;
  return runs.filter((r) => (label === null || r.label === label) && (status === null || r.status === status));
}

export function uniqueLabels(runs) {
  return [...new Set(runs.map((r) => r.label))].sort((a, b) => a.localeCompare(b));
}

/** Newest run (by start) of `runs`, optionally limited to a label. */
export function newestRun(runs, label = null) {
  let best = null;
  for (const r of runs) {
    if (label !== null && r.label !== label) continue;
    if (!best || r.started_at > best.started_at) best = r;
  }
  return best;
}

/** What a node shows: last run, plus average and best over its successful runs. A named node only counts its own label. */
export function nodeSummary(runs, label) {
  const scope = label ? filterRuns(runs, { label }) : runs;
  const ok = scope.filter((r) => r.status === "ok");
  const stats = computeStats(ok);
  const last = newestRun(scope);
  return {
    last: last ? { ms: last.duration_ms, status: last.status } : null,
    avg: stats.avg,
    best: stats.best,
    count: ok.length,
  };
}

// ------------------------------------------------------------------ export

const CSV_COLUMNS = ["id", "prompt_id", "started_at", "started_at_ms", "duration_ms", "duration", "status", "label", "workflow", "node_count", "slowest_nodes", "approx_start"];

function csvCell(value, isText = false) {
  let s = value === null || value === undefined ? "" : String(value);
  if (isText && /^[=+\-@\t\r]/.test(s)) s = `'${s}`; // keep spreadsheets from running a label as a formula
  return /[",\r\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}

export function toCsv(runs) {
  const lines = [CSV_COLUMNS.join(",")];
  for (const r of runs) {
    const slowest = (r.slowest ?? []).map((n) => `${n.title}=${n.ms}ms`).join("; ");
    lines.push([
      csvCell(r.id), csvCell(r.prompt_id), csvCell(new Date(r.started_at).toISOString()), csvCell(r.started_at),
      csvCell(r.duration_ms), csvCell(r.duration_ms === null ? "" : formatDuration(r.duration_ms)), csvCell(r.status),
      csvCell(r.label, true), csvCell(r.workflow, true), csvCell(r.node_count), csvCell(slowest, true), csvCell(r.approx ? "yes" : "no"),
    ].join(","));
  }
  return `${lines.join("\r\n")}\r\n`;
}

export const toJson = (runs) => `${JSON.stringify(runs, null, 2)}\n`;

export function exportName(kind, date) {
  const p = (n) => String(n).padStart(2, "0");
  return `run_history-${date.getFullYear()}${p(date.getMonth() + 1)}${p(date.getDate())}-${p(date.getHours())}${p(date.getMinutes())}.${kind}`;
}

// ------------------------------------------------------------------ per-node timing

/** Attributes wall time to the node that was executing between two `executing` events. */
export class NodeTimeline {
  constructor() {
    this.current = null;
    this.totals = new Map();
  }

  /** A node started executing (key null = the prompt finished); the previous node's span ends here. */
  enter(key, title, ts) {
    this.leave(ts);
    if (key === null || key === undefined) return;
    this.current = { key: String(key), title: String(title || key), ts };
  }

  leave(ts) {
    const cur = this.current;
    if (!cur) return;
    this.current = null;
    const ms = Math.max(0, ts - cur.ts);
    const prev = this.totals.get(cur.key);
    if (prev) prev.ms += ms;
    else this.totals.set(cur.key, { title: cur.title, ms });
  }

  slowest(limit = MAX_SLOWEST) {
    return [...this.totals.values()]
      .filter((n) => n.ms >= 1)
      .sort((a, b) => b.ms - a.ms)
      .slice(0, limit)
      .map((n) => ({ title: n.title, ms: Math.floor(n.ms) }));
  }
}

// ------------------------------------------------------------------ prompt inspection

/** Look through an API-format prompt (muted and bypassed nodes are already absent from it). */
export function scanPrompt(prompt) {
  const out = { hasTimer: false, label: "", nodeCount: 0, titles: {} };
  if (!prompt || typeof prompt !== "object") return out;
  const ids = Object.keys(prompt).sort((a, b) => Number(a) - Number(b) || a.localeCompare(b));
  out.nodeCount = ids.length;
  for (const id of ids) {
    const node = prompt[id];
    if (!node || typeof node !== "object") continue;
    const title = node._meta && typeof node._meta.title === "string" ? node._meta.title : "";
    out.titles[id] = title || String(node.class_type ?? id);
    if (node.class_type !== TIMER_CLASS) continue;
    out.hasTimer = true;
    const raw = node.inputs && node.inputs.label;
    if (!out.label && typeof raw === "string" && raw.trim()) out.label = raw.trim();
  }
  return out;
}

/** Real start/end/status of a finished prompt from its /history entry (works for runs that ended while the tab was closed). */
export function outcomeFromHistory(item) {
  const status = item && item.status;
  if (!status || typeof status !== "object") return null;
  let start = null;
  let end = null;
  let kind = null;
  const map = { execution_success: "ok", execution_error: "error", execution_interrupted: "interrupted" };
  for (const m of Array.isArray(status.messages) ? status.messages : []) {
    if (!Array.isArray(m) || m.length < 2 || !m[1] || typeof m[1] !== "object") continue;
    const ts = isNum(m[1].timestamp) ? m[1].timestamp : null;
    if (m[0] === "execution_start") start = ts;
    else if (map[m[0]]) { kind = map[m[0]]; end = ts; }
  }
  if (!kind) {
    if (status.status_str === "success") kind = "ok";
    else if (status.status_str === "error") kind = "error";
    else return null;
  }
  return { status: kind, startedAt: start, endedAt: end, durationMs: start !== null && end !== null ? Math.max(0, end - start) : null };
}

// ------------------------------------------------------------------ run tracking

/** Tracks runs by prompt_id. Several prompts may be queued; only one executes at a time. */
export class RunTracker {
  constructor() {
    this.runs = new Map();
    this.currentId = null;
  }

  start(promptId, info) {
    const run = {
      promptId, startedAt: info.startedAt, label: info.label ?? "", workflow: info.workflow ?? "", nodeCount: info.nodeCount ?? 0,
      hasTimer: info.hasTimer !== false, approx: !!info.approx, titles: info.titles ?? {}, timeline: new NodeTimeline(), classified: null,
    };
    this.runs.delete(promptId);
    this.runs.set(promptId, run);
    this.currentId = promptId;
    while (this.runs.size > MAX_TRACKED) this.runs.delete(this.runs.keys().next().value);
    return run;
  }

  get(promptId) { return this.runs.get(promptId) ?? null; }

  /** An `executing` event; the event carries no prompt id, so it belongs to the run that started last. */
  executing(nodeKey, title, ts) {
    const run = this.currentId ? this.runs.get(this.currentId) : null;
    if (run) run.timeline.enter(nodeKey, title, ts);
  }

  /** Remove a run and close its last node span. Returns the run, or null when it was not tracked. */
  finish(promptId, endedAt) {
    const run = this.runs.get(promptId);
    if (!run) return null;
    run.timeline.leave(endedAt);
    this.runs.delete(promptId);
    if (this.currentId === promptId) this.currentId = this.runs.size ? [...this.runs.keys()].at(-1) : null;
    return run;
  }

  discard(promptId) { return this.finish(promptId, 0); }

  /** Runs worth showing on a stopwatch (a timer node is in the graph). */
  active() { return [...this.runs.values()].filter((r) => r.hasTimer); }

  /** The run the stopwatch follows: the most recently started one. */
  primary() {
    const a = this.active();
    return a.length ? a[a.length - 1] : null;
  }
}

/** The record to POST for a run that has ended. `durationMs` null only for status "unknown". */
export function buildRecord(run, status, endedAt, workflow) {
  const known = status !== "unknown" && isNum(endedAt);
  return {
    prompt_id: run.promptId,
    label: run.label,
    started_at: Math.floor(run.startedAt),
    duration_ms: known ? Math.max(0, Math.floor(endedAt - run.startedAt)) : null,
    status,
    workflow: workflow || run.workflow || "",
    node_count: run.nodeCount,
    slowest: known ? run.timeline.slowest() : [],
    approx: run.approx,
  };
}

// ------------------------------------------------------------------ journal (runs the browser must not forget across a reload)

/** Parse the localStorage journal defensively: { [promptId]: { started_at, label, workflow, node_count, approx } }. */
export function parseJournal(text) {
  let doc;
  try { doc = JSON.parse(text || "{}"); } catch { return {}; }
  if (!doc || typeof doc !== "object" || Array.isArray(doc)) return {};
  const out = {};
  for (const [id, e] of Object.entries(doc).slice(-MAX_JOURNAL)) {
    if (!e || typeof e !== "object" || !isNum(e.started_at)) continue;
    out[id] = {
      started_at: e.started_at,
      label: typeof e.label === "string" ? e.label : "",
      workflow: typeof e.workflow === "string" ? e.workflow : "",
      node_count: isNum(e.node_count) ? e.node_count : 0,
      approx: e.approx === true,
    };
  }
  return out;
}

export function journalEntry(run) {
  return { started_at: run.startedAt, label: run.label, workflow: run.workflow, node_count: run.nodeCount, approx: run.approx };
}

/** Which of the server's queue entries are running/pending, from GET /queue ({queue_running, queue_pending}). */
export function parseQueue(body) {
  if (!body || typeof body !== "object") return null;
  const index = (list) => {
    const map = new Map();
    for (const item of Array.isArray(list) ? list : []) {
      if (Array.isArray(item) && typeof item[1] === "string") map.set(item[1], item[2] ?? null);
    }
    return map;
  };
  return { running: index(body.queue_running), pending: index(body.queue_pending) };
}
