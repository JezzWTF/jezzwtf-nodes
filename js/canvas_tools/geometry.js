// Pure canvas maths for Canvas Tools (no DOM, no ComfyUI imports) so it can be tested under plain node.
// A "box" is { id, x, y, w, h } in graph coordinates; `h` includes the title bar.

export const boundsOf = (boxes) => {
  if (!boxes.length) return { x: 0, y: 0, w: 0, h: 0 };
  const x0 = Math.min(...boxes.map((b) => b.x));
  const y0 = Math.min(...boxes.map((b) => b.y));
  const x1 = Math.max(...boxes.map((b) => b.x + b.w));
  const y1 = Math.max(...boxes.map((b) => b.y + b.h));
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
};

/** True when the segment (ax,ay)-(bx,by) touches the rectangle (Liang-Barsky clipping). */
export function segmentHitsRect(ax, ay, bx, by, r) {
  let t0 = 0, t1 = 1;
  const dx = bx - ax, dy = by - ay;
  const clip = (p, q) => {
    if (p === 0) return q >= 0;
    const t = q / p;
    if (p < 0) { if (t > t1) return false; if (t > t0) t0 = t; } else { if (t < t0) return false; if (t < t1) t1 = t; }
    return true;
  };
  return clip(-dx, ax - r.x) && clip(dx, r.x + r.w - ax) && clip(-dy, ay - r.y) && clip(dy, r.y + r.h - ay);
}

/** Ids of the boxes a slash from (ax,ay) to (bx,by) crosses. */
export const boxesOnSlash = (boxes, ax, ay, bx, by) => boxes.filter((b) => segmentHitsRect(ax, ay, bx, by, b)).map((b) => b.id);

const ALIGN = {
  left: (box, b) => ({ x: b.x }),
  right: (box, b) => ({ x: b.x + b.w - box.w }),
  top: (box, b) => ({ y: b.y }),
  bottom: (box, b) => ({ y: b.y + b.h - box.h }),
  "center-x": (box, b) => ({ x: b.x + (b.w - box.w) / 2 }),
  "center-y": (box, b) => ({ y: b.y + (b.h - box.h) / 2 }),
};

export const ALIGN_MODES = Object.keys(ALIGN);

/** New positions { id: {x?, y?} } that align every box to the selection's bounds. */
export function align(boxes, mode) {
  const fn = ALIGN[mode];
  if (!fn || boxes.length < 2) return {};
  const b = boundsOf(boxes);
  return Object.fromEntries(boxes.map((box) => [box.id, fn(box, b)]));
}

/** Spread boxes so the gaps between them are equal along an axis ("x" or "y"); the outer two stay put. */
export function distribute(boxes, axis) {
  if (boxes.length < 3) return {};
  const pos = axis === "x" ? "x" : "y";
  const size = axis === "x" ? "w" : "h";
  const sorted = [...boxes].sort((a, b) => a[pos] - b[pos]);
  const first = sorted[0], last = sorted[sorted.length - 1];
  const inner = sorted.slice(1, -1).reduce((sum, b) => sum + b[size], 0);
  const gap = (last[pos] - (first[pos] + first[size]) - inner) / (sorted.length - 1);
  const out = {};
  let cursor = first[pos] + first[size] + gap;
  for (const b of sorted.slice(1, -1)) { out[b.id] = { [pos]: cursor }; cursor += b[size] + gap; }
  return out;
}

/**
 * Dependency layout: columns by longest path from the sources (left to right), rows ordered by the average row of
 * each node's parents, anchored at the top-left of the original selection. `links` are { from, to } between ids.
 * Cycles are tolerated (a back edge is ignored). Returns { id: {x, y} }.
 */
export function tidyByDependency(boxes, links, { gapX = 70, gapY = 36 } = {}) {
  if (!boxes.length) return {};
  const ids = new Set(boxes.map((b) => b.id));
  const parents = new Map(boxes.map((b) => [b.id, []]));
  const children = new Map(boxes.map((b) => [b.id, []]));
  for (const { from, to } of links) {
    if (from === to || !ids.has(from) || !ids.has(to)) continue;
    parents.get(to).push(from);
    children.get(from).push(to);
  }
  // depth by DFS with an on-stack set so cycles do not recurse forever
  const depth = new Map();
  const visiting = new Set();
  const depthOf = (id) => {
    if (depth.has(id)) return depth.get(id);
    if (visiting.has(id)) return 0;
    visiting.add(id);
    let d = 0;
    for (const p of parents.get(id)) d = Math.max(d, depthOf(p) + 1);
    visiting.delete(id);
    depth.set(id, d);
    return d;
  };
  for (const b of boxes) depthOf(b.id);

  const byId = new Map(boxes.map((b) => [b.id, b]));
  const columns = [];
  for (const b of boxes) (columns[depth.get(b.id)] ??= []).push(b);

  const anchor = boundsOf(boxes);
  const rowOf = new Map();
  const out = {};
  let x = anchor.x;
  columns.forEach((column, ci) => {
    if (!column) return;
    const key = (b) => {
      const ps = parents.get(b.id).filter((p) => rowOf.has(p));
      return ps.length ? ps.reduce((s, p) => s + rowOf.get(p), 0) / ps.length : Number.MAX_SAFE_INTEGER;
    };
    column.sort((a, b) => key(a) - key(b) || a.y - b.y || String(a.id).localeCompare(String(b.id)));
    let y = anchor.y;
    column.forEach((b, i) => {
      out[b.id] = { x, y };
      rowOf.set(b.id, i);
      y += b.h + gapY;
    });
    x += Math.max(...column.map((b) => b.w)) + gapX;
  });
  return out;
}

/** Padding box for a group around some boxes, with room for the group's title bar on top. */
export function groupRect(boxes, { pad = 20, title = 34 } = {}) {
  const b = boundsOf(boxes);
  return { x: b.x - pad, y: b.y - pad - title, w: b.w + pad * 2, h: b.h + pad * 2 + title };
}
