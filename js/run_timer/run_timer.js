// Run Timer: extension entry. Registers the node card (live stopwatch, last/average/best) and wires the shared
// controller and floating history panel. Logic: run_core.js. Events and history: run_controller.js. Panel: run_panel.js.
import { app } from "../../../scripts/app.js";
import { createController } from "./run_controller.js";
import { createPanel, ensureStylesheet } from "./run_panel.js";
import { formatDuration, nodeSummary } from "./run_core.js";
import { createFloatingTimer } from "./floating_timer.js";
import { BACKGROUNDS, FONTS, THEMES, accent, aspectOf, cssVars, lapMsFor, ringState, ANIMS, LAPS, FACES, SKINS, handAngles, sanitize } from "./timer_style.js";

const EXT_NAME = "JezzWTF.RunTimer";
const NODE_TYPE = "JWTFRunTimer";
const SHARED_KEY = "__jwtfRunTimerShared";
const SET_AUTO_OPEN = "JezzWTF.RunTimer.AutoOpen";
const SET_FLOATING = "JezzWTF.RunTimer.Floating";
const MIN_W = 220;
const MIN_CARD_H = 64;
const DEFAULT_W = 220;
const DEFAULT_H = 70; // card body; the node adds its title bar and slot row on top

let autoOpen = false;
let floating = null;

/** Show or hide the floating timer, creating it on first use. */
function setFloating(on) {
  if (on) { floating ??= createFloatingTimer(buildCard); floating.show(); } else floating?.hide();
}

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

/** A small floating editor for the node's look. Closes on an outside click or Escape. */
function openStylePopover(anchor, getStyle, save) {
  document.querySelector(".jwtf-rt-pop")?.remove();
  const pop = el("div", "jwtf-rt-pop");
  const row = (label, ...kids) => { const r = el("div", "jwtf-rt-pop-row"); r.append(el("span", "jwtf-rt-pop-k", label), ...kids); return r; };
  const seg = (options, current, onPick) => {
    const box = el("div", "jwtf-rt-pop-seg");
    for (const [value, label] of options) {
      const b = el("button", "", label);
      b.type = "button";
      b.setAttribute("aria-pressed", String(value === current));
      b.addEventListener("click", () => { onPick(value); render(); });
      box.append(b);
    }
    return box;
  };
  function swatches(s) {
    const sw = el("div", "jwtf-rt-pop-swatches");
    for (const [key, t] of Object.entries(THEMES)) {
      const b = el("button", "jwtf-rt-swatch");
      b.type = "button"; b.title = t.label; b.style.background = t.color;
      b.setAttribute("aria-pressed", String(!s.color && s.theme === key));
      b.addEventListener("click", () => { save({ theme: key, color: "" }); render(); });
      sw.append(b);
    }
    const custom = el("input", "jwtf-rt-color");
    custom.type = "color"; custom.value = accent(s); custom.title = "Custom colour";
    custom.addEventListener("input", () => save({ color: custom.value }));
    sw.append(custom);
    return sw;
  }
  function render() {
    const s = getStyle();
    pop.replaceChildren(
      row("Skin", seg(Object.entries(SKINS), s.skin, (skin) => save({ skin }))),
      row("Face", seg(Object.entries(FACES), s.face, (face) => save({ face }))),
      row("Colour", swatches(s)),
      ...(s.face === "ring" ? [
        row("Motion", seg(Object.entries(ANIMS), s.anim, (anim) => save({ anim }))),
        row("Lap", seg(Object.entries(LAPS), s.lap, (lap) => save({ lap }))),
      ] : []),
      row("Font", seg(Object.entries(FONTS).map(([k, f]) => [k, f.label]), s.font, (font) => save({ font }))),
      row("Back", seg(Object.entries(BACKGROUNDS).map(([k, b]) => [k, b.label]), s.background, (background) => save({ background }))),
      row("Result", seg([[true, "Tint by result"], [false, "Always accent"]], s.statusTint, (statusTint) => save({ statusTint }))),
    );
  }
  render();
  document.body.append(pop);
  // Place it beside the timer (right, then left, below, above) so the change stays visible while you edit.
  const target = (anchor.closest(".jwtf-rt-float, .jwtf-rt-node") ?? anchor).getBoundingClientRect();
  const w = pop.offsetWidth, h = pop.offsetHeight, gap = 10;
  const fits = {
    right: target.right + gap + w <= innerWidth - 8,
    left: target.left - gap - w >= 8,
    below: target.bottom + gap + h <= innerHeight - 8,
    above: target.top - gap - h >= 8,
  };
  const side = ["right", "left", "below", "above"].find((s) => fits[s]) ?? "right";
  const at = {
    right: [target.right + gap, target.top],
    left: [target.left - gap - w, target.top],
    below: [target.left, target.bottom + gap],
    above: [target.left, target.top - gap - h],
  }[side];
  pop.style.left = `${Math.max(8, Math.min(innerWidth - w - 8, at[0]))}px`;
  pop.style.top = `${Math.max(8, Math.min(innerHeight - h - 8, at[1]))}px`;
  const close = () => { pop.remove(); document.removeEventListener("pointerdown", away, true); document.removeEventListener("keydown", esc, true); };
  const away = (e) => { if (!pop.contains(e.target) && e.target !== anchor) close(); };
  const esc = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("pointerdown", away, true);
  document.addEventListener("keydown", esc, true);
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
  openBtn.title = "Run history";
  const foot = el("div", "jwtf-rt-foot");
  foot.append(stats, openBtn);
  const SVG = "http://www.w3.org/2000/svg";
  const svgEl = (tag, attrs = {}, cls = "") => {
    const n = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
    if (cls) n.setAttribute("class", cls);
    return n;
  };
  const R = 41; // radius of the ring's centre line; the glow needs the margin up to the card edge
  const W = 4.2; // stroke width
  const CIRC = 2 * Math.PI * R;
  const ringSvg = svgEl("svg", { viewBox: "0 0 100 100" }, "jwtf-rt-ring");
  const ringTrack = svgEl("circle", { cx: 50, cy: 50, r: R, fill: "none", "stroke-width": W }, "jwtf-rt-ring-track");
  const ringPrev = svgEl("circle", { cx: 50, cy: 50, r: R, fill: "none", "stroke-width": W }, "jwtf-rt-ring-prev");
  const ringArc = svgEl("circle", { cx: 50, cy: 50, r: R, fill: "none", "stroke-width": W, "stroke-linecap": "round", transform: "rotate(-90 50 50)", "stroke-dasharray": CIRC }, "jwtf-rt-ring-arc");
  const tickGroup = svgEl("g", {}, "jwtf-rt-ticks");
  const ticks = Array.from({ length: 60 }, (_, i) => {
    const line = svgEl("line", { x1: 50, y1: 4, x2: 50, y2: i % 5 === 0 ? 14 : 11, "stroke-width": i % 5 === 0 ? 2.4 : 1.6, "stroke-linecap": "round", transform: `rotate(${i * 6} 50 50)` });
    tickGroup.append(line);
    return line;
  });
  // Comet: a conic-gradient tail (masked to the ring) and a head dot, rotated as one piece.
  const cometTail = el("div", "jwtf-rt-comet-tail");
  const cometHead = el("span", "jwtf-rt-comet-head");
  const cometEl = el("div", "jwtf-rt-comet");
  cometEl.append(cometTail, cometHead);
  // Glass skin: the ring strokes fade from the lap colour to a lighter shade of it.
  const gid = `jwtf-rt-g${Math.random().toString(36).slice(2, 8)}`;
  const defs = svgEl("defs");
  for (const key of ["a", "b"]) {
    const g = svgEl("linearGradient", { id: `${gid}-${key}`, gradientUnits: "userSpaceOnUse", x1: 18, y1: 12, x2: 82, y2: 88 }, `jwtf-rt-grad-${key}`);
    g.append(svgEl("stop", { offset: "0%" }), svgEl("stop", { offset: "100%" }));
    defs.append(g);
  }
  // Analog stopwatch dial: 60 ticks, a sweeping hand and a small 30-minute sub-dial.
  const dial = svgEl("g", {}, "jwtf-rt-dial");
  for (let i = 0; i < 60; i++) {
    const major = i % 5 === 0;
    dial.append(svgEl("line", { x1: 50, y1: 4, x2: 50, y2: major ? 12 : 8, "stroke-width": major ? 2.2 : 1, "stroke-linecap": "round", transform: `rotate(${i * 6} 50 50)` }, major ? "jwtf-rt-tick-major" : "jwtf-rt-tick-minor"));
  }
  const subDial = svgEl("circle", { cx: 50, cy: 31, r: 10, fill: "none", "stroke-width": 1 }, "jwtf-rt-subdial");
  const minuteHand = svgEl("line", { x1: 50, y1: 31, x2: 50, y2: 23, "stroke-width": 1.4, "stroke-linecap": "round" }, "jwtf-rt-hand-small");
  const secondHand = svgEl("line", { x1: 50, y1: 56, x2: 50, y2: 11, "stroke-width": 1.8, "stroke-linecap": "round" }, "jwtf-rt-hand");
  const hub = svgEl("circle", { cx: 50, cy: 50, r: 2.6 }, "jwtf-rt-hub");
  dial.append(subDial, minuteHand, secondHand, hub);
  ringSvg.append(defs, ringTrack, ringPrev, ringArc, tickGroup, dial);
  const styleBtn = el("button", "jwtf-rt-open jwtf-rt-style-btn", "style");
  styleBtn.type = "button";
  styleBtn.title = "Colours, font and face";
  foot.insertBefore(styleBtn, openBtn);
  const card = el("div", "jwtf-rt-card");
  card.append(ringSvg, cometEl, dot, readout, caption, foot);
  const root = el("div", "jwtf-rt-node");
  root.append(card);

  function setClock(ms, running = false) {
    const safe = Number.isFinite(ms) && ms > 0 ? ms : 0;
    const totalSec = Math.floor(safe / 1000);
    // Keep the blink aligned with the displayed seconds, even when a tick arrives late.
    root.classList.toggle("jwtf-rt-indicators-off", running && totalSec % 2 === 1);
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

  let style = sanitize(node.properties?.jwtf_style);
  let lastSum = null;
  const lapClass = (n) => (n % 2 === 0 ? "jwtf-rt-lap-a" : "jwtf-rt-lap-b");
  function updateRing(p, sum) {
    if (style.face === "analog") {
      const a = handAngles(p ? p.elapsed : sum?.last?.ms ?? 0);
      secondHand.setAttribute("transform", `rotate(${a.second} 50 50)`);
      minuteHand.setAttribute("transform", `rotate(${a.minute} 50 31)`);
      return;
    }
    if (style.face !== "ring") return;
    const lapMs = lapMsFor(style.lap, sum?.avg ?? 0);
    const st = ringState({ running: !!p, elapsedMs: p ? p.elapsed : 0, lapMs });
    root.dataset.rest = st.rest ? "1" : "0";
    const cur = lapClass(st.lap), prev = lapClass(st.lap + 1);
    if (style.anim === "ticks") {
      const lit = Math.round(st.frac * 60) % 61;
      ticks.forEach((line, i) => {
        const on = st.rest || i < lit;
        line.setAttribute("class", on ? cur : st.lap > 0 ? prev : "jwtf-rt-tick-off");
      });
      return;
    }
    if (style.anim === "comet") {
      cometEl.style.transform = `rotate(${st.rest ? 0 : st.frac * 360}deg)`;
      cometEl.dataset.lap = st.lap % 2 === 0 ? "a" : "b";
      if (!st.rest) return;
    }
    // laps: the finished lap stays drawn in the other colour, the current one grows over it
    ringArc.setAttribute("stroke-dashoffset", String(CIRC * (1 - st.frac)));
    ringArc.setAttribute("class", `jwtf-rt-ring-arc ${cur}`);
    const glass = style.skin === "glass";
    ringArc.style.stroke = glass ? `url(#${gid}-${st.lap % 2 === 0 ? "a" : "b"})` : "";
    ringPrev.style.stroke = glass ? `url(#${gid}-${st.lap % 2 === 0 ? "b" : "a"})` : "";
    ringPrev.setAttribute("class", `jwtf-rt-ring-prev ${prev}${st.lap > 0 && !st.rest ? " on" : ""}`);
  }

  // The ring, comet and hands move every frame while a run is going, so they sweep instead of stepping at 10 Hz.
  let raf = 0;
  function frame() {
    raf = 0;
    const p = controller.primary();
    if (!p || (style.face !== "ring" && style.face !== "analog")) return;
    updateRing(p, lastSum);
    raf = requestAnimationFrame(frame);
  }
  const ensureMotion = () => { if (!raf && typeof requestAnimationFrame === "function") raf = requestAnimationFrame(frame); };

  function refresh(kind) {
    const p = controller.primary();
    const history = controller.history;
    if (p) {
      setClock(p.elapsed, true);
      updateRing(p, lastSum);
      ensureMotion();
      if (kind === "tick" && root.dataset.status === "running") return;
    }
    const sum = nodeSummary(history, labelOf(node));
    lastSum = sum;
    updateRing(p, sum);
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

  function applyStyle() {
    root.dataset.face = style.face;
    root.dataset.skin = style.skin;
    root.dataset.tint = style.statusTint ? "status" : "fixed";
    root.dataset.anim = style.anim;
    for (const [k, v] of Object.entries(cssVars(style))) root.style.setProperty(k, v);
    node._jwtfRunTimerFit?.();
    refresh("change");
  }
  function saveStyle(next) {
    style = sanitize({ ...style, ...next });
    node.properties = node.properties ?? {};
    node.properties.jwtf_style = style;
    applyStyle();
    node.setDirtyCanvas?.(true, true);
  }
  node._jwtfRunTimerApplyStyle = () => { style = sanitize(node.properties?.jwtf_style); applyStyle(); };
  styleBtn.addEventListener("click", (e) => { e.stopPropagation(); openStylePopover(styleBtn, () => style, saveStyle); }, { signal: ac.signal });

  const unsubscribe = controller.subscribe(refresh);
  refresh("change");

  node.addDOMWidget("jwtf_run_timer", "jwtf_run_timer", root, { serialize: false, hideOnZoom: false, getMinHeight: () => MIN_CARD_H });
  hideLabelWidget(node);
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

  // Fixed shape: the height always follows the width (2:1 for the digital face, square for the ring), so the node
  // cannot be stretched or squashed into something unreadable. The readout scales with the card (container units).
  const digitalRatio = DEFAULT_W / (node.computeSize()[1] + DEFAULT_H - MIN_CARD_H);
  const ratioNow = () => aspectOf(style.face, digitalRatio);
  const minWidth = node.minWidth ?? MIN_W; // a floating timer may be far smaller than a node
  const minOf = () => [minWidth, Math.round(minWidth / ratioNow())];
  node.min_size = minOf();
  const resized = node.onResize;
  node.onResize = function (size) {
    size[0] = Math.max(size[0], minWidth);
    size[1] = Math.round(size[0] / ratioNow());
    return resized?.call(this, size);
  };
  const fit = () => { const s = [Math.max(node.size[0], minWidth), 0]; s[1] = Math.round(s[0] / ratioNow()); node.min_size = minOf(); node.setSize(s); };
  node._jwtfRunTimerFit = fit;
  node.size[0] = Math.max(node.size[0], node.minWidth ?? DEFAULT_W); // a saved floating size is kept down to its minimum
  applyStyle();

  node._jwtfRunTimerDispose = () => {
    ac.abort();
    if (raf) cancelAnimationFrame(raf);
    unsubscribe();
    node._jwtfRunTimerDispose = null; // the frontend removes the DOM widget element itself
  };
  node._jwtfRunTimerRefresh = () => { node._jwtfRunTimerApplyStyle(); };
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
    {
      id: SET_FLOATING,
      name: "Run Timer: show a floating timer (always on screen, drag and resize it, click its style button to restyle)",
      type: "boolean",
      defaultValue: true,
      category: ["JezzWTF", "Run Timer", "Floating timer"],
      onChange: (v) => setFloating(!!v),
    },
  ],
  commands: [
    { id: "JezzWTF.RunTimer.TogglePanel", label: "Run Timer: toggle history panel", function: () => shared().panel.toggle() },
    {
      id: "JezzWTF.RunTimer.ToggleFloating",
      label: "Run Timer: toggle floating timer",
      function: () => {
        const next = !(floating?.visible ?? false);
        // the setting is the source of truth, so it is changed first and its handler shows or hides the window
        const store = app.extensionManager?.setting;
        if (store?.set) store.set(SET_FLOATING, next); else setFloating(next);
      },
    },
  ],

  setup() {
    autoOpen = readBool(SET_AUTO_OPEN, false);
    shared();
    if (readBool(SET_FLOATING, true)) setFloating(true);
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
