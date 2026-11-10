// Pure helpers for the Gallery window (no DOM, no ComfyUI imports) so they can be tested under plain node.

/** Stored form of a picked file: plain for the input folder, annotated otherwise (Load Image style). */
export const refOf = (type, name) => (type === "input" ? name : `${name} [${type}]`);

/** Breadcrumb trail for a folder path: [{ label, folder }] starting at the root. */
export function crumbs(type, folder) {
  const out = [{ label: type, folder: "" }];
  let acc = "";
  for (const part of String(folder ?? "").split("/").filter(Boolean)) {
    acc = acc ? `${acc}/${part}` : part;
    out.push({ label: part, folder: acc });
  }
  return out;
}

/** The parent of a folder path ("" for the root). */
export const parentOf = (folder) => String(folder ?? "").split("/").filter(Boolean).slice(0, -1).join("/");

/**
 * Apply a click to a selection (an ordered array of refs).
 * Plain click: just that file. Ctrl/Cmd: toggle it. Shift: everything between the anchor and the clicked file
 * (in `order`), added to the selection. Returns { selection, anchor }.
 */
export function applyClick({ selection, anchor, order }, ref, { ctrl = false, shift = false } = {}) {
  if (shift && anchor && order.includes(anchor) && order.includes(ref)) {
    const a = order.indexOf(anchor);
    const b = order.indexOf(ref);
    const range = order.slice(Math.min(a, b), Math.max(a, b) + 1);
    const next = [...selection];
    for (const r of range) if (!next.includes(r)) next.push(r);
    return { selection: next, anchor };
  }
  if (ctrl) {
    const has = selection.includes(ref);
    return { selection: has ? selection.filter((r) => r !== ref) : [...selection, ref], anchor: ref };
  }
  return { selection: [ref], anchor: ref };
}

/** Select every file in `order`, keeping the existing picks first so their batch order is stable. */
export function selectAll(selection, order) {
  return [...selection, ...order.filter((r) => !selection.includes(r))];
}

/** Move one pick within the batch order. */
export function movePick(selection, ref, delta) {
  const i = selection.indexOf(ref);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= selection.length) return selection;
  const next = [...selection];
  [next[i], next[j]] = [next[j], next[i]];
  return next;
}

/** Parse the node's JSON list defensively. */
export function parseSelection(text) {
  try {
    const data = JSON.parse(text || "[]");
    return Array.isArray(data) ? [...new Set(data.filter((x) => typeof x === "string" && x.trim()))] : [];
  } catch {
    return [];
  }
}

/** Compact summary for the node body: "3 images: a.png, b.png, +1 more". */
export function summary(selection, shown = 2) {
  if (!selection.length) return "No images picked";
  const names = selection.slice(0, shown).map((r) => r.split("/").pop());
  const more = selection.length - names.length;
  const head = `${selection.length} image${selection.length === 1 ? "" : "s"}`;
  return `${head}: ${names.join(", ")}${more > 0 ? `, +${more} more` : ""}`;
}
