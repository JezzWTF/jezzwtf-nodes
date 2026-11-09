// Run Timer: the floating run-history panel (draggable, resizable, minimizes to a chip). Mirrors the Paste Stack
// panel's behaviour with its own code. Pure logic lives in run_core.js; data comes from the controller.
import {
  computeStats, exportName, filterRuns, formatChip, formatClock, formatDuration, runName, timeAgo, toCsv, toJson, uniqueLabels,
} from "./run_core.js";

const UI_KEY = "jezzwtf.runTimer.ui";
const CSS_ID = "jwtf-rt-css";
const CHIP_H = 34;
const CHIP_MIN_W = 56;
const DRAG_THRESHOLD = 4;
const MIN_W = 300;
const MIN_H = 260;

const el = (tag, cls, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "text") n.textContent = v;
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids) if (kid) n.append(kid);
  return n;
};

const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), Math.max(lo, hi));

export function ensureStylesheet() {
  if (document.getElementById(CSS_ID)) return null;
  const link = el("link", "", { id: CSS_ID, rel: "stylesheet", href: new URL("./run_timer.css", import.meta.url).href });
  document.head.append(link);
  return link;
}

function loadUi() {
  try {
    const parsed = JSON.parse(localStorage.getItem(UI_KEY) || "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch { return {}; }
}

function saveUi(ui) {
  try { localStorage.setItem(UI_KEY, JSON.stringify(ui)); } catch { /* storage blocked: position just will not persist */ }
}

const STATUS_TEXT = { ok: "ok", error: "error", interrupted: "interrupted", unknown: "unknown" };

export function createPanel(controller) {
  const ac = new AbortController();
  const sig = { signal: ac.signal };
  const timers = new Set();
  const stored = loadUi();
  const ui = {
    w: 360, h: 460, state: "closed", label: null, status: null,
    ...Object.fromEntries(Object.entries(stored).filter(([k]) => ["w", "h", "x", "y", "cx", "cy", "state", "label", "status"].includes(k))),
  };
  if (!["closed", "open", "chip"].includes(ui.state)) ui.state = "closed";

  let hovering = false;
  let clearArmed = false;
  let clearTimer = 0;
  let toastTimer = 0;
  let resizeTimer = 0;
  let lastCount = controller.history.length;
  let visibleRuns = [];

  const later = (fn, ms) => { const id = setTimeout(() => { timers.delete(id); fn(); }, ms); timers.add(id); return id; };

  // ---- DOM
  const title = el("span", "jwtf-rt-title", { text: "Run history" });
  const count = el("span", "jwtf-rt-count");
  const minBtn = el("button", "jwtf-rt-btn jwtf-rt-x", { type: "button", text: "–", title: "Minimize", "aria-label": "Minimize run history" });
  const closeBtn = el("button", "jwtf-rt-btn jwtf-rt-x", { type: "button", text: "×", title: "Close", "aria-label": "Close run history" });
  const head = el("div", "jwtf-rt-head", {}, title, count, minBtn, closeBtn);

  const liveDot = el("span", "jwtf-rt-dot s-running");
  const liveTime = el("span", "jwtf-rt-live-time", { text: "00:00.0" });
  const liveName = el("span", "jwtf-rt-live-name");
  const live = el("div", "jwtf-rt-live", { hidden: true, role: "status" }, liveDot, el("span", "jwtf-rt-live-tag", { text: "Running" }), liveTime, liveName);

  const labelSel = el("select", "jwtf-rt-sel", { "aria-label": "Filter by label" });
  const statusSel = el("select", "jwtf-rt-sel", { "aria-label": "Filter by status" });
  for (const [v, t] of [["all", "All statuses"], ["ok", "OK"], ["error", "Error"], ["interrupted", "Interrupted"], ["unknown", "Unknown"]]) {
    statusSel.append(el("option", "", { value: v, text: t }));
  }
  const filters = el("div", "jwtf-rt-filters", {}, labelSel, statusSel);

  const statEls = {};
  const stats = el("div", "jwtf-rt-stats");
  for (const [key, name] of [["count", "Runs"], ["avg", "Average"], ["median", "Median"], ["best", "Best"], ["worst", "Worst"]]) {
    const value = el("span", "jwtf-rt-stat-v", { text: "--" });
    statEls[key] = value;
    stats.append(el("div", "jwtf-rt-stat", {}, el("span", "jwtf-rt-stat-k", { text: name }), value));
  }

  const list = el("div", "jwtf-rt-list", { role: "list" });
  const empty = el("div", "jwtf-rt-empty", { text: "No runs recorded yet." });
  const csvBtn = el("button", "jwtf-rt-btn", { type: "button", text: "CSV", title: "Export the runs shown as CSV" });
  const jsonBtn = el("button", "jwtf-rt-btn", { type: "button", text: "JSON", title: "Export the runs shown as JSON" });
  const clearBtn = el("button", "jwtf-rt-btn", { type: "button", text: "Clear all" });
  const foot = el("div", "jwtf-rt-foot", {}, csvBtn, jsonBtn, el("span", "jwtf-rt-grow"), clearBtn);
  const toast = el("div", "jwtf-rt-toast", { role: "status", "aria-live": "polite" });
  const panel = el("section", "jwtf-rt-panel", { role: "region", "aria-label": "Run history", hidden: true }, head, live, filters, stats, list, empty, foot, toast);

  const chipTime = el("span", "jwtf-rt-chip-time", { text: "--" });
  const chip = el("button", "jwtf-rt-chip", { type: "button", "aria-label": "Open run history", hidden: true }, el("span", "jwtf-rt-dot"), chipTime);
  const root = el("div", "jwtf-rt");
  root.append(panel, chip);
  document.body.append(root);
  const link = ensureStylesheet();

  // ---- toast
  function say(msg, ms = 2600) {
    toast.textContent = msg;
    toast.classList.add("on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("on"), ms);
  }

  // ---- placement and state
  function place() {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    if (ui.state === "chip") {
      const w = chip.offsetWidth || CHIP_MIN_W;
      if (typeof ui.cx !== "number") { ui.cx = vw - w - 24; ui.cy = vh - CHIP_H - 24; }
      ui.cx = clamp(ui.cx, 0, vw - w);
      ui.cy = clamp(ui.cy, 0, vh - CHIP_H);
      chip.style.left = `${ui.cx}px`;
      chip.style.top = `${ui.cy}px`;
    } else if (ui.state === "open") {
      if (typeof ui.x !== "number") { ui.x = Math.max(8, vw - ui.w - 24); ui.y = 100; }
      const w = panel.offsetWidth || ui.w;
      const h = panel.offsetHeight || ui.h;
      ui.x = clamp(ui.x, 0, vw - w);
      ui.y = clamp(ui.y, 0, vh - h);
      panel.style.left = `${ui.x}px`;
      panel.style.top = `${ui.y}px`;
    }
  }

  function applyState() {
    panel.hidden = ui.state !== "open";
    chip.hidden = ui.state !== "chip";
    root.dataset.state = ui.state;
    if (ui.state === "open") {
      panel.style.width = `${clamp(ui.w, MIN_W, window.innerWidth)}px`;
      panel.style.height = `${clamp(ui.h, MIN_H, window.innerHeight)}px`;
      render();
    }
    if (ui.state !== "closed") renderLive();
    place();
  }

  function open() {
    if (ui.state === "chip") {
      ui.x = (ui.cx ?? 0) + (chip.offsetWidth || CHIP_MIN_W) - ui.w;
      ui.y = ui.cy ?? 100;
    }
    ui.state = "open";
    applyState();
    saveUi(ui);
    controller.refreshHistory();
    panel.focus?.({ preventScroll: true });
  }

  function minimize() {
    if (ui.state !== "open") return;
    ui.w = panel.offsetWidth || ui.w;
    ui.h = panel.offsetHeight || ui.h;
    ui.cx = (ui.x ?? 0) + ui.w - CHIP_MIN_W;
    ui.cy = ui.y ?? 0;
    ui.state = "chip";
    applyState();
    saveUi(ui);
  }

  function close() {
    if (ui.state === "closed") return;
    if (ui.state === "open") { ui.w = panel.offsetWidth || ui.w; ui.h = panel.offsetHeight || ui.h; }
    ui.state = "closed";
    cancelClear();
    applyState();
    saveUi(ui);
  }

  const toggle = () => (ui.state === "open" ? close() : open());

  // ---- rendering
  function filterNow() {
    return { label: ui.label, status: ui.status };
  }

  function syncFilters(all) {
    const labels = uniqueLabels(all);
    if (ui.label !== null && !labels.includes(ui.label)) ui.label = null;
    labelSel.replaceChildren(el("option", "", { value: "all", text: "All labels" }));
    for (const l of labels) labelSel.append(el("option", "", { value: `l:${l}`, text: l || "(no label)" }));
    labelSel.value = ui.label === null ? "all" : `l:${ui.label}`;
    statusSel.value = ui.status === null ? "all" : ui.status;
  }

  function detailsOf(run) {
    const lines = [`${runName(run)}`, `Started ${new Date(run.started_at).toLocaleString()}`, `Status: ${STATUS_TEXT[run.status] ?? run.status}`];
    if (run.workflow) lines.push(`Workflow: ${run.workflow}`);
    if (run.node_count) lines.push(`${run.node_count} nodes`);
    if (run.slowest?.length) lines.push("Slowest nodes:", ...run.slowest.map((n) => `  ${n.title}: ${formatDuration(n.ms)}`));
    if (run.approx) lines.push("Start time was recovered after a page reload and may be late.");
    if (run.local) lines.push("Not saved to the history file yet.");
    return lines.join("\n");
  }

  function rowFor(run, now) {
    const status = STATUS_TEXT[run.status] ? run.status : "unknown";
    const name = el("div", "jwtf-rt-name", { text: runName(run) });
    const bits = [timeAgo(run.started_at, now), status];
    if (run.label && run.workflow) bits.push(run.workflow);
    const sub = el("div", "jwtf-rt-sub", { text: bits.join(" · ") });
    sub.dataset.ts = String(run.started_at);
    sub.dataset.tail = bits.slice(1).join(" · ");
    const dur = el("div", "jwtf-rt-dur", { text: run.duration_ms === null ? "--" : formatDuration(run.duration_ms) });
    if (run.approx) dur.textContent += " ~";
    const del = el("button", "jwtf-rt-btn jwtf-rt-del", { type: "button", text: "×", title: "Delete this run", "aria-label": `Delete run ${runName(run)}` });
    const row = el("div", `jwtf-rt-row s-${status}`, { role: "listitem", title: detailsOf(run) }, el("span", `jwtf-rt-dot s-${status}`), el("div", "jwtf-rt-main", {}, name, sub), dur, del);
    row.dataset.id = run.id;
    return row;
  }

  function render() {
    if (ui.state !== "open") return;
    const all = controller.history;
    syncFilters(all);
    visibleRuns = filterRuns(all, filterNow());
    const now = Date.now();
    list.replaceChildren(...visibleRuns.map((r) => rowFor(r, now)));
    empty.hidden = visibleRuns.length > 0;
    empty.textContent = all.length ? "No runs match the filters." : controller.lastError || "No runs recorded yet.";
    list.hidden = visibleRuns.length === 0;
    const s = computeStats(visibleRuns);
    statEls.count.textContent = String(s.count);
    for (const key of ["avg", "median", "best", "worst"]) statEls[key].textContent = formatDuration(s[key]);
    count.textContent = all.length === visibleRuns.length ? String(all.length) : `${visibleRuns.length} of ${all.length}`;
    csvBtn.disabled = jsonBtn.disabled = visibleRuns.length === 0;
    clearBtn.disabled = all.length === 0;
  }

  function renderLive() {
    const p = controller.primary();
    live.hidden = !p;
    root.classList.toggle("running", !!p);
    if (p) {
      liveTime.textContent = formatClock(p.elapsed);
      liveName.textContent = p.run.label || p.run.workflow || "";
      chipTime.textContent = formatChip(p.elapsed);
      chip.dataset.status = "running";
      return;
    }
    const newest = controller.history[0];
    chipTime.textContent = newest && newest.duration_ms !== null ? formatChip(newest.duration_ms) : "--";
    chip.dataset.status = newest ? newest.status : "idle";
  }

  function refreshAges() {
    const now = Date.now();
    for (const sub of list.querySelectorAll(".jwtf-rt-sub")) {
      sub.textContent = `${timeAgo(Number(sub.dataset.ts), now)} · ${sub.dataset.tail}`;
    }
  }

  const unsubscribe = controller.subscribe((kind) => {
    if (ui.state === "closed") return;
    renderLive();
    if (kind === "tick") return;
    if (ui.state === "open") render();
    if (ui.state === "chip" && controller.history.length !== lastCount) {
      chip.classList.remove("pulse");
      void chip.offsetWidth;
      chip.classList.add("pulse");
    }
    lastCount = controller.history.length;
  });
  const ageTimer = setInterval(() => { if (ui.state === "open") refreshAges(); }, 30000);

  // ---- actions
  labelSel.addEventListener("change", () => {
    ui.label = labelSel.value === "all" ? null : labelSel.value.slice(2);
    saveUi(ui);
    render();
  }, sig);
  statusSel.addEventListener("change", () => {
    ui.status = statusSel.value === "all" ? null : statusSel.value;
    saveUi(ui);
    render();
  }, sig);

  list.addEventListener("click", async (e) => {
    const btn = e.target.closest(".jwtf-rt-del");
    const row = btn?.closest(".jwtf-rt-row");
    if (!row) return;
    try { await controller.deleteRun(row.dataset.id); } catch { say("Could not delete that run."); }
  }, sig);

  function download(name, text, mime) {
    const url = URL.createObjectURL(new Blob([text], { type: mime }));
    const a = el("a", "", { href: url, download: name });
    root.append(a);
    a.click();
    a.remove();
    later(() => URL.revokeObjectURL(url), 10000);
  }

  csvBtn.addEventListener("click", () => {
    if (!visibleRuns.length) { say("Nothing to export."); return; }
    download(exportName("csv", new Date()), toCsv(visibleRuns), "text/csv;charset=utf-8");
  }, sig);
  jsonBtn.addEventListener("click", () => {
    if (!visibleRuns.length) { say("Nothing to export."); return; }
    download(exportName("json", new Date()), toJson(visibleRuns), "application/json");
  }, sig);

  function cancelClear() {
    clearTimeout(clearTimer);
    clearArmed = false;
    clearBtn.textContent = "Clear all";
    clearBtn.classList.remove("warn");
  }

  clearBtn.addEventListener("click", async () => {
    if (!clearArmed) {
      clearArmed = true;
      clearBtn.textContent = "Click again to confirm";
      clearBtn.classList.add("warn");
      clearTimer = later(cancelClear, 3500);
      return;
    }
    cancelClear();
    try { await controller.clearAll(); say("History cleared."); } catch { say("Could not clear the history."); }
  }, sig);

  minBtn.addEventListener("click", minimize, sig);
  closeBtn.addEventListener("click", close, sig);

  for (const n of [panel, chip]) {
    n.addEventListener("pointerenter", () => { hovering = true; }, sig);
    n.addEventListener("pointerleave", () => { hovering = false; }, sig);
  }

  // Esc minimizes while a run is going (keeping the stopwatch visible), otherwise closes.
  window.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || ui.state !== "open" || e.defaultPrevented) return;
    if (!(hovering || panel.contains(document.activeElement))) return;
    e.preventDefault();
    e.stopPropagation();
    if (controller.activeCount) minimize(); else close();
  }, { signal: ac.signal, capture: true });

  // ---- drag (header moves the panel, the chip moves itself; a tap on the chip expands it)
  function movable(handle, origin, apply, onTap) {
    let s = null;
    handle.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || (handle !== chip && e.target.closest("button, select, input"))) return;
      s = { id: e.pointerId, x: e.clientX, y: e.clientY, o: origin(), moved: false };
      handle.setPointerCapture(e.pointerId);
    }, sig);
    handle.addEventListener("pointermove", (e) => {
      if (!s || e.pointerId !== s.id) return;
      const dx = e.clientX - s.x;
      const dy = e.clientY - s.y;
      if (!s.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
      s.moved = true;
      apply(s.o, dx, dy);
    }, sig);
    const end = (e) => {
      if (!s || e.pointerId !== s.id) return;
      const moved = s.moved;
      s = null;
      try { handle.releasePointerCapture(e.pointerId); } catch { /* already released */ }
      if (moved) saveUi(ui); else if (onTap && e.type === "pointerup") onTap();
    };
    handle.addEventListener("pointerup", end, sig);
    handle.addEventListener("pointercancel", end, sig);
  }

  movable(head, () => [ui.x, ui.y], ([x, y], dx, dy) => { ui.x = x + dx; ui.y = y + dy; place(); });
  movable(chip, () => [ui.cx, ui.cy], ([x, y], dx, dy) => { ui.cx = x + dx; ui.cy = y + dy; place(); }, open);
  chip.addEventListener("click", (e) => { if (e.detail === 0) open(); }, sig); // keyboard activation

  // ---- resize persistence
  if (typeof ResizeObserver !== "undefined") {
    const ro = new ResizeObserver(() => {
      if (ui.state !== "open") return;
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        const w = panel.offsetWidth;
        const h = panel.offsetHeight;
        if (!w || !h) return;
        ui.w = w;
        ui.h = h;
        place();
        saveUi(ui);
      }, 150);
    });
    ro.observe(panel);
    sig.signal.addEventListener("abort", () => ro.disconnect());
  }
  window.addEventListener("resize", place, sig);

  applyState();

  function destroy() {
    ac.abort();
    unsubscribe();
    clearInterval(ageTimer);
    for (const id of timers) clearTimeout(id);
    timers.clear();
    clearTimeout(toastTimer);
    clearTimeout(resizeTimer);
    root.remove();
    link?.remove();
  }

  return { open, close, minimize, toggle, destroy, get state() { return ui.state; } };
}
