// Workflows window: browse saved workflows and the bundled examples with thumbnails, search that looks inside
// workflows, folders, favourites and what-it-makes / model categories.
import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { h } from "../utility_core/_shared.js";
import { createPanel } from "./panel.js";
import { drawPreview } from "./preview.js";
import { ago, categorize, indexWorkflow, matchesAll } from "./search.js";

const FAVORITES_KEY = "jezzwtf.workflowFavorites.v2";
const PREFS_KEY = "jezzwtf.workflowBrowser";
const CONCURRENCY = 3;
const packName = () => /\/extensions\/([^/]+)\//.exec(import.meta.url)?.[1] ?? "jezzwtf-nodes";

const read = (key, fallback) => {
  try { const v = JSON.parse(localStorage.getItem(key) ?? "null"); return v ?? fallback; } catch { return fallback; }
};
const write = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { return false; } };

async function getJSON(path, signal) {
  const res = await api.fetchApi(path, { cache: "no-store", signal });
  if (!res.ok) throw new Error(`ComfyUI returned ${res.status}.`);
  return res.json();
}

/** Keep only what thumbnails need, so hundreds of big workflows do not sit in memory. */
function compact(workflow) {
  return {
    nodes: (workflow?.nodes ?? []).map((n) => ({ id: n.id, pos: n.pos, size: n.size, bgcolor: n.bgcolor, color: n.color, mode: n.mode })),
    groups: (workflow?.groups ?? []).map((g) => ({ bounding: g.bounding, color: g.color })),
    links: workflow?.links ?? [],
  };
}

export function createWorkflowBrowser() {
  const modal = createPanel({
    id: "workflows", title: "JezzWTF Workflows", className: "jwtf-ws-workflows", size: { w: 1040, h: 640 }, at: { x: 90, y: 70 },
    onShow: () => { render(); refresh(); },
    onHide: () => abortIndexing(),
  });
  const prefs = { view: "grid", sort: "recent", ...read(PREFS_KEY, {}) };
  const favorites = new Set(read(FAVORITES_KEY, []).filter((x) => typeof x === "string"));
  let entries = [];
  const info = new Map(); // id -> { index, thumb, tags }
  let filter = { kind: "all", value: "" };
  let selected = null;
  let indexing = null;
  let busy = false;

  const search = h("input.jwtf-ws-search", { type: "search", placeholder: "Search names, models, prompts, notes…", "aria-label": "Search workflows" });
  const gridBtn = h("button", { type: "button", textContent: "Grid" });
  const listBtn = h("button", { type: "button", textContent: "List" });
  const sort = h("select", { "aria-label": "Sort" },
    h("option", { value: "recent", textContent: "Sort: Recent" }),
    h("option", { value: "name", textContent: "Sort: Name" }),
    h("option", { value: "nodes", textContent: "Sort: Nodes" }));
  const refreshBtn = h("button", { type: "button", textContent: "Refresh" });
  const status = h("div.jwtf-ws-status", { role: "status" });
  const sidebar = h("nav.jwtf-ws-sidebar", { "aria-label": "Categories" });
  const cards = h("div.jwtf-ws-cards");
  const details = h("aside.jwtf-ws-details");
  modal.headerExtra.append(search, h("div.jwtf-ws-seg", {}, gridBtn, listBtn), sort, refreshBtn);
  modal.body.append(sidebar, h("div.jwtf-ws-main", {}, status, cards), details);
  modal.footer.append(
    ...[["type", "search"], ["←→↑↓", "move"], ["Enter", "open"], ["double click", "open"], ["Esc", "close"]]
      .flatMap(([k, t]) => [h("kbd", { textContent: k }), h("span", { textContent: t })]));

  const idOf = (e) => `${e.source}:${e.path}`;
  const keyText = (e) => {
    const i = info.get(e.id)?.index;
    return [e.name, e.folder, e.source === "example" ? "example jezzwtf" : "", i?.text, i?.models?.join(" "), i?.types?.join(" ")].join("\n");
  };

  function visibleEntries() {
    const list = entries.filter((e) => {
      const t = info.get(e.id)?.tags;
      if (filter.kind === "fav" && !favorites.has(e.id)) return false;
      if (filter.kind === "examples" && e.source !== "example") return false;
      if (filter.kind === "folder" && !(e.source === "user" && e.folder === filter.value)) return false;
      if (filter.kind === "makes" && !t?.makes.includes(filter.value)) return false;
      if (filter.kind === "model" && !t?.models.includes(filter.value)) return false;
      return matchesAll(keyText(e), search.value);
    });
    const by = { recent: (a, b) => b.modified - a.modified || a.name.localeCompare(b.name),
      name: (a, b) => a.name.localeCompare(b.name),
      nodes: (a, b) => (info.get(b.id)?.index?.nodeCount ?? 0) - (info.get(a.id)?.index?.nodeCount ?? 0) };
    list.sort(by[prefs.sort] ?? by.recent);
    if (filter.kind === "recent") return list.filter((e) => e.source === "user").slice(0, 20);
    return list;
  }

  function renderSidebar() {
    const count = (fn) => entries.filter(fn).length;
    const item = (label, kind, value, n) => {
      const on = filter.kind === kind && filter.value === value;
      return h("button.jwtf-ws-side", { type: "button", "aria-current": on ? "true" : null, onclick: () => { filter = { kind, value }; render(); } },
        h("span", { textContent: label }), h("small", { textContent: n ?? "" }));
    };
    const user = entries.filter((e) => e.source === "user");
    const folders = [...new Set(user.map((e) => e.folder))].sort();
    const makes = new Map(), models = new Map();
    for (const e of entries) {
      for (const m of info.get(e.id)?.tags?.makes ?? []) makes.set(m, (makes.get(m) ?? 0) + 1);
      for (const m of info.get(e.id)?.tags?.models ?? []) models.set(m, (models.get(m) ?? 0) + 1);
    }
    sidebar.replaceChildren(
      item("All workflows", "all", "", entries.length),
      item("Favourites", "fav", "", count((e) => favorites.has(e.id))),
      item("Recent", "recent", "", Math.min(20, user.length)),
      count((e) => e.source === "example") ? item("JezzWTF examples", "examples", "", count((e) => e.source === "example")) : null,
      folders.length ? h("div.jwtf-ws-side-title", { textContent: "Folders" }) : null,
      ...folders.map((f) => item(f || "(loose files)", "folder", f, user.filter((e) => e.folder === f).length)),
      makes.size ? h("div.jwtf-ws-side-title", { textContent: "What it makes" }) : null,
      ...[...makes].sort((a, b) => b[1] - a[1]).map(([m, n]) => item(m, "makes", m, n)),
      models.size ? h("div.jwtf-ws-side-title", { textContent: "Model" }) : null,
      ...[...models].sort((a, b) => b[1] - a[1]).map(([m, n]) => item(m, "model", m, n)));
  }

  function paint(canvas, id) {
    const thumb = info.get(id)?.thumb;
    if (thumb && canvas.isConnected) drawPreview(canvas, thumb);
  }

  function toggleFavorite(e) {
    if (favorites.has(e.id)) favorites.delete(e.id); else favorites.add(e.id);
    if (!write(FAVORITES_KEY, [...favorites])) status.textContent = "Favourites could not be saved in this browser.";
    render();
  }

  function render() {
    const list = visibleEntries();
    gridBtn.setAttribute("aria-pressed", String(prefs.view === "grid"));
    listBtn.setAttribute("aria-pressed", String(prefs.view === "list"));
    sort.value = prefs.sort;
    cards.className = `jwtf-ws-cards ${prefs.view}`;
    cards.replaceChildren();
    if (!list.length) cards.append(h("p.jwtf-ws-empty", { textContent: entries.length ? "No workflows match." : "No workflows found." }));
    for (const e of list) {
      const star = h("button.jwtf-ws-star", { type: "button", textContent: favorites.has(e.id) ? "★" : "☆", "aria-pressed": String(favorites.has(e.id)),
        "aria-label": `Favourite ${e.name}`, onclick: (ev) => { ev.stopPropagation(); toggleFavorite(e); } });
      const idx = info.get(e.id)?.index;
      const meta = [ago(e.modified), idx ? (idx.apiFormat ? `API format · ${idx.nodeCount} nodes` : `${idx.nodeCount} nodes`) : ""].filter(Boolean).join(" · ");
      const canvas = prefs.view === "grid" ? h("canvas.jwtf-ws-thumb", { "aria-hidden": "true" }) : null;
      const card = h("div.jwtf-ws-card", { tabIndex: 0, dataset: { id: e.id }, "aria-selected": String(selected === e.id), title: e.path,
        onclick: () => select(e.id), ondblclick: () => open(e) },
        canvas, h("div.jwtf-ws-card-text", {}, h("strong", { textContent: e.name }),
          h("small", { textContent: e.source === "example" ? `Example${meta ? " · " + meta : ""}` : [e.folder, meta].filter(Boolean).join(" · ") })),
        star);
      cards.append(card);
      if (canvas) requestAnimationFrame(() => paint(canvas, e.id));
    }
    renderSidebar();
    const total = entries.length;
    status.textContent = indexing ? `${list.length} of ${total} workflows · indexing ${indexing.done}/${total}` : `${list.length} of ${total} workflows`;
    renderDetails();
  }

  function select(id) {
    selected = id;
    for (const c of cards.children) c.setAttribute?.("aria-selected", String(c.dataset?.id === id));
    renderDetails();
  }

  function renderDetails() {
    const e = entries.find((x) => x.id === selected);
    if (!e) { details.replaceChildren(h("p.jwtf-ws-empty", { textContent: "Pick a workflow to see what is in it." })); return; }
    const i = info.get(e.id)?.index;
    const tags = info.get(e.id)?.tags;
    const note = (i?.text?.split("\n").find((l) => l.length > 30) ?? "").replace(/[*`#>_]+/g, "");
    details.replaceChildren(
      h("h3", { textContent: e.name }),
      h("p.jwtf-ws-path", { textContent: e.source === "example" ? "Bundled example" : e.path }),
      h("div.jwtf-ws-actions", {}, h("button.jwtf-ws-primary", { type: "button", textContent: "Open", onclick: () => open(e) }),
        h("button", { type: "button", textContent: favorites.has(e.id) ? "Unfavourite" : "Favourite", onclick: () => toggleFavorite(e) })),
      i ? h("dl", {},
        h("dt", { textContent: "Nodes" }), h("dd", { textContent: String(i.nodeCount) }),
        i.apiFormat ? h("dt", { textContent: "Format" }) : null, i.apiFormat ? h("dd", { textContent: "API format: it has no layout, so it cannot be drawn or opened as a graph here." }) : null,
        tags?.makes.length ? h("dt", { textContent: "Makes" }) : null, tags?.makes.length ? h("dd", { textContent: tags.makes.join(", ") }) : null,
        i.models.length ? h("dt", { textContent: "Models" }) : null,
        i.models.length ? h("dd", {}, ...i.models.slice(0, 8).map((m) => h("div", { textContent: m }))) : null,
        note ? h("dt", { textContent: "Notes" }) : null, note ? h("dd", { textContent: note.slice(0, 280) }) : null)
        : h("p.jwtf-ws-empty", { textContent: "Reading workflow…" }));
  }

  function abortIndexing() { indexing?.abort.abort(); indexing = null; }

  async function runIndexing() {
    abortIndexing();
    const abort = new AbortController();
    indexing = { abort, done: 0 };
    const queue = entries.slice();
    const worker = async () => {
      while (queue.length && !abort.signal.aborted) {
        const e = queue.shift();
        try {
          const wf = await getJSON(e.source === "example" ? `/workflow_templates/${e.pack}/${encodeURIComponent(e.name)}.json` : `/userdata/${encodeURIComponent(`workflows/${e.path}`)}`, abort.signal);
          const index = indexWorkflow(wf);
          info.set(e.id, { index, thumb: compact(wf), tags: categorize(index) });
        } catch { info.set(e.id, { index: { nodeCount: 0, types: [], models: [], text: "" }, thumb: null, tags: { makes: [], models: [] } }); }
        if (abort.signal.aborted) return;
        indexing.done++;
        const canvas = cards.querySelector(`[data-id="${CSS.escape(e.id)}"] canvas`);
        if (canvas) paint(canvas, e.id);
        if (indexing.done % 6 === 0 || !queue.length) render();
      }
    };
    await Promise.all(Array.from({ length: CONCURRENCY }, worker));
    if (!abort.signal.aborted) { indexing = null; render(); }
  }

  async function refresh() {
    status.textContent = "Loading workflows…";
    abortIndexing();
    try {
      const [list, templates] = await Promise.all([
        getJSON("/userdata?dir=workflows&recurse=true&full_info=true"),
        getJSON("/workflow_templates").catch(() => ({})),
      ]);
      const user = list.filter((f) => typeof f?.path === "string" && /\.json$/i.test(f.path)).map((f) => {
        const cut = f.path.lastIndexOf("/");
        return { source: "user", path: f.path, name: f.path.slice(cut + 1, -5), folder: f.path.slice(0, Math.max(0, cut)), modified: f.modified ?? 0 };
      });
      const pack = packName();
      const examples = (templates[pack] ?? []).map((name) => ({ source: "example", pack, path: `${pack}/${name}`, name, folder: "", modified: 0 }));
      entries = [...user, ...examples].map((e) => ({ ...e, id: idOf(e) }));
      if (!entries.some((e) => e.id === selected)) selected = null;
      render();
      runIndexing();
    } catch (error) {
      status.textContent = `Could not list workflows. ${error.message}`;
    }
  }

  async function open(e) {
    if (busy) return;
    busy = true;
    status.textContent = "Opening workflow…";
    try {
      if (e.source === "example") {
        const wf = await getJSON(`/workflow_templates/${e.pack}/${encodeURIComponent(e.name)}.json`);
        if ((await app.loadGraphData(wf, true, true, e.name)) === false) throw new Error("ComfyUI could not open the workflow.");
      } else {
        const store = app.extensionManager?.workflow;
        if (!store?.getWorkflowByPath) throw new Error("This frontend does not expose its workflow library.");
        const key = `workflows/${e.path}`;
        let wf = store.getWorkflowByPath(key);
        if (!wf) { await store.syncWorkflows?.(); wf = store.getWorkflowByPath(key); }
        if (!wf) throw new Error("The workflow is no longer available.");
        if (store.activeWorkflow?.path !== key) {
          await wf.load(); // reuse its loaded state so unsaved edits in its tab are kept
          if (!wf.activeState) throw new Error("The workflow could not be read.");
          if ((await app.loadGraphData(wf.activeState, true, true, wf)) === false) throw new Error("ComfyUI could not open the workflow.");
        }
      }
      status.textContent = `Opened ${e.name}`;
    } catch (error) {
      status.textContent = error.message;
    } finally { busy = false; }
  }

  function move(delta) {
    const els = [...cards.querySelectorAll(".jwtf-ws-card")];
    if (!els.length) return;
    const at = Math.max(0, els.findIndex((c) => c.dataset.id === selected));
    let next = at;
    if (delta === 1 || delta === -1) next = at + delta;
    else {
      const here = els[at].offsetTop;
      const row = els.findIndex((c) => c.offsetTop !== here);
      const cols = prefs.view === "list" || row < 0 ? 1 : row;
      next = at + (delta > 0 ? cols : -cols);
    }
    next = Math.max(0, Math.min(els.length - 1, next));
    select(els[next].dataset.id);
    els[next].scrollIntoView({ block: "nearest" });
    els[next].focus({ preventScroll: true });
  }

  modal.root.addEventListener("keydown", (ev) => {
    if (ev.defaultPrevented || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    const inField = ev.target instanceof HTMLInputElement || ev.target instanceof HTMLSelectElement;
    if (ev.key === "Enter" && selected && !(ev.target instanceof HTMLButtonElement)) { ev.preventDefault(); open(entries.find((e) => e.id === selected)); }
    else if (ev.key.startsWith("Arrow") && !(ev.target === search && (ev.key === "ArrowLeft" || ev.key === "ArrowRight")) && !(ev.target instanceof HTMLSelectElement)) {
      ev.preventDefault();
      move({ ArrowLeft: -1, ArrowRight: 1, ArrowUp: -2, ArrowDown: 2 }[ev.key]);
    } else if (ev.key.length === 1 && !inField) search.focus();
  }, true);

  search.addEventListener("input", render);
  sort.addEventListener("change", () => { prefs.sort = sort.value; write(PREFS_KEY, prefs); render(); });
  gridBtn.addEventListener("click", () => { prefs.view = "grid"; write(PREFS_KEY, prefs); render(); });
  listBtn.addEventListener("click", () => { prefs.view = "list"; write(PREFS_KEY, prefs); render(); });
  refreshBtn.addEventListener("click", refresh);

  return {
    panel: modal,
    open() { modal.show(); search.focus(); },
    toggle() { if (modal.visible) modal.hide(); else { modal.show(); search.focus(); } },
  };
}
