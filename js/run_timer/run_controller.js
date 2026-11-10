// Run Timer controller: listens to ComfyUI execution events, tracks runs by prompt_id, keeps the live stopwatch
// and talks to the history routes. No DOM here; the node widget and the panel subscribe to it.
import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import {
  MAX_JOURNAL, RunTracker, TIMER_CLASS, buildRecord, journalEntry, outcomeFromHistory, parseJournal, parseQueue, scanPrompt,
} from "./run_core.js";

const BASE = "/jezzwtf/run_timer";
const MUTATE = { "Content-Type": "application/json", "X-JezzWTF-RunTimer": "1" };
const GUARD_HEADER = { "X-JezzWTF-RunTimer": "1" };
const JOURNAL_KEY = "jezzwtf.runTimer.live";
const TICK_MS = 100;
const POLL_MS = 4000;
const MIN_AGE_BEFORE_POLL_CLOSE = 2500;
const MAX_PENDING_POSTS = 50;
const MAX_HISTORY = 500;
const MAX_NAMES = 64;

const isNum = (v) => typeof v === "number" && Number.isFinite(v);

function readStorage(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function writeStorage(key, value) {
  try { localStorage.setItem(key, value); } catch { /* storage blocked: the stopwatch still works, only reload-resume is lost */ }
}

function activeWorkflowName() {
  try {
    const wf = app.extensionManager?.workflow?.activeWorkflow;
    const name = wf?.filename ?? wf?.key ?? "";
    return typeof name === "string" ? name.replace(/\.json$/i, "") : "";
  } catch { return ""; }
}

/** Fallback when the prompt cannot be fetched: an active (not muted or bypassed) timer node in the open graphs. */
function openGraphTimer() {
  const found = { hasTimer: false, label: "" };
  try {
    const root = app.rootGraph ?? app.graph;
    const graphs = [root, ...(root?.subgraphs ? [...root.subgraphs.values()] : [])];
    for (const g of graphs) {
      for (const n of g?.nodes ?? g?._nodes ?? []) {
        if (n.type !== TIMER_CLASS || (n.mode ?? 0) !== 0) continue;
        found.hasTimer = true;
        const title = typeof n.title === "string" ? n.title.trim() : "";
        const v = title && title !== "Run Timer" ? title : n.widgets?.find((w) => w.name === "label")?.value;
        if (!found.label && typeof v === "string" && v.trim()) found.label = v.trim();
      }
    }
  } catch { /* graph not ready */ }
  return found;
}

export function createController() {
  const ac = new AbortController();
  const tracker = new RunTracker();
  const listeners = new Set();
  const names = new Map();
  const pendingPosts = [];
  let history = [];
  let skew = 0;
  let tickTimer = 0;
  let pollTimer = 0;
  let pollBusy = false;
  let destroyed = false;
  let loaded = false;
  let lastError = "";
  const oneShots = new Set();
  const hooks = { onRunStarted: null };
  let restoreQueuePrompt = null;

  const serverNow = () => Date.now() + skew;
  const notify = (kind) => { for (const fn of [...listeners]) { try { fn(kind); } catch { /* a bad subscriber must not stop the others */ } } };
  const later = (fn, ms) => { const id = setTimeout(() => { oneShots.delete(id); if (!destroyed) fn(); }, ms); oneShots.add(id); };

  // ---------------------------------------------------------------- journal

  function journal() { return parseJournal(readStorage(JOURNAL_KEY)); }
  function saveJournal(doc) {
    const keys = Object.keys(doc);
    for (const k of keys.slice(0, Math.max(0, keys.length - MAX_JOURNAL))) delete doc[k];
    writeStorage(JOURNAL_KEY, JSON.stringify(doc));
  }
  function journalSet(run) { const doc = journal(); doc[run.promptId] = journalEntry(run); saveJournal(doc); }
  function journalDel(pid) { const doc = journal(); if (pid in doc) { delete doc[pid]; saveJournal(doc); } }

  // ---------------------------------------------------------------- server calls

  async function getJson(path) {
    const res = await api.fetchApi(path);
    if (!res.ok) throw new Error(`${path} ${res.status}`);
    return res.json();
  }

  async function fetchQueue() {
    try { return parseQueue(await getJson("/queue")); } catch { return null; }
  }

  async function findPrompt(pid) {
    const queue = await fetchQueue();
    const live = queue?.running.get(pid) ?? queue?.pending.get(pid);
    if (live) return live;
    try {
      const body = await getJson(`/history/${encodeURIComponent(pid)}`);
      return body?.[pid]?.prompt?.[2] ?? null;
    } catch { return null; }
  }

  function upsert(rec) {
    history = [rec, ...history.filter((r) => r.id !== rec.id && r.prompt_id !== rec.prompt_id)]
      .sort((a, b) => b.started_at - a.started_at)
      .slice(0, MAX_HISTORY);
  }

  async function refreshHistory() {
    try {
      const body = await getJson(`${BASE}/history`);
      if (Array.isArray(body.runs)) history = body.runs;
      if (isNum(body.now)) skew = body.now - Date.now();
      loaded = true;
      lastError = "";
    } catch (err) {
      lastError = `Could not load history (${err.message})`;
    }
    notify("change");
  }

  async function post(draft) {
    const res = await api.fetchApi(`${BASE}/record`, { method: "POST", headers: MUTATE, body: JSON.stringify(draft) });
    if (!res.ok) {
      const retryable = res.status >= 500;
      const err = new Error(`record ${res.status}`);
      err.retryable = retryable;
      throw err;
    }
    return (await res.json()).run;
  }

  async function commit(draft) {
    try {
      upsert(await post(draft));
      lastError = "";
    } catch (err) {
      lastError = "A run could not be saved to the history file.";
      // Show it locally either way; keep retrying only for failures that can pass (server busy, offline).
      upsert({ ...draft, id: `local-${draft.prompt_id}`, recorded_at: Date.now(), local: true });
      if (err.retryable !== false && pendingPosts.length < MAX_PENDING_POSTS) pendingPosts.push(draft);
    }
    notify("change");
  }

  async function flushPending() {
    for (const draft of pendingPosts.splice(0, pendingPosts.length)) {
      try { upsert(await post(draft)); } catch (err) { if (err.retryable !== false) pendingPosts.push(draft); }
    }
  }

  // ---------------------------------------------------------------- timers

  function ensureTimers() {
    if (destroyed) return;
    if (!tickTimer) tickTimer = setInterval(() => notify("tick"), TICK_MS);
    if (!pollTimer) pollTimer = setInterval(poll, POLL_MS);
  }

  function stopTimersIfIdle() {
    if (tracker.active().length) return;
    clearInterval(tickTimer);
    clearInterval(pollTimer);
    tickTimer = pollTimer = 0;
  }

  // ---------------------------------------------------------------- run lifecycle

  function beginRun(pid, info) {
    const run = tracker.start(pid, info);
    journalSet(run);
    ensureTimers();
    return run;
  }

  function classify(run) {
    run.classified = (async () => {
      const scan = scanPrompt(await findPrompt(run.promptId));
      if (!scan.nodeCount) return; // prompt not found: keep the open-graph fallback
      run.nodeCount = scan.nodeCount;
      run.titles = scan.titles;
      if (scan.label) run.label = scan.label;
      journalSet(run);
    })().catch(() => { /* keep the fallback */ });
    run.classified.then(() => {
      if (destroyed) return;
      notify("change");
      hooks.onRunStarted?.(run);
    });
  }

  function onStart(detail) {
    const pid = detail?.prompt_id;
    if (typeof pid !== "string") return;
    const stamp = isNum(detail.timestamp) ? detail.timestamp : serverNow();
    if (isNum(detail.timestamp)) skew = detail.timestamp - Date.now();
    const fallback = openGraphTimer();
    const run = beginRun(pid, { startedAt: stamp, label: fallback.label, workflow: activeWorkflowName() });
    run.seenAt = Date.now();
    classify(run);
    notify("change");
  }

  function onExecuting(nodeId) {
    const key = nodeId === null || nodeId === undefined ? null : String(nodeId);
    const run = tracker.currentId ? tracker.get(tracker.currentId) : null;
    if (!run) return;
    let title = key;
    if (key !== null) {
      title = run.titles[key];
      if (!title) {
        try {
          const g = app.rootGraph ?? app.graph;
          const n = g?.getNodeById?.(Number.isNaN(Number(key)) ? key : Number(key));
          title = n?.title || n?.type;
        } catch { /* graph not ready */ }
      }
    }
    tracker.executing(key, title || key, serverNow());
  }

  async function onEnd(status, detail) {
    const pid = detail?.prompt_id;
    if (typeof pid !== "string") return;
    const run = tracker.get(pid);
    if (!run) return; // another client's prompt (interrupts are broadcast) or already settled
    const endedAt = isNum(detail.timestamp) ? detail.timestamp : serverNow();
    tracker.finish(pid, endedAt);
    stopTimersIfIdle();
    notify("change");
    await run.classified;
    journalDel(pid);
    await commit(buildRecord(run, status, endedAt, names.get(pid)));
  }

  /** A run that is no longer in ComfyUI's queue: take its real outcome from /history, or call it unknown. */
  async function settleFromHistory(run, journaled) {
    let outcome = null;
    try {
      const body = await getJson(`/history/${encodeURIComponent(run.promptId)}`);
      outcome = outcomeFromHistory(body?.[run.promptId]);
    } catch { /* history unreachable: unknown */ }
    journalDel(run.promptId);
    const exact = outcome && outcome.startedAt !== null && outcome.endedAt !== null;
    if (exact) run.startedAt = outcome.startedAt;
    const draft = buildRecord(run, exact ? outcome.status : "unknown", exact ? outcome.endedAt : null, names.get(run.promptId));
    if (!exact && journaled) draft.approx = true;
    await commit(draft);
  }

  async function poll() {
    if (pollBusy || destroyed) return;
    pollBusy = true;
    try {
      await flushPending();
      const queue = await fetchQueue();
      if (!queue) return;
      for (const run of tracker.active()) {
        if (queue.running.has(run.promptId) || queue.pending.has(run.promptId)) continue;
        if (Date.now() - (run.seenAt ?? 0) < MIN_AGE_BEFORE_POLL_CLOSE) continue;
        tracker.finish(run.promptId, serverNow());
        await settleFromHistory(run, false);
      }
      stopTimersIfIdle();
      notify("change");
    } finally {
      pollBusy = false;
    }
  }

  /** After a page load: resume runs that are still going, settle the ones that ended while the tab was away. */
  async function reconcileAtLoad() {
    const queue = await fetchQueue();
    const saved = journal();
    if (!queue) return; // cannot tell; the journal stays for the next load
    let liveRuns = [];
    try {
      const live = await getJson(`${BASE}/live`);
      liveRuns = Array.isArray(live.runs) ? live.runs : [];
      if (isNum(live.now)) skew = live.now - Date.now();
    } catch { /* no server-side hint */ }

    for (const [pid, entry] of Object.entries(saved)) {
      if (tracker.get(pid)) continue;
      const run = tracker.start(pid, {
        startedAt: entry.started_at, label: entry.label, workflow: entry.workflow, nodeCount: entry.node_count, approx: entry.approx, hasTimer: true,
      });
      run.seenAt = 0;
      run.classified = Promise.resolve();
      if (queue.running.has(pid) || queue.pending.has(pid)) continue;
      tracker.finish(pid, serverNow());
      await settleFromHistory(run, true);
    }
    for (const [pid, prompt] of queue.running) {
      if (tracker.get(pid)) continue;
      const scan = scanPrompt(prompt);
      const hint = liveRuns.find((r) => r.prompt_id === pid);
      const run = tracker.start(pid, {
        startedAt: isNum(hint?.executed_at) ? hint.executed_at : serverNow(), label: scan.label, nodeCount: scan.nodeCount,
        titles: scan.titles, approx: true, hasTimer: true,
      });
      run.seenAt = 0;
      run.classified = Promise.resolve();
      journalSet(run);
    }
    if (tracker.active().length) ensureTimers();
    notify("change");
  }

  // ---------------------------------------------------------------- wiring

  const onApi = (type, fn) => {
    const handler = (e) => { if (!destroyed) fn(e.detail); };
    api.addEventListener(type, handler, { signal: ac.signal });
    return () => api.removeEventListener(type, handler);
  };
  const detach = [
    onApi("execution_start", onStart),
    onApi("executing", onExecuting),
    onApi("execution_success", (d) => onEnd("ok", d)),
    onApi("execution_error", (d) => onEnd("error", d)),
    onApi("execution_interrupted", (d) => onEnd("interrupted", d)),
    onApi("status", (d) => { if (tracker.active().length && d?.exec_info?.queue_remaining === 0) later(poll, 1500); }),
    onApi("reconnected", () => { if (tracker.active().length) poll(); }),
  ];

  // Remember which workflow each prompt was queued from; the open tab can change before the run ends.
  try {
    const original = api.queuePrompt;
    if (typeof original === "function" && !original.__jwtfRunTimer) {
      const wrapped = async function (...args) {
        const name = activeWorkflowName();
        const res = await original.apply(this, args);
        if (res && typeof res.prompt_id === "string" && name) {
          names.set(res.prompt_id, name);
          while (names.size > MAX_NAMES) names.delete(names.keys().next().value);
        }
        return res;
      };
      wrapped.__jwtfRunTimer = true;
      api.queuePrompt = wrapped;
      restoreQueuePrompt = () => { if (api.queuePrompt === wrapped) api.queuePrompt = original; };
    }
  } catch { /* leave queuePrompt alone; the open tab's name is used instead */ }

  // ---------------------------------------------------------------- public surface

  const ready = (async () => {
    await refreshHistory();
    await reconcileAtLoad();
  })().catch(() => { /* the panel shows lastError */ });

  return {
    ready,
    hooks,
    get history() { return history; },
    get loaded() { return loaded; },
    get lastError() { return lastError; },
    get activeCount() { return tracker.active().length; },
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    /** The run the stopwatch follows, with its elapsed time on the server clock. */
    primary() {
      const run = tracker.primary();
      return run ? { run, elapsed: Math.max(0, serverNow() - run.startedAt) } : null;
    },
    refreshHistory,
    async deleteRun(id) {
      if (String(id).startsWith("local-")) { history = history.filter((r) => r.id !== id); notify("change"); return; }
      const res = await api.fetchApi(`${BASE}/history/${encodeURIComponent(id)}`, { method: "DELETE", headers: GUARD_HEADER });
      if (!res.ok && res.status !== 404) throw new Error(`delete ${res.status}`);
      history = history.filter((r) => r.id !== id);
      notify("change");
    },
    async clearAll() {
      const res = await api.fetchApi(`${BASE}/history`, { method: "DELETE", headers: GUARD_HEADER });
      if (!res.ok) throw new Error(`clear ${res.status}`);
      history = [];
      pendingPosts.length = 0;
      notify("change");
    },
    destroy() {
      destroyed = true;
      ac.abort();
      for (const off of detach) off();
      clearInterval(tickTimer);
      clearInterval(pollTimer);
      for (const id of oneShots) clearTimeout(id);
      oneShots.clear();
      listeners.clear();
      restoreQueuePrompt?.();
    },
  };
}
