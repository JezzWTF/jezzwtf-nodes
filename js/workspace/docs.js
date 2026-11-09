// Documentation window: a searchable tree of help topics for the JezzWTF nodes. The pages are Markdown files in
// ./docs, listed in docs/index.json; nothing is editable here.
import { h } from "../utility_core/_shared.js";
import { blocksToText, parseMarkdown, renderBlocks } from "./md.js";
import { createPanel } from "./panel.js";
import { score, snippet } from "./search.js";

const LAST_KEY = "jezzwtf.docs.lastTopic";
const base = new URL("./docs/", import.meta.url);

async function getText(path) {
  const res = await fetch(new URL(path, base), { cache: "no-store" });
  if (!res.ok) throw new Error(`Could not load ${path} (${res.status}).`);
  return res.text();
}

export function createDocumentation() {
  let wanted; // a topic requested before the pages finished loading
  const modal = createPanel({
    id: "docs", title: "JezzWTF Documentation", className: "jwtf-ws-docs", size: { w: 880, h: 620 }, at: { x: Math.max(24, innerWidth - 940), y: 90 },
    onShow: () => { ensureShown(); },
  });
  const search = h("input.jwtf-ws-search", { type: "search", placeholder: "Search nodes, topics or a problem…", "aria-label": "Search documentation" });
  const homeBtn = h("button", { type: "button", textContent: "Home" });
  const tree = h("nav.jwtf-ws-tree", { "aria-label": "Topics" });
  const page = h("article.jwtf-ws-page", { tabIndex: -1 });
  modal.headerExtra.append(search, homeBtn);
  modal.body.append(tree, page);
  modal.footer.append(h("kbd", { textContent: "type" }), h("span", { textContent: "search" }), h("kbd", { textContent: "Esc" }), h("span", { textContent: "close" }));

  let sections = [];
  let topics = new Map(); // id -> { id, title, section, keywords, text, blocks }
  let loaded = false;
  let current = null;
  const collapsed = new Set();

  const showError = (msg) => page.replaceChildren(h("p.jwtf-ws-empty", { textContent: msg }));

  async function load() {
    if (loaded) return;
    const index = JSON.parse(await getText("index.json"));
    sections = index.sections ?? [];
    const pending = [];
    for (const section of sections) {
      for (const t of section.topics) {
        const topic = { ...t, section: section.title, text: "", blocks: [] };
        topics.set(t.id, topic);
        pending.push(getText(t.file).then((md) => { topic.blocks = parseMarkdown(md); topic.text = blocksToText(topic.blocks); })
          .catch(() => { topic.blocks = parseMarkdown("This page could not be loaded."); }));
      }
    }
    await Promise.all(pending);
    loaded = true;
  }

  function renderTree(results) {
    tree.replaceChildren();
    if (results) {
      if (!results.length) tree.append(h("p.jwtf-ws-empty", { textContent: "No topics match." }));
      for (const r of results) {
        tree.append(h("button.jwtf-ws-hit", { type: "button", "aria-current": current === r.topic.id ? "page" : null, onclick: () => show(r.topic.id) },
          h("strong", { textContent: r.topic.title }), h("small", { textContent: r.topic.section }),
          h("span", { textContent: snippet(r.topic.text, search.value) })));
      }
      return;
    }
    for (const section of sections) {
      const closed = collapsed.has(section.title);
      tree.append(h("button.jwtf-ws-section", { type: "button", "aria-expanded": String(!closed),
        onclick: () => { if (closed) collapsed.delete(section.title); else collapsed.add(section.title); renderTree(); } },
      h("span", { textContent: closed ? "▸" : "▾" }), h("span", { textContent: section.title }), h("small", { textContent: String(section.topics.length) })));
      if (closed) continue;
      for (const t of section.topics) {
        tree.append(h("button.jwtf-ws-topic", { type: "button", "aria-current": current === t.id ? "page" : null, onclick: () => show(t.id) }, t.title));
      }
    }
  }

  function show(id) {
    const topic = topics.get(id);
    if (!topic) return;
    current = id;
    try { localStorage.setItem(LAST_KEY, id); } catch { /* optional */ }
    const copy = h("button", { type: "button", textContent: "Copy as text" });
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(`${topic.title}\n\n${topic.text}`); copy.textContent = "Copied"; }
      catch { copy.textContent = "Copy failed"; }
      setTimeout(() => { copy.textContent = "Copy as text"; }, 1400);
    });
    page.replaceChildren(
      h("div.jwtf-ws-crumb", {}, h("span", { textContent: topic.section.toUpperCase() }), " / ", h("span", { textContent: topic.title.toUpperCase() })),
      h("h2", { textContent: topic.title }),
      h("div.jwtf-ws-copy", {}, copy),
      // The page title is already shown above, so skip the Markdown H1 when it repeats it.
      ...renderBlocks(topic.blocks[0]?.type === "heading" && topic.blocks[0].level === 1 ? topic.blocks.slice(1) : topic.blocks, h, show));
    page.scrollTop = 0;
    renderTree(search.value.trim() ? rank() : null);
  }

  function rank() {
    return [...topics.values()].map((topic) => ({ topic, s: score(topic, search.value) })).filter((r) => r.s > 0).sort((a, b) => b.s - a.s);
  }

  function onSearch() {
    renderTree(search.value.trim() ? rank() : null);
  }

  search.addEventListener("input", onSearch);
  homeBtn.addEventListener("click", () => { search.value = ""; show("welcome"); });
  modal.root.addEventListener("keydown", (ev) => {
    if (ev.defaultPrevented || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    if (ev.key.length === 1 && !(ev.target instanceof HTMLInputElement)) search.focus();
  }, true);

  // Runs whenever the panel is shown, however it was opened (dock, command, menu or a restored session).
  async function ensureShown() {
    if (!loaded) page.replaceChildren(h("p.jwtf-ws-empty", { textContent: "Loading…" }));
    try { await load(); } catch (error) { showError(error.message); return; }
    let last = wanted;
    wanted = undefined;
    try { last ??= current ?? localStorage.getItem(LAST_KEY) ?? undefined; } catch { /* optional */ }
    search.value = "";
    show(topics.has(last) ? last : "welcome");
  }

  async function open(topicId) {
    wanted = topicId;
    if (modal.visible) await ensureShown(); else modal.show({ focus: false });
    search.focus();
  }

  return {
    panel: modal,
    open,
    toggle(topicId) { if (modal.visible && !topicId) modal.hide(); else open(topicId); },
  };
}
