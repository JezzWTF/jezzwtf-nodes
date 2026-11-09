// Floating, non-blocking panels (like Paste Stack): draggable, resizable, they never dim or lock the canvas,
// and their position, size and open state are remembered. A small dock of launcher buttons keeps them one click away.
import { h } from "../utility_core/_shared.js";

const KEY = (id) => `jezzwtf.ws.${id}`;
const DOCK_KEY = "jezzwtf.ws.dock";
let layer = 1480;

const readState = (key) => { try { return JSON.parse(localStorage.getItem(key) ?? "{}") || {}; } catch { return {}; } };
const writeState = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage is optional */ } };
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

/** Keep a rectangle reachable inside the viewport (at least the title bar stays on screen). */
export function clampRect({ x, y, w, h }, vw, vh) {
  const width = clamp(w, 320, Math.max(320, vw - 16));
  const height = clamp(h, 240, Math.max(240, vh - 16));
  return { x: clamp(x, 8 - width + 120, vw - 120), y: clamp(y, 0, vh - 40), w: width, h: height };
}

const sizeClass = (w) => (w < 760 ? "sm" : w < 1040 ? "md" : "lg");

export function createPanel({ id, title, className, size, at, onShow, onHide }) {
  const saved = readState(KEY(id));
  let rect = clampRect({ x: saved.x ?? at.x, y: saved.y ?? at.y, w: saved.w ?? size.w, h: saved.h ?? size.h }, innerWidth, innerHeight);

  const closeBtn = h("button.jwtf-ws-close", { type: "button", textContent: "×", title: "Hide (Esc). It stays one click away in the dock.", "aria-label": `Hide ${title}` });
  const heading = h("div.jwtf-ws-title", {}, h("strong", { textContent: title }));
  const headerExtra = h("div.jwtf-ws-header-extra");
  const header = h("header.jwtf-ws-header", {}, heading, headerExtra, closeBtn);
  const body = h("div.jwtf-ws-body");
  const footer = h("footer.jwtf-ws-footer");
  const dialog = h("section.jwtf-ws-dialog", { role: "dialog", "aria-label": title, tabIndex: -1 }, header, body, footer);
  const root = h(`div.jwtf-ws.${className}`, { hidden: true }, dialog);
  document.body.append(root);

  const apply = () => {
    Object.assign(dialog.style, { left: `${rect.x}px`, top: `${rect.y}px`, width: `${rect.w}px`, height: `${rect.h}px` });
    dialog.dataset.size = sizeClass(rect.w);
  };
  const persist = () => writeState(KEY(id), { ...rect, open: !root.hidden });
  apply();

  const bringToFront = () => { dialog.style.zIndex = String(++layer); };
  dialog.addEventListener("pointerdown", bringToFront);

  // drag by the header (not by its controls)
  let drag = null;
  header.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest("button, input, select, textarea, a")) return;
    drag = { dx: e.clientX - rect.x, dy: e.clientY - rect.y };
    header.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  header.addEventListener("pointermove", (e) => {
    if (!drag) return;
    rect = clampRect({ ...rect, x: e.clientX - drag.dx, y: e.clientY - drag.dy }, innerWidth, innerHeight);
    apply();
  });
  const endDrag = () => { if (drag) { drag = null; persist(); } };
  header.addEventListener("pointerup", endDrag);
  header.addEventListener("lostpointercapture", endDrag);

  // CSS resize handle: follow it so the size is remembered
  const observer = new ResizeObserver(() => {
    if (root.hidden || drag) return;
    const w = Math.round(dialog.offsetWidth), hh = Math.round(dialog.offsetHeight);
    if (Math.abs(w - rect.w) > 1 || Math.abs(hh - rect.h) > 1) { rect = { ...rect, w, h: hh }; dialog.dataset.size = sizeClass(w); persist(); }
  });
  observer.observe(dialog);
  addEventListener("resize", () => { rect = clampRect(rect, innerWidth, innerHeight); apply(); });

  const api = {
    root, body, footer, headerExtra, heading, id, title,
    get visible() { return !root.hidden; },
    show({ focus = true } = {}) {
      if (!root.hidden) { bringToFront(); return; }
      root.hidden = false;
      bringToFront();
      persist();
      onShow?.();
      if (focus) dialog.focus({ preventScroll: true });
    },
    hide() {
      if (root.hidden) return;
      root.hidden = true;
      persist();
      onHide?.();
    },
    toggle() { if (api.visible) api.hide(); else api.show(); },
  };
  closeBtn.addEventListener("click", () => api.hide());
  // Keys typed inside the panel stay inside it (canvas shortcuts must not fire); Escape hides it.
  dialog.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); api.hide(); }
    e.stopPropagation();
  });
  dialog.addEventListener("wheel", (e) => e.stopPropagation(), { passive: true });
  api.wasOpen = !!saved.open;
  return api;
}

/** A draggable dock of launcher buttons; each shows whether its panel is open. */
export function createDock(items) {
  const state = readState(DOCK_KEY);
  const grip = h("span.jwtf-ws-grip", { title: "Drag to move", textContent: "⠿" });
  const buttons = items.map(({ label, toggle, hint }) => h("button.jwtf-ws-dock-btn", { type: "button", title: hint, onclick: () => toggle() }, label));
  const dock = h("div.jwtf-ws-dock", { role: "toolbar", "aria-label": "JezzWTF windows" }, grip, ...buttons);
  document.body.append(dock);
  const place = () => {
    const x = clamp(state.x ?? 16, 0, Math.max(0, innerWidth - dock.offsetWidth));
    const y = clamp(state.y ?? innerHeight - 120, 0, Math.max(0, innerHeight - dock.offsetHeight));
    Object.assign(dock.style, { left: `${x}px`, top: `${y}px` });
    state.x = x; state.y = y;
  };
  requestAnimationFrame(place);
  addEventListener("resize", place);
  let drag = null;
  grip.addEventListener("pointerdown", (e) => {
    drag = { dx: e.clientX - dock.offsetLeft, dy: e.clientY - dock.offsetTop };
    grip.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  grip.addEventListener("pointermove", (e) => {
    if (!drag) return;
    state.x = e.clientX - drag.dx; state.y = e.clientY - drag.dy;
    place();
  });
  const end = () => { if (drag) { drag = null; writeState(DOCK_KEY, state); } };
  grip.addEventListener("pointerup", end);
  grip.addEventListener("lostpointercapture", end);
  return {
    refresh() { items.forEach(({ panel }, i) => buttons[i].setAttribute("aria-pressed", String(panel.visible))); },
    setVisible(v) { dock.hidden = !v; },
  };
}
