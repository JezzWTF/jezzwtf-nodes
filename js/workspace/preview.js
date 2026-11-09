// Draws a small schematic thumbnail of a saved workflow: groups, links and nodes.

const finite = (...v) => v.every(Number.isFinite);
const vec = (v) => (Array.isArray(v) ? v : v && typeof v === "object" ? [v[0], v[1]] : []);

/** Bounds of everything drawable, or null when the workflow has no usable geometry. */
export function workflowBounds(workflow) {
  const boxes = [];
  for (const n of Array.isArray(workflow?.nodes) ? workflow.nodes : []) {
    const [x, y] = vec(n?.pos), [w, h] = vec(n?.size);
    if (finite(x, y, w, h)) boxes.push([x, y, x + w, y + h]);
  }
  for (const g of Array.isArray(workflow?.groups) ? workflow.groups : []) {
    const [x, y, w, h] = Array.isArray(g?.bounding) ? g.bounding : [];
    if (finite(x, y, w, h)) boxes.push([x, y, x + w, y + h]);
  }
  if (!boxes.length) return null;
  return {
    x: Math.min(...boxes.map((b) => b[0])), y: Math.min(...boxes.map((b) => b[1])),
    right: Math.max(...boxes.map((b) => b[2])), bottom: Math.max(...boxes.map((b) => b[3])),
  };
}

/** Scale and offset that fit `bounds` inside a width x height box with padding. */
export function fit(bounds, width, height, pad = 8) {
  const bw = Math.max(1, bounds.right - bounds.x), bh = Math.max(1, bounds.bottom - bounds.y);
  const scale = Math.min((width - pad * 2) / bw, (height - pad * 2) / bh);
  return { scale, ox: (width - bw * scale) / 2 - bounds.x * scale, oy: (height - bh * scale) / 2 - bounds.y * scale };
}

export function drawPreview(canvas, workflow, theme = {}) {
  const bounds = workflowBounds(workflow);
  const ctx = canvas.getContext("2d");
  const dpr = Math.min(2, globalThis.devicePixelRatio || 1);
  const width = canvas.clientWidth || canvas.width, height = canvas.clientHeight || canvas.height;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  if (!bounds) return false;
  const { scale, ox, oy } = fit(bounds, width, height);
  const px = (x) => x * scale + ox, py = (y) => y * scale + oy;

  for (const g of Array.isArray(workflow.groups) ? workflow.groups : []) {
    const [x, y, w, h] = Array.isArray(g?.bounding) ? g.bounding : [];
    if (!finite(x, y, w, h)) continue;
    ctx.fillStyle = (typeof g.color === "string" ? g.color : "#667686") + "33";
    ctx.strokeStyle = (typeof g.color === "string" ? g.color : "#667686") + "99";
    ctx.lineWidth = 1;
    ctx.fillRect(px(x), py(y), w * scale, h * scale);
    ctx.strokeRect(px(x) + 0.5, py(y) + 0.5, w * scale, h * scale);
  }

  const byId = new Map();
  for (const n of Array.isArray(workflow.nodes) ? workflow.nodes : []) byId.set(n?.id, n);
  ctx.strokeStyle = theme.link ?? "#8aa2b5aa";
  ctx.lineWidth = Math.max(0.6, scale * 3);
  for (const l of Array.isArray(workflow.links) ? workflow.links : []) {
    const [, from, , to] = Array.isArray(l) ? l : [l?.id, l?.origin_id, l?.origin_slot, l?.target_id];
    const a = byId.get(from), b = byId.get(to);
    if (!a || !b) continue;
    const [ax, ay] = vec(a.pos), [aw] = vec(a.size), [bx, by] = vec(b.pos);
    if (!finite(ax, ay, aw, bx, by)) continue;
    ctx.beginPath();
    ctx.moveTo(px(ax + aw), py(ay + 14));
    ctx.bezierCurveTo(px(ax + aw) + 24 * scale * 4, py(ay + 14), px(bx) - 24 * scale * 4, py(by + 14), px(bx), py(by + 14));
    ctx.stroke();
  }

  for (const n of byId.values()) {
    const [x, y] = vec(n?.pos), [w, h] = vec(n?.size);
    if (!finite(x, y, w, h)) continue;
    ctx.globalAlpha = n.mode === 2 || n.mode === 4 ? 0.35 : 1;
    ctx.fillStyle = typeof n.bgcolor === "string" ? n.bgcolor : theme.node ?? "#4b5b6b";
    ctx.fillRect(px(x), py(y), Math.max(1.5, w * scale), Math.max(1.5, h * scale));
    ctx.fillStyle = typeof n.color === "string" ? n.color : theme.title ?? "#6d8197";
    ctx.fillRect(px(x), py(y), Math.max(1.5, w * scale), Math.max(1, Math.min(h * scale, 20 * scale)));
  }
  ctx.globalAlpha = 1;
  return true;
}
