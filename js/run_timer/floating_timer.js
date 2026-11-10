// Floating Run Timer: the same clock card as the node, in a free window with no node frame around it. It is opt-in
// (a setting), always on screen while enabled, draggable, resizable at a fixed shape, and remembers its place and look.
// `buildCard` is passed in from run_timer.js; this file gives it a small stand-in for a graph node.

const KEY = "jezzwtf.runTimer.floating";
const HOST_CARD_H = 127; // what a node's computeSize() reports; fixes the digital face at the same 2:1 shape as the node
const MARGIN = 6;

const readState = () => {
  try { return JSON.parse(localStorage.getItem(KEY) ?? "{}") || {}; } catch { return {}; }
};
const writeState = (state) => {
  try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* storage is optional */ }
};
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

export function createFloatingTimer(buildCard) {
  const saved = readState();
  const window_ = document.createElement("div");
  window_.className = "jwtf-rt-float";
  window_.hidden = true;
  const grip = document.createElement("div");
  grip.className = "jwtf-rt-float-grip";
  grip.title = "Drag to resize";
  document.body.append(window_);

  let x = Number.isFinite(saved.x) ? saved.x : 24;
  let y = Number.isFinite(saved.y) ? saved.y : 96;
  let w = Number.isFinite(saved.w) ? saved.w : 270;
  let hgt = Number.isFinite(saved.h) ? saved.h : 133;
  let ready = false;

  const persist = () => writeState({ x, y, w, h: hgt, style: host.properties.jwtf_style });
  const place = () => {
    x = clamp(x, MARGIN - w + 60, innerWidth - 60);
    y = clamp(y, 0, innerHeight - 40);
    Object.assign(window_.style, { left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${hgt}px` });
  };

  // The stand-in node: only what buildCard touches.
  const host = {
    title: "Run Timer",
    widgets: [],
    properties: { jwtf_style: saved.style },
    get size() { return this._size; },
    _size: [w, hgt],
    min_size: [0, 0],
    computeSize: () => [0, HOST_CARD_H],
    addDOMWidget(_name, _type, element) { window_.prepend(element); window_.append(grip); },
    setSize(s) {
      w = Math.round(s[0]);
      hgt = Math.round(s[1]);
      this._size = [w, hgt];
      if (ready) { place(); persist(); }
    },
    setDirtyCanvas() { if (ready) persist(); },
    onResize() {},
  };
  buildCard(host);
  ready = true;
  place();

  // Move by the card itself (not its buttons or the label editor).
  let drag = null;
  window_.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest("button, input, .jwtf-rt-float-grip")) return;
    drag = { dx: e.clientX - x, dy: e.clientY - y };
    window_.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  window_.addEventListener("pointermove", (e) => {
    if (!drag) return;
    x = e.clientX - drag.dx;
    y = e.clientY - drag.dy;
    place();
  });
  const endDrag = () => { if (drag) { drag = null; persist(); } };
  window_.addEventListener("pointerup", endDrag);
  window_.addEventListener("lostpointercapture", endDrag);

  // Resize from the corner: the width leads and buildCard's onResize hook keeps the shape.
  let size = null;
  grip.addEventListener("pointerdown", (e) => {
    size = { sx: e.clientX, w };
    grip.setPointerCapture(e.pointerId);
    e.preventDefault();
    e.stopPropagation();
  });
  grip.addEventListener("pointermove", (e) => {
    if (!size) return;
    const next = [Math.min(size.w + e.clientX - size.sx, innerWidth - x - 8), 0];
    host.onResize(next);
    host.setSize(next);
  });
  const endSize = () => { if (size) { size = null; persist(); } };
  grip.addEventListener("pointerup", endSize);
  grip.addEventListener("lostpointercapture", endSize);
  addEventListener("resize", place);

  return {
    get visible() { return !window_.hidden; },
    show() { window_.hidden = false; place(); },
    hide() { window_.hidden = true; },
    toggle() { window_.hidden = !window_.hidden; if (!window_.hidden) place(); },
  };
}
