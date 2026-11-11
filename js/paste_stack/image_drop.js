import { nodeAcceptsImage } from "./stack_logic.js";

/** Resolve a drop over either classic canvas nodes or ComfyUI's DOM node layers. */
export function imageNodeAtPoint(canvas, graph, x, y, doc = globalThis.document) {
  const element = canvas?.canvas;
  graph = canvas?.graph ?? graph;
  if (!element || !graph) return null;
  const rect = element.getBoundingClientRect();
  if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) return null;

  const hit = doc.elementFromPoint(x, y);
  const overlay = hit?.closest?.("[data-node-id], .dom-widget");
  // Accept node UI above the canvas, but never drop through unrelated panels or dialogs.
  if (hit !== element && (!overlay || !element.parentElement?.contains(overlay))) return null;

  const id = overlay?.getAttribute("data-node-id");
  let node;
  if (id != null) {
    node = graph.getNodeById?.(id) ?? graph.getNodeById?.(Number(id));
  } else {
    const ds = canvas.ds;
    if (!ds) return null;
    node = graph.getNodeOnPos?.((x - rect.left) / ds.scale - ds.offset[0], (y - rect.top) / ds.scale - ds.offset[1]);
  }
  return nodeAcceptsImage(node) ? node : null;
}
