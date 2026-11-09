// Run Timer: extension entry. Registers the node card (live stopwatch, last/average/best) and wires the shared
// controller and floating history panel. Logic: run_core.js. Events and history: run_controller.js. Panel: run_panel.js.
import { app } from "../../../scripts/app.js";
import { createController } from "./run_controller.js";
import { createPanel, ensureStylesheet } from "./run_panel.js";
import { formatDuration, nodeSummary } from "./run_core.js";

const EXT_NAME = "JezzWTF.RunTimer";
const NODE_TYPE = "JWTFRunTimer";
const SHARED_KEY = "__jwtfRunTimerShared";
const SET_AUTO_OPEN = "JezzWTF.RunTimer.AutoOpen";
const MIN_W = 220;
const MIN_CARD_H = 110;
const DEFAULT_W = 340;
const DEFAULT_H = 150; // card body; the node adds its title bar and slot row on top

let autoOpen = false;

const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};

function readBool(id, fallback) {
  try {
    const v = app.extensionManager?.setting?.get?.(id) ?? app.ui?.settings?.getSettingValue?.(id);
    return v === null || v === undefined ? fallback : !!v;
  } catch { return fallback; }
}

/** One controller and one panel per page, however many Run Timer nodes exist. */
function shared() {
  let s = window[SHARED_KEY];
  if (s) return s;
  const controller = createController();
  const panel = createPanel(controller);
  controller.hooks.onRunStarted = () => { if (autoOpen && panel.state === "closed") panel.open(); };
  s = { controller, panel };
  window[SHARED_KEY] = s;
  return s;
}

const DEFAULT_TITLE = "Run Timer";

/** The label a run is filed under: the node's title once the user renamed it, else the hidden `label` widget's text. */
function labelOf(node) {
  const title = typeof node.title === "string" ? node.title.trim() : "";
  if (title && title !== DEFAULT_TITLE) return title;
  const v = node.widgets?.find((w) => w.name === "label")?.value;
  return typeof v === "string" ? v.trim() : "";
}

/** The `label` widget stays in the node signature (workflows and the server read it) but is never drawn or laid out. */
function hideLabelWidget(node) {
  const w = node.widgets?.find((x) => x.name === "label");
  if (!w) return;
  w.hidden = true;
  w.computeSize = () => [0, -4];
  w.draw = () => {};
  w.serializeValue = () => labelOf(node);
  // The frontend may add a socket for the widget; a hidden label has no business showing one.
  const idx = node.inputs?.findIndex((i) => i.widget?.name === "label") ?? -1;
  if (idx >= 0) node.inputs[idx].hidden = true;
}

/** Make the pass-through slots visually quiet: no text, the dot alone. */
function quietSlots(node) {
  for (const s of [...(node.inputs ?? []), ...(node.outputs ?? [])]) {
    if (s.name === "value") s.label = " ";
  }
}

function buildCard(node) {
  const { controller, panel } = shared();
  ensureStylesheet();

  const dot = el("span", "jwtf-rt-dot");
  const readout = el("div", "jwtf-rt-readout");
  readout.setAttribute("role", "timer");
  const parts = {};
  const seps = [];
  for (const unit of ["h", "m", "s"]) {
    if (unit !== "h") seps.push(el("span", "jwtf-rt-sep", ":"));
    const num = el("span", "jwtf-rt-num", "00");
    const u = el("span", "jwtf-rt-unit", unit);
    const group = el("span", "jwtf-rt-group");
    group.append(num, u);
    parts[unit] = { num, group };
  }
  // h : m : s, where the hour group and its colon only exist from one hour up.
  const colonH = seps[0];
  const colonS = seps[1];
  colonH.classList.add("jwtf-rt-sep-h");
  readout.append(parts.h.group, colonH, parts.m.group, colonS, parts.s.group);
  const caption = el("div", "jwtf-rt-caption", "last run");
  caption.title = "Double-click to set the label";
  const stats = el("div", "jwtf-rt-stats", "");
  const openBtn = el("button", "jwtf-rt-open", "history");
  openBtn.type = "button";
  const foot = el("div", "jwtf-rt-foot");
  foot.append(stats, openBtn);
  const card = el("div", "jwtf-rt-card");
  card.append(dot, readout, caption, foot);
  const root = el("div", "jwtf-rt-node");
  root.append(card);

  // The colons and the status dot beat once per elapsed second, phase-locked to the clock,
  // instead of running on a free CSS loop that has nothing to do with the seconds.
  const beats = [dot, colonH, colonS];
  const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  let lastSec = -1;
  function beat(ms) {
    if (reduceMotion || !card.isConnected) return;
    for (const target of beats) {
      if (target.hidden) continue;
      target.getAnimations().forEach((a) => a.cancel());
      const a = target.animate(
        [{ opacity: 1 }, { opacity: 0.2, offset: 0.55 }, { opacity: 1 }],
        { duration: 1000, easing: "ease-out" },
      );
      a.currentTime = ms % 1000;
    }
  }
  function stopBeat() {
    lastSec = -1;
    for (const target of beats) target.getAnimations().forEach((a) => a.cancel());
  }

  function setClock(ms, running = false) {
    const safe = Number.isFinite(ms) && ms > 0 ? ms : 0;
    const totalSec = Math.floor(safe / 1000);
    if (running) {
      if (totalSec !== lastSec) {
        lastSec = totalSec;
        beat(safe);
      }
    } else if (lastSec !== -1) {
      stopBeat();
    }
    const h = Math.floor(totalSec / 3600);
    const two = (n) => String(n).padStart(2, "0");
    parts.h.num.textContent = String(h);
    parts.m.num.textContent = two(Math.floor((totalSec % 3600) / 60));
    parts.s.num.textContent = two(totalSec % 60);
    const showH = h > 0;
    parts.h.group.hidden = !showH;
    colonH.hidden = !showH;
    readout.dataset.groups = showH ? "3" : "2";
    readout.setAttribute("aria-label", showH ? `${h} hours` + ` ${parts.m.num.textContent} minutes ${parts.s.num.textContent} seconds` : `${parts.m.num.textContent} minutes ${parts.s.num.textContent} seconds`);
  }
  setClock(0);

  const ac = new AbortController();
  openBtn.addEventListener("click", () => panel.open(), { signal: ac.signal });
  // Keep canvas shortcuts and wheel zoom from firing while the pointer is on the card's controls.
  openBtn.addEventListener("keydown", (e) => e.stopPropagation(), { signal: ac.signal });

  function refresh(kind) {
    const p = controller.primary();
    const history = controller.history;
    if (p) {
      setClock(p.elapsed, true);
      if (kind === "tick" && root.dataset.status === "running") return;
    }
    const sum = nodeSummary(history, labelOf(node));
    const status = p ? "running" : sum.last ? sum.last.status : "idle";
    root.dataset.status = status;
    dot.title = status;
    if (!p) setClock(sum.last && sum.last.ms !== null ? sum.last.ms : 0, false);
    const label = labelOf(node);
    const state = p ? "running" : sum.last ? "last run" : "no runs yet";
    if (!caption.querySelector("input")) caption.textContent = label ? `${label} · ${state}` : state;
    stats.textContent = sum.count ? `avg ${formatDuration(sum.avg)} · best ${formatDuration(sum.best)}` : "";
    stats.hidden = !sum.count;
  }

  const unsubscribe = controller.subscribe(refresh);
  refresh("change");

  node.addDOMWidget("jwtf_run_timer", "jwtf_run_timer", root, { serialize: false, hideOnZoom: false, getMinHeight: () => MIN_CARD_H });
  hideLabelWidget(node);
  quietSlots(node);
  const labelWidget = node.widgets?.find((w) => w.name === "label");
  if (labelWidget) {
    const original = labelWidget.callback;
    labelWidget.callback = function (...args) {
      const r = original?.apply(this, args);
      refresh("change");
      return r;
    };
  }

  // Double-click the caption to edit the label. On a renamed node the title is the label, so edit that instead.
  caption.addEventListener("dblclick", (e) => {
    e.stopPropagation();
    if (caption.querySelector("input")) return;
    const input = el("input", "jwtf-rt-label-input");
    input.type = "text";
    input.maxLength = 120;
    input.placeholder = "label";
    input.value = labelOf(node);
    let done = false;
    const finish = (commit) => {
      if (done) return;
      done = true;
      const text = input.value.trim();
      if (commit) {
        const renamed = typeof node.title === "string" && node.title.trim() !== DEFAULT_TITLE;
        if (renamed) node.title = text || DEFAULT_TITLE;
        else if (labelWidget) labelWidget.value = text;
        node.setDirtyCanvas?.(true, true);
      }
      input.remove();
      refresh("change");
    };
    input.addEventListener("keydown", (ev) => {
      ev.stopPropagation();
      if (ev.key === "Enter") finish(true);
      else if (ev.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
    for (const t of ["pointerdown", "dblclick", "wheel"]) input.addEventListener(t, (ev) => ev.stopPropagation());
    caption.textContent = "";
    caption.append(input);
    input.focus();
    input.select();
  }, { signal: ac.signal });

  // Renaming the node re-files its runs under the new title; notice it without a title-change hook.
  let seenTitle = node.title;
  const drawn = node.onDrawForeground;
  node.onDrawForeground = function (...args) {
    if (this.title !== seenTitle) {
      seenTitle = this.title;
      refresh("change");
    }
    return drawn?.apply(this, args);
  };

  node.setSize([Math.max(node.size[0], DEFAULT_W), Math.max(node.size[1], node.computeSize()[1] + DEFAULT_H - MIN_CARD_H)]);

  node._jwtfRunTimerDispose = () => {
    ac.abort();
    unsubscribe();
    node._jwtfRunTimerDispose = null; // the frontend removes the DOM widget element itself
  };
  node._jwtfRunTimerRefresh = () => refresh("change");
}

app.registerExtension({
  name: EXT_NAME,
  settings: [
    {
      id: SET_AUTO_OPEN,
      name: "Run Timer: open the history panel when a run starts",
      type: "boolean",
      defaultValue: false,
      category: ["JezzWTF", "Run Timer", "Auto open"],
      onChange: (v) => { autoOpen = !!v; },
    },
  ],
  commands: [
    { id: "JezzWTF.RunTimer.TogglePanel", label: "Run Timer: toggle history panel", function: () => shared().panel.toggle() },
  ],

  setup() {
    autoOpen = readBool(SET_AUTO_OPEN, false);
    shared();
  },

  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_TYPE) return;
    const proto = nodeType.prototype;
    const created = proto.onNodeCreated;
    proto.onNodeCreated = function (...args) {
      const r = created?.apply(this, args);
      buildCard(this);
      return r;
    };
    const configured = proto.onConfigure;
    proto.onConfigure = function (...args) {
      const r = configured?.apply(this, args);
      this._jwtfRunTimerRefresh?.();
      return r;
    };
    const removed = proto.onRemoved;
    proto.onRemoved = function (...args) {
      this._jwtfRunTimerDispose?.();
      return removed?.apply(this, args);
    };
  },
});
