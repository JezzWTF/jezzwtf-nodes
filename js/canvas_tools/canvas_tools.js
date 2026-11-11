// Canvas Tools: tidy by dependency, align and distribute, group the selection, and a "bypass slash" gesture.
// The maths lives in geometry.js (tested under node); this file only reads and writes the live graph.
import { app } from "../../../scripts/app.js";
import { getLink, h } from "../utility_core/_shared.js";
import { align, boxesOnSlash, distribute, groupRect, tidyByDependency } from "./geometry.js";

const SET_SLASH = "JezzWTF.CanvasTools.BypassSlash";
const BYPASS = 4;
const ALWAYS = 0;

const lg = () => globalThis.LiteGraph;
const titleHeight = () => lg()?.NODE_TITLE_HEIGHT ?? 30;

const selected = () => Object.values(app.canvas?.selected_nodes ?? {});
const boxOf = (node) => {
  const t = node.flags?.collapsed ? 0 : titleHeight();
  const size = node.flags?.collapsed ? [node._collapsed_width ?? 140, 0] : node.size;
  return { id: node.id, x: node.pos[0], y: node.pos[1] - t, w: size[0], h: size[1] + t };
};
const place = (node, p) => {
  const t = node.flags?.collapsed ? 0 : titleHeight();
  if (p.x != null) node.pos[0] = Math.round(p.x);
  if (p.y != null) node.pos[1] = Math.round(p.y + t);
};
const finish = () => {
  app.graph?.setDirtyCanvas?.(true, true);
  app.graph?.change?.();
};

/** Selected nodes (or all, when fewer than `min` are selected) as boxes. */
const targets = (min = 2) => {
  const sel = selected();
  return (sel.length >= min ? sel : app.graph?._nodes ?? []).filter((n) => n.pos && n.size);
};

function tidy() {
  // Resolve the selection first so excluding pins cannot fall back to the whole graph.
  const nodes = targets(2).filter((n) => !n.pinned && !n.flags?.pinned);
  if (nodes.length < 2) return;
  const ids = new Set(nodes.map((n) => n.id));
  const links = [];
  for (const node of nodes) {
    for (const input of node.inputs ?? []) {
      const link = input.link != null ? getLink(app.graph, input.link) : null;
      if (link && ids.has(link.origin_id)) links.push({ from: link.origin_id, to: node.id });
    }
  }
  const positions = tidyByDependency(nodes.map(boxOf), links);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  for (const [id, p] of Object.entries(positions)) place(byId.get(Number.isNaN(+id) ? id : +id) ?? byId.get(id), p);
  finish();
}

function alignSelection(mode) {
  const nodes = selected().filter((n) => n.pos && n.size);
  const moves = align(nodes.map(boxOf), mode);
  const byId = new Map(nodes.map((n) => [String(n.id), n]));
  for (const [id, p] of Object.entries(moves)) place(byId.get(id), p);
  finish();
}

function distributeSelection(axis) {
  const nodes = selected().filter((n) => n.pos && n.size);
  const moves = distribute(nodes.map(boxOf), axis);
  const byId = new Map(nodes.map((n) => [String(n.id), n]));
  for (const [id, p] of Object.entries(moves)) place(byId.get(id), p);
  finish();
}

function groupSelection() {
  const nodes = selected().filter((n) => n.pos && n.size);
  const LGraphGroup = lg()?.LGraphGroup ?? globalThis.LGraphGroup;
  if (!nodes.length || !LGraphGroup) return;
  const rect = groupRect(nodes.map(boxOf));
  const group = new LGraphGroup("Group");
  group.pos = [rect.x, rect.y];
  group.size = [rect.w, rect.h];
  app.graph.add(group);
  finish();
}

function toggleBypass(nodes) {
  if (!nodes.length) return;
  const mode = nodes.every((n) => n.mode === BYPASS) ? ALWAYS : BYPASS;
  for (const n of nodes) n.mode = mode;
  finish();
}

const tools = [
  { id: "JezzWTF.Canvas.Tidy", label: "Tidy by dependency", run: tidy, key: "t" },
  { id: "JezzWTF.Canvas.Group", label: "Group selected nodes", run: groupSelection, key: "g" },
  { id: "JezzWTF.Canvas.AlignLeft", label: "Align left", run: () => alignSelection("left") },
  { id: "JezzWTF.Canvas.AlignRight", label: "Align right", run: () => alignSelection("right") },
  { id: "JezzWTF.Canvas.AlignTop", label: "Align top", run: () => alignSelection("top") },
  { id: "JezzWTF.Canvas.AlignBottom", label: "Align bottom", run: () => alignSelection("bottom") },
  { id: "JezzWTF.Canvas.AlignCenterX", label: "Align centres (vertical line)", run: () => alignSelection("center-x") },
  { id: "JezzWTF.Canvas.AlignCenterY", label: "Align centres (horizontal line)", run: () => alignSelection("center-y") },
  { id: "JezzWTF.Canvas.DistributeX", label: "Distribute horizontally", run: () => distributeSelection("x") },
  { id: "JezzWTF.Canvas.DistributeY", label: "Distribute vertically", run: () => distributeSelection("y") },
];

// ---------------------------------------------------------------- bypass slash
// Hold Ctrl+Alt and drag across nodes: every node the line crosses toggles bypass (all bypassed -> back on).

function installSlash() {
  const canvasEl = app.canvas?.canvas;
  if (!canvasEl || canvasEl._jwtfSlash) return;
  canvasEl._jwtfSlash = true;
  let line = null;
  let overlay = null;

  const enabled = () => {
    try { return !!app.ui.settings.getSettingValue(SET_SLASH, true); } catch { return true; }
  };
  const armed = (e) => e.button === 0 && e.ctrlKey && e.altKey && !e.shiftKey && enabled();
  const toGraph = (e) => app.canvas.convertEventToCanvasOffset(e);

  const stop = () => { overlay?.remove(); overlay = null; line = null; };
  const draw = (e) => {
    if (!overlay) {
      overlay = h("div.jwtf-slash", { style: { position: "fixed", height: "3px", borderRadius: "2px", background: "#f43f5e", boxShadow: "0 0 8px #f43f5e", transformOrigin: "0 50%", pointerEvents: "none", zIndex: 99999 } });
      document.body.append(overlay);
    }
    const dx = e.clientX - line.cx, dy = e.clientY - line.cy;
    Object.assign(overlay.style, { left: `${line.cx}px`, top: `${line.cy}px`, width: `${Math.hypot(dx, dy)}px`, transform: `rotate(${Math.atan2(dy, dx)}rad)` });
  };

  canvasEl.addEventListener("pointerdown", (e) => {
    if (!armed(e)) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const [gx, gy] = toGraph(e);
    line = { gx, gy, cx: e.clientX, cy: e.clientY };
    canvasEl.setPointerCapture(e.pointerId);
  }, true);
  canvasEl.addEventListener("pointermove", (e) => {
    if (!line) return;
    e.stopImmediatePropagation();
    draw(e);
  }, true);
  const release = (e) => {
    if (!line) return;
    e.stopImmediatePropagation();
    const [gx, gy] = toGraph(e);
    const nodes = (app.graph?._nodes ?? []).filter((n) => n.pos && n.size);
    const hit = new Set(boxesOnSlash(nodes.map(boxOf), line.gx, line.gy, gx, gy).map(String));
    stop();
    toggleBypass(nodes.filter((n) => hit.has(String(n.id))));
  };
  canvasEl.addEventListener("pointerup", release, true);
  canvasEl.addEventListener("pointercancel", () => stop(), true);
}

app.registerExtension({
  name: "JezzWTF.CanvasTools",
  settings: [{
    id: SET_SLASH,
    name: "Bypass slash: hold Ctrl+Alt and drag across nodes to toggle bypass on them",
    type: "boolean",
    defaultValue: true,
    category: ["JezzWTF", "Canvas", "Bypass slash"],
  }],
  setup() { installSlash(); },
  commands: tools.map(({ id, label, run }) => ({ id, label, function: run })),
  keybindings: tools.filter((t) => t.key).map(({ id, key }) => ({ combo: { key, alt: true, shift: true }, commandId: id })),
  getCanvasMenuItems: () => tools.filter((t) => t.key).map(({ label, run }) => ({ content: label, callback: () => run() })),
});
