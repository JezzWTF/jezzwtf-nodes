// Gallery Load: a floating, non-blocking gallery window (like Paste Stack) that picks images for the node.
// The node keeps its picks as a JSON list in the hidden `selection` widget; the window edits that list.
import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { chain, fitHeight, findWidget, h, hideWidget } from "../utility_core/_shared.js";
import { createPanel } from "../workspace/panel.js";
import { applyClick, crumbs, movePick, parentOf, parseSelection, refOf, selectAll, summary } from "./gallery_logic.js";

const NODE = "JWTFGalleryLoad";
const THUMB = 168;

let gallery = null;

const thumbUrl = (type, name) => {
  const slash = name.lastIndexOf("/");
  const q = new URLSearchParams({ filename: name.slice(slash + 1), subfolder: slash < 0 ? "" : name.slice(0, slash), type, preview: "webp;70" });
  return api.apiURL(`/view?${q}`);
};

function createGallery() {
  const panel = createPanel({ id: "gallery", title: "Gallery", className: "jwtf-gallery", size: { w: 860, h: 620 }, at: { x: 120, y: 90 } });
  const state = { type: "input", folder: "", query: "", data: null, selection: [], anchor: null, target: null, order: [] };

  const typeSelect = h("select", { title: "Folder to browse" }, h("option", { value: "input" }, "input"), h("option", { value: "output" }, "output"));
  const search = h("input.jwtf-ws-search", { type: "search", placeholder: "Filter by name…", "aria-label": "Filter images" });
  panel.headerExtra.append(typeSelect, search);

  const trail = h("nav.jwtf-gal-trail", { "aria-label": "Folder" });
  const grid = h("div.jwtf-gal-grid");
  const strip = h("div.jwtf-gal-strip", { "aria-label": "Picked images" });
  const note = h("span.jwtf-gal-note");
  const useBtn = h("button.jwtf-gal-use", { type: "button" }, "Use picks");
  const clearBtn = h("button", { type: "button", title: "Clear the picks" }, "Clear");
  const allBtn = h("button", { type: "button", title: "Pick every image in this folder" }, "Pick all");
  panel.body.append(trail, grid, strip);
  panel.footer.append(note, allBtn, clearBtn, useBtn);

  const commit = () => {
    const node = state.target;
    if (!node) return;
    const widget = findWidget(node, "selection");
    if (!widget) return;
    widget.value = JSON.stringify(state.selection);
    widget.callback?.(widget.value);
    node._jwtfGal?.refresh();
    node.setDirtyCanvas(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
  };

  const renderStrip = () => {
    strip.replaceChildren(...state.selection.map((ref) => {
      const slash = ref.lastIndexOf("/");
      const bracket = ref.match(/^(.*?)\s*\[(input|output|temp)\]$/i);
      const type = bracket ? bracket[2].toLowerCase() : "input";
      const name = bracket ? bracket[1] : ref;
      const img = h("img", { src: thumbUrl(type, name), alt: ref, title: ref, loading: "lazy", draggable: false });
      const left = h("button", { type: "button", title: "Earlier in the batch", onclick: () => { state.selection = movePick(state.selection, ref, -1); renderAll(); commit(); } }, "‹");
      const right = h("button", { type: "button", title: "Later in the batch", onclick: () => { state.selection = movePick(state.selection, ref, 1); renderAll(); commit(); } }, "›");
      const drop = h("button", { type: "button", title: "Remove", onclick: () => { state.selection = state.selection.filter((r) => r !== ref); renderAll(); commit(); } }, "×");
      return h("figure", {}, img, h("figcaption", {}, ref.slice(slash + 1)), h("div.jwtf-gal-ops", {}, left, right, drop));
    }));
    strip.hidden = !state.selection.length;
  };

  const renderGrid = () => {
    const data = state.data;
    if (!data) { grid.replaceChildren(h("p.jwtf-gal-empty", {}, "Loading…")); return; }
    const cells = [];
    if (state.folder) cells.push(h("button.jwtf-gal-folder", { type: "button", onclick: () => open(state.type, parentOf(state.folder)) }, "↰ ..") );
    for (const f of data.folders) {
      const next = state.folder ? `${state.folder}/${f}` : f;
      cells.push(h("button.jwtf-gal-folder", { type: "button", onclick: () => open(state.type, next) }, `📁 ${f}`));
    }
    state.order = data.files.map((f) => refOf(state.type, f.name));
    for (const f of data.files) {
      const ref = refOf(state.type, f.name);
      const picked = state.selection.indexOf(ref);
      const cell = h("button.jwtf-gal-cell", { type: "button", "aria-pressed": String(picked >= 0), title: f.name, ondblclick: () => { state.selection = [ref]; commit(); panel.hide(); } },
        h("img", { src: thumbUrl(state.type, f.name), alt: f.name, loading: "lazy", draggable: false }),
        h("span.jwtf-gal-name", {}, f.name.split("/").pop()),
        picked >= 0 ? h("span.jwtf-gal-badge", {}, String(picked + 1)) : "");
      cell.addEventListener("click", (e) => {
        const next = applyClick({ selection: state.selection, anchor: state.anchor, order: state.order }, ref, { ctrl: e.ctrlKey || e.metaKey, shift: e.shiftKey });
        state.selection = next.selection; state.anchor = next.anchor;
        renderAll(); commit();
      });
      cells.push(cell);
    }
    if (!data.files.length && !data.folders.length) cells.push(h("p.jwtf-gal-empty", {}, state.query ? "Nothing matches the filter." : "This folder has no images."));
    grid.replaceChildren(...cells);
    note.textContent = data.truncated ? "Showing the newest images only; use the filter to narrow down." : `${data.files.length} image${data.files.length === 1 ? "" : "s"}`;
  };

  const renderTrail = () => {
    trail.replaceChildren(...crumbs(state.type, state.folder).flatMap((c, i) => [
      i ? h("span", { "aria-hidden": "true" }, "/") : "",
      h("button", { type: "button", onclick: () => open(state.type, c.folder) }, c.label),
    ]));
  };

  const renderAll = () => { renderTrail(); renderGrid(); renderStrip(); useBtn.textContent = state.selection.length ? `Use ${state.selection.length} pick${state.selection.length === 1 ? "" : "s"}` : "Use picks"; };

  let token = 0;
  async function open(type, folder) {
    state.type = type; state.folder = folder; state.data = null; typeSelect.value = type;
    const mine = ++token;
    renderAll();
    try {
      const q = new URLSearchParams({ type, folder, q: state.query });
      const res = await api.fetchApi(`/jezzwtf/gallery/list?${q}`);
      const data = await res.json();
      if (mine !== token) return;
      state.data = { folders: [], files: [], truncated: false, ...data };
    } catch {
      if (mine !== token) return;
      state.data = { folders: [], files: [], truncated: false };
      note.textContent = "Could not read the folder.";
    }
    renderAll();
  }

  typeSelect.addEventListener("change", () => open(typeSelect.value, ""));
  let timer = 0;
  search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { state.query = search.value; open(state.type, state.folder); }, 220); });
  useBtn.addEventListener("click", () => { commit(); panel.hide(); });
  clearBtn.addEventListener("click", () => { state.selection = []; state.anchor = null; renderAll(); commit(); });
  allBtn.addEventListener("click", () => { state.selection = selectAll(state.selection, state.order); renderAll(); commit(); });

  return {
    panel,
    openFor(node) {
      state.target = node;
      state.selection = parseSelection(findWidget(node, "selection")?.value);
      state.anchor = state.selection.at(-1) ?? null;
      panel.show();
      open(state.type, state.folder);
    },
  };
}

function setup(node) {
  const widget = findWidget(node, "selection");
  if (!widget) return;
  hideWidget(node, widget);
  const label = h("div.jwtf-gal-label", {}, summary([]));
  const button = h("button.jwtf-gal-open", { type: "button" }, "Open gallery");
  const holder = h("div.jwtf-gal-node", {}, label, button);
  node.addDOMWidget("jwtf_gallery", "jwtf_gallery", holder, { serialize: false, getMinHeight: () => 64 });
  const refresh = () => { label.textContent = summary(parseSelection(widget.value)); };
  button.addEventListener("click", () => { gallery ??= createGallery(); gallery.openFor(node); });
  node._jwtfGal = { refresh };
  refresh();
  fitHeight(node, 260);
}

app.registerExtension({
  name: "JezzWTF.Gallery",
  async setup() {
    const href = new URL("./gallery.css", import.meta.url).href;
    document.head.append(h("link", { rel: "stylesheet", href }));
  },
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE) return;
    chain(nodeType.prototype, "onNodeCreated", function () { setup(this); });
    chain(nodeType.prototype, "onConfigure", function () { this._jwtfGal?.refresh(); });
  },
});
