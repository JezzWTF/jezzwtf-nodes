// Paste Stack: a floating, persistent clipboard-history panel for the ComfyUI web UI.
import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { createBackdrop } from "./backdrop.js";
import { imageNodeAtPoint } from "./image_drop.js";
import {
  LIMITS, base64ToBytes, classifyFile, clamp, findDuplicate, fingerprint, formatSize, imageMimeFromName,
  looksLikeImagePath, makeId, moveInArray, nextTopOrd, normalizeLimit, normalizeOrder,
  pickEvictions, planMove, refusalFor, relativeAge, safeUploadName, widgetValueFrom,
} from "./stack_logic.js";

const EXT_NAME = "JezzWTF.PasteStack";
const GUARD = "__jwtfPasteStackLoaded";
const DB_NAME = "jezzwtf_paste_stack";
const STORE = "items";
const UI_KEY = "jezzwtf.pasteStack.ui";
const CLIPBOARD_ROUTE = "/jezzwtf/paste_stack/clipboard";
const SET_ENABLED = "JezzWTF.PasteStack.Enabled";
const SET_LIMIT = "JezzWTF.PasteStack.Limit";
const SET_BACKDROP = "JezzWTF.PasteStack.Backdrop";
const CHIP = 46;
const DRAG_THRESHOLD = 6;
const PANEL_DRAG_THRESHOLD = 4;

const el = (tag, cls, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "text") n.textContent = v;
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids) if (kid) n.append(kid);
  return n;
};

// ------------------------------------------------------------------ extension

if (!window[GUARD]) {
  window[GUARD] = true;
  app.registerExtension({
    name: EXT_NAME,
    async setup() {
      const settings = { enabled: true, limit: LIMITS.defaultEntries, backdrop: true };
      let widget = null;
      try {
        app.ui.settings.addSetting({
          id: SET_ENABLED, name: "JezzWTF Paste Stack: show widget", type: "boolean", defaultValue: true,
          onChange: (v) => { settings.enabled = !!v; widget?.setEnabled(settings.enabled); },
        });
        app.ui.settings.addSetting({
          id: SET_LIMIT, name: "JezzWTF Paste Stack: maximum saved entries", type: "number", defaultValue: LIMITS.defaultEntries,
          attrs: { min: LIMITS.minEntries, max: LIMITS.maxEntries, step: 5 },
          onChange: (v) => { settings.limit = normalizeLimit(v); widget?.setLimit(settings.limit); },
        });
        app.ui.settings.addSetting({
          id: SET_BACKDROP, name: "JezzWTF Paste Stack: animated backdrop (WebGL2; falls back to a still gradient)", type: "boolean", defaultValue: true,
          onChange: (v) => { settings.backdrop = !!v; widget?.setBackdrop(settings.backdrop); },
        });
        settings.enabled = !!app.ui.settings.getSettingValue(SET_ENABLED, true);
        settings.backdrop = !!app.ui.settings.getSettingValue(SET_BACKDROP, true);
        settings.limit = normalizeLimit(app.ui.settings.getSettingValue(SET_LIMIT, LIMITS.defaultEntries));
      } catch { /* old frontend without the settings API: defaults apply */ }
      widget = await createWidget(settings);
    },
  });
}

// ------------------------------------------------------------------ storage

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "id" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function txDone(db, mode, fn) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const out = fn(tx.objectStore(STORE));
    tx.oncomplete = () => resolve(out && "result" in out ? out.result : undefined);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

function loadUi() {
  try { return JSON.parse(localStorage.getItem(UI_KEY) || "{}") || {}; } catch { return {}; }
}

function saveUi(ui) {
  try { localStorage.setItem(UI_KEY, JSON.stringify(ui)); } catch { /* ignore */ }
}

// ------------------------------------------------------------------ clipboard helpers

const canAsyncClipboard = () => !!(navigator.clipboard && window.isSecureContext);

async function writeText(text) {
  if (canAsyncClipboard()) { await navigator.clipboard.writeText(text); return; }
  const ta = el("textarea", "jwtf-ps-offscreen", { "aria-hidden": "true", tabindex: "-1" });
  ta.value = text;
  document.body.append(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } finally { ta.remove(); }
  if (!ok) throw new Error("copy failed");
}

async function toPngBlob(blob) {
  if (blob.type === "image/png") return blob;
  const bitmap = await createImageBitmap(blob);
  try {
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    canvas.getContext("2d").drawImage(bitmap, 0, 0);
    return await new Promise((res, rej) => canvas.toBlob((b) => (b ? res(b) : rej(new Error("encode failed"))), "image/png"));
  } finally {
    bitmap.close();
  }
}

async function writeImage(blob) {
  if (!canAsyncClipboard() || !navigator.clipboard.write || typeof ClipboardItem === "undefined") {
    throw new Error("Copying an image needs localhost or https.");
  }
  await navigator.clipboard.write([new ClipboardItem({ "image/png": await toPngBlob(blob) })]);
}

async function fetchHelperFiles() {
  try {
    const res = await api.fetchApi(CLIPBOARD_ROUTE, { method: "POST", headers: { "X-JezzWTF-Paste": "1" } });
    if (!res.ok) return [];
    const body = await res.json();
    return (body.files || []).map((f) => new File([base64ToBytes(f.data)], f.name, { type: f.mime }));
  } catch { return []; }
}

// ------------------------------------------------------------------ widget

async function createWidget(settings) {
  const ac = new AbortController();
  const sig = { signal: ac.signal };
  const cleanups = [];
  const timers = new Set();
  const urls = new Set();

  const ui = { w: 300, h: 310, state: "open", ...loadUi() };
  let enabled = settings.enabled;
  let backdropOn = settings.backdrop !== false;
  let backdrop = null;
  let limit = settings.limit;
  let items = [];
  let dbBroken = false;
  let db = null;
  let queue = Promise.resolve();
  let toastTimer = 0;
  let hovering = false;
  let editor = null;
  let clearTimer = 0;
  let clearArmed = false;
  let copyTimer = 0;
  let drag = null;
  let suppressClickUntil = 0;
  let boost = null;
  let boosting = false;
  let resizeTimer = 0;
  let dragDepth = 0;

  const later = (fn, ms) => { const id = setTimeout(() => { timers.delete(id); fn(); }, ms); timers.add(id); return id; };

  // ---- DOM
  const root = el("div", "jwtf-ps", { "data-open": "1" });
  const title = el("span", "jwtf-ps-title", { text: "Paste stack" });
  const count = el("span", "jwtf-ps-count");
  const clearBtn = el("button", "jwtf-ps-btn", { type: "button", text: "Clear" });
  const minBtn = el("button", "jwtf-ps-btn jwtf-ps-x", { type: "button", text: "×", title: "Minimize", "aria-label": "Minimize paste stack" });
  const head = el("div", "jwtf-ps-head", {}, title, count, clearBtn, minBtn);
  const list = el("div", "jwtf-ps-list");
  const pasteBtn = el("button", "jwtf-ps-paste", { type: "button" },
    el("span", "jwtf-ps-paste-main", { text: "Click here to paste" }),
    el("span", "jwtf-ps-hint", { text: "Or hover and press Ctrl+V. You can also drop files here." }));
  const toast = el("div", "jwtf-ps-toast", { role: "status", "aria-live": "polite" });
  const fx = el("canvas", "jwtf-ps-fx", { "aria-hidden": "true", hidden: true });
  const panel = el("section", "jwtf-ps-panel", { role: "region", "aria-label": "Paste stack" }, fx, head, list, pasteBtn, toast);
  const badge = el("span", "jwtf-ps-badge");
  const chip = el("button", "jwtf-ps-chip", { type: "button", "aria-label": "Open paste stack" },
    iconClipboard(), badge);
  const bar = el("div", "jwtf-ps-bar", { hidden: true });
  const outline = el("div", "jwtf-ps-outline", { hidden: true });
  root.append(panel, chip, bar, outline);
  document.body.append(root);

  // CSS: link element resolved relative to this script
  const link = el("link", "", { rel: "stylesheet", href: new URL("./paste_stack.css", import.meta.url).href });
  document.head.append(link);
  cleanups.push(() => link.remove());

  function iconClipboard() {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "22");
    svg.setAttribute("height", "22");
    svg.setAttribute("aria-hidden", "true");
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", "M9 4h6v2H9zM7 5H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-1v2h1v12H6V7h1z");
    p.setAttribute("fill", "currentColor");
    svg.append(p);
    return svg;
  }

  // ---- toast / ripple
  function say(msg, ms = 2400) {
    toast.textContent = msg;
    toast.classList.add("on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("on"), ms);
  }

  function ripple(x, y) {
    if (ui.state !== "open") return;
    const r = panel.getBoundingClientRect();
    backdrop?.ripple(x - r.left, y - r.top);
    const dot = el("span", "jwtf-ps-ripple");
    dot.style.left = `${x - r.left}px`;
    dot.style.top = `${y - r.top}px`;
    panel.append(dot);
    later(() => dot.remove(), 650);
  }

  // ---- DB guard
  async function guard(fn) {
    if (!db || dbBroken) return;
    try { await fn(db); } catch {
      dbBroken = true;
      say("Saving is blocked in this browser. Your stack will last until you refresh.", 4200);
    }
  }
  const dbPut = (rec) => guard((d) => txDone(d, "readwrite", (s) => s.put(rec)));
  const dbDelete = (id) => guard((d) => txDone(d, "readwrite", (s) => s.delete(id)));
  const dbClear = () => guard((d) => txDone(d, "readwrite", (s) => s.clear()));
  const dbPutAll = (recs) => guard((d) => txDone(d, "readwrite", (s) => { recs.forEach((r) => s.put(r)); }));

  // ---- placement
  function viewport() { return { vw: window.innerWidth, vh: window.innerHeight }; }

  function place() {
    const { vw, vh } = viewport();
    root.hidden = !enabled;
    if (ui.state === "chip") {
      if (typeof ui.cx !== "number") { ui.cx = vw - CHIP - 24; ui.cy = vh - CHIP - 24; }
      ui.cx = clamp(ui.cx, 0, Math.max(0, vw - CHIP));
      ui.cy = clamp(ui.cy, 0, Math.max(0, vh - CHIP));
      chip.style.left = `${ui.cx}px`;
      chip.style.top = `${ui.cy}px`;
    } else {
      if (typeof ui.x !== "number") { ui.x = Math.max(8, vw - ui.w - 24); ui.y = 120; }
      const w = panel.offsetWidth || ui.w;
      const h = panel.offsetHeight || ui.h;
      ui.x = clamp(ui.x, 0, Math.max(0, vw - w));
      ui.y = clamp(ui.y, 0, Math.max(0, vh - h));
      panel.style.left = `${ui.x}px`;
      panel.style.top = `${ui.y}px`;
    }
  }

  /** The backdrop runs only while the panel is open, enabled and the setting is on; otherwise the CSS gradient shows. */
  function syncBackdrop() {
    const want = enabled && backdropOn && ui.state !== "chip" && !root.hidden;
    if (!want) { backdrop?.setActive(false); fx.hidden = true; return; }
    fx.hidden = false;
    backdrop ??= createBackdrop(fx, panel, () => Math.min(1, items.length / Math.max(1, limit)));
    if (!backdrop) { fx.hidden = true; return; }
    backdrop.setActive(true);
  }

  function setBackdrop(v) { backdropOn = !!v; syncBackdrop(); }

  function applyState() {
    const open = ui.state !== "chip";
    root.dataset.open = open ? "1" : "0";
    panel.hidden = !open;
    chip.hidden = open;
    if (open) { panel.style.width = `${ui.w}px`; panel.style.height = `${ui.h}px`; }
    place();
    syncBackdrop();
  }

  function minimize() {
    cancelDrag();
    endEdit(true);
    const w = panel.offsetWidth || ui.w;
    ui.w = w;
    ui.cx = (ui.x ?? 0) + w - CHIP;
    ui.cy = ui.y ?? 0;
    ui.state = "chip";
    applyState();
    saveUi(ui);
  }

  function expand() {
    ui.x = (ui.cx ?? 0) + CHIP - ui.w;
    ui.y = ui.cy ?? 0;
    ui.state = "open";
    applyState();
    saveUi(ui);
  }

  function setEnabled(v) {
    enabled = !!v;
    if (!enabled) { cancelDrag(); endEdit(true); hovering = false; }
    place();
    syncBackdrop();
    if (enabled) renderAll();
  }

  // ---- stack operations
  function enqueue(fn) {
    const run = queue.then(fn, fn);
    queue = run.catch(() => undefined);
    return run;
  }

  async function evict() {
    const victims = pickEvictions(items, limit);
    if (!victims.length) return;
    const gone = new Set(victims.map((v) => v.id));
    items = items.filter((it) => !gone.has(it.id));
    for (const v of victims) await dbDelete(v.id);
  }

  function addItem(partial) {
    return enqueue(async () => {
      const blob = partial.kind === "text" ? new Blob([partial.text]) : partial.blob;
      const key = await fingerprint(blob);
      const dup = findDuplicate(items, partial.kind, key);
      if (dup) { items = items.filter((it) => it !== dup); await dbDelete(dup.id); }
      const now = Date.now();
      const rec = { name: "", mime: "", w: 0, h: 0, ...partial, id: makeId(now), ts: now, ord: nextTopOrd(items), key };
      items.unshift(rec);
      await dbPut(rec);
      await evict();
      renderAll();
      if (ui.state === "chip") pulse();
      return dup ? "moved" : "added";
    });
  }

  async function addText(text, name = "") {
    if (!text || !text.trim()) return null;
    const refusal = refusalFor("text", text.length);
    if (refusal) { say(refusal, 3600); return null; }
    return addItem({ kind: "text", text, name });
  }

  async function addImage(blob, name = "") {
    const refusal = refusalFor("image", blob.size);
    if (refusal) { say(refusal, 3600); return null; }
    let w = 0, h = 0;
    try { const bmp = await createImageBitmap(blob); w = bmp.width; h = bmp.height; bmp.close(); } catch { /* unknown size */ }
    return addItem({ kind: "image", blob, w, h, mime: blob.type || "image/png", name });
  }

  async function addFile(file) {
    let mime = file.type;
    if (!mime) mime = imageMimeFromName(file.name);
    const kind = classifyFile(file.name, mime);
    if (kind === "image") return addImage(mime === file.type ? file : new Blob([file], { type: mime }), file.name);
    if (kind === "text") {
      const refusal = refusalFor("text-file", file.size, file.name);
      if (refusal) { say(refusal, 3600); return null; }
      return addText(await file.text(), file.name);
    }
    const refusal = refusalFor("file", file.size, file.name);
    if (refusal) { say(refusal, 3600); return null; }
    return addItem({ kind: "file", blob: file, mime: mime || "application/octet-stream", name: file.name });
  }

  async function addFiles(files) {
    const results = [];
    for (const f of files) results.push(await addFile(f));
    return results;
  }

  function report(results) {
    const added = results.filter((r) => r === "added").length;
    if (added) say(added === 1 ? "Saved." : `Saved ${added} items.`);
    else if (results.some((r) => r === "moved")) say("Already in your stack. Moved it to the top.");
    else say("Nothing to save from the clipboard.");
  }

  async function pasteFromClipboard() {
    const results = [];
    let blocked = false;
    if (canAsyncClipboard()) {
      try {
        if (navigator.clipboard.read) {
          for (const item of await navigator.clipboard.read()) {
            if (item.types.includes("text/plain")) {
              const text = await (await item.getType("text/plain")).text();
              if (looksLikeImagePath(text)) continue;
              results.push(await addText(text));
            } else {
              const t = item.types.find((x) => x.startsWith("image/"));
              if (t) results.push(await addImage(await item.getType(t)));
            }
          }
        } else if (navigator.clipboard.readText) {
          results.push(await addText(await navigator.clipboard.readText()));
        }
      } catch (err) {
        if (err && err.name === "NotAllowedError") blocked = true;
        else { try { results.push(await addText(await navigator.clipboard.readText())); } catch { /* ignore */ } }
      }
    }
    if (results.some(Boolean)) { report(results); return; }
    const files = await fetchHelperFiles();
    if (files.length) { report(await addFiles(files)); return; }
    if (blocked) say("Clipboard access is blocked. Allow it in the address bar, or hover and press Ctrl+V.", 4800);
    else say("Nothing to paste yet. Copy some text, an image, or a file, then click again.", 3600);
  }

  async function removeItem(it) {
    if (editor && editor.item === it) endEdit(false);
    items = items.filter((x) => x !== it);
    renderAll();
    await dbDelete(it.id);
  }

  async function doClear() {
    endEdit(false);
    items = [];
    renderAll();
    await dbClear();
    say("Stack cleared.");
  }

  async function moveItem(from, to) {
    const plan = planMove(items.map((i) => i.ord), from, to);
    if (!plan) return null;
    const moved = items[from];
    items = moveInArray(items, from, plan.to);
    if (plan.renumber) {
      items.forEach((it, i) => { it.ord = i; });
      renderAll();
      await dbPutAll(items);
    } else {
      moved.ord = plan.ord;
      renderAll();
      await dbPut(moved);
    }
    return moved;
  }

  function pulse() {
    chip.classList.remove("pulse");
    void chip.offsetWidth;
    chip.classList.add("pulse");
  }

  // ---- rendering
  function revokeUrls() { for (const u of urls) URL.revokeObjectURL(u); urls.clear(); }

  function setLimit(n) {
    limit = n;
    enqueue(async () => { await evict(); renderAll(); });
  }

  function renderCounts() {
    count.textContent = `${items.length} / ${limit}`;
    badge.textContent = String(items.length);
    badge.hidden = items.length === 0;
    clearBtn.disabled = items.length === 0;
    root.style.setProperty("--jwtf-fill", String(Math.min(1, items.length / Math.max(1, limit))));
  }

  function refreshAges() {
    for (const n of panel.querySelectorAll("[data-ts]")) n.textContent = relativeAge(Number(n.dataset.ts));
  }

  function renderAll() {
    endEdit(true, true);
    revokeUrls();
    renderCounts();
    panel.classList.toggle("empty", items.length === 0);
    list.replaceChildren(...items.map(buildCard));
    clearBtnLabel();
  }

  function clearBtnLabel() {
    clearBtn.textContent = clearArmed ? "Clear all?" : "Clear";
    clearBtn.classList.toggle("warn", clearArmed);
  }

  function buildCard(it) {
    const meta = el("span", "jwtf-ps-meta-l");
    const age = el("span", "jwtf-ps-meta-r", { "data-ts": String(it.ts), title: new Date(it.ts).toLocaleString(), text: relativeAge(it.ts) });
    let body;
    let label;
    let tip;
    if (it.kind === "image") {
      const url = URL.createObjectURL(it.blob);
      urls.add(url);
      body = el("img", "jwtf-ps-thumb", { src: url, alt: "", draggable: "false" });
      meta.textContent = it.w && it.h ? `${it.w}×${it.h} image` : "image";
      label = "Copy this image entry";
      tip = "Click to copy, drag to reorder, or drag onto a Load Image node";
    } else if (it.kind === "text") {
      body = el("div", "jwtf-ps-text", { text: it.text.slice(0, 400) });
      meta.textContent = `${it.name ? it.name + ", " : ""}${it.text.length.toLocaleString("en-US")} characters`;
      label = "Copy this text entry";
      tip = "Click to copy, double-click to edit, drag to reorder";
    } else {
      body = el("div", "jwtf-ps-text", { text: it.name || "file" });
      meta.textContent = `${formatSize(it.blob.size)}, click to download`;
      label = `Download ${it.name || "paste"}`;
      tip = "Click to download, drag to reorder";
    }
    const del = el("button", "jwtf-ps-del", { type: "button", text: "×", title: "Delete", "aria-label": "Delete entry" });
    const card = el("div", `jwtf-ps-card k-${it.kind}`, { tabindex: "0", role: "button", "aria-label": label, title: tip },
      body, el("div", "jwtf-ps-meta", {}, meta, age), del);
    card._item = it;
    del.addEventListener("click", (e) => { e.stopPropagation(); removeItem(it); });
    del.addEventListener("pointerdown", (e) => e.stopPropagation());
    return card;
  }

  // ---- card activation (copy back)
  let copyPending = 0;

  async function activate(it, card) {
    try {
      if (it.kind === "text") {
        await writeText(it.text);
        say("Copied. Press Ctrl+V to use it.");
        flashCopied(card);
      } else if (it.kind === "image") {
        await writeImage(it.blob);
        say("Image copied. Press Ctrl+V to use it.");
        flashCopied(card);
      } else {
        const url = URL.createObjectURL(it.blob);
        const a = el("a", "", { href: url, download: it.name || "paste" });
        document.body.append(a);
        a.click();
        a.remove();
        later(() => URL.revokeObjectURL(url), 4000);
        say(`Downloaded ${it.name || "paste"}. Files can't go back on the clipboard.`, 3600);
      }
    } catch (err) {
      const msg = err && /needs localhost or https/.test(err.message) ? "Copying an image needs localhost or https." : "The browser blocked that copy. Click the card again.";
      say(msg, 3600);
    }
  }

  function flashCopied(card) {
    card.classList.add("copied");
    later(() => card.classList.remove("copied"), 900);
  }

  list.addEventListener("click", (e) => {
    if (performance.now() < suppressClickUntil) return;
    const card = e.target.closest(".jwtf-ps-card");
    if (!card) {
      if (e.target === list) { ripple(e.clientX, e.clientY); pasteFromClipboard(); }
      return;
    }
    if (editor && editor.item === card._item) return;
    ripple(e.clientX, e.clientY);
    const it = card._item;
    if (it.kind === "text") {
      clearTimeout(copyPending);
      if (e.detail > 1) return;
      copyPending = later(() => activate(it, card), 230);
    } else activate(it, card);
  }, sig);

  list.addEventListener("dblclick", (e) => {
    const card = e.target.closest(".jwtf-ps-card");
    if (!card || card._item.kind !== "text") return;
    clearTimeout(copyPending);
    startEdit(card);
  }, sig);

  list.addEventListener("keydown", (e) => {
    const card = e.target.closest(".jwtf-ps-card");
    if (!card || e.target !== card) return;
    const it = card._item;
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(it, card); }
    else if (e.key === "F2" && it.kind === "text") { e.preventDefault(); startEdit(card); }
    else if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      e.preventDefault();
      const from = items.indexOf(it);
      const to = e.key === "ArrowUp" ? from - 1 : from + 1;
      if (to < 0 || to >= items.length) return;
      moveItem(from, to).then(() => {
        const next = [...list.children].find((c) => c._item === it);
        next?.focus();
      });
    }
  }, sig);

  // ---- editing
  function startEdit(card) {
    const it = card._item;
    if (editor && editor.item === it) return;
    endEdit(true);
    const ta = el("textarea", "jwtf-ps-editor", { spellcheck: "false", maxlength: String(LIMITS.textChars), "aria-label": "Edit text. Changes save automatically." });
    ta.value = it.text;
    const status = el("span", "jwtf-ps-meta-l", { text: "Editing. Saves automatically." });
    const done = el("button", "jwtf-ps-btn", { type: "button", text: "Done" });
    const meta = el("div", "jwtf-ps-meta", {}, status, done);
    card.classList.add("editing");
    card.replaceChildren(ta, meta);
    card.style.minHeight = `${Math.max(190, list.clientHeight)}px`;
    const ed = { item: it, card, ta, status, before: it.text, saveTimer: 0, seq: 0, blurTimer: 0 };
    editor = ed;
    boostPanel();
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
    ta.scrollTop = ta.scrollHeight;
    ta.addEventListener("input", () => {
      clearTimeout(ed.saveTimer);
      ed.status.textContent = ta.value.trim() ? "Saving…" : "Empty text isn't saved";
      ed.saveTimer = setTimeout(() => saveEdit(ed), 600);
    });
    ta.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Escape" || (e.key === "Enter" && (e.ctrlKey || e.metaKey))) { e.preventDefault(); endEdit(true); renderAll(); }
    });
    ta.addEventListener("blur", () => { ed.blurTimer = setTimeout(() => { if (editor === ed && !card.contains(document.activeElement)) { endEdit(true); renderAll(); } }, 0); });
    done.addEventListener("pointerdown", (e) => e.preventDefault());
    done.addEventListener("click", (e) => { e.stopPropagation(); endEdit(true); renderAll(); });
    card.addEventListener("pointerdown", (e) => e.stopPropagation());
  }

  async function saveEdit(ed) {
    const value = ed.ta.value;
    if (!value.trim() || value === ed.item.text) return;
    const seq = ++ed.seq;
    const it = ed.item;
    const key = await fingerprint(new Blob([value]));
    if (seq !== ed.seq || !items.includes(it)) return;
    it.text = value;
    it.key = key;
    await dbPut(it);
    if (editor === ed) ed.status.textContent = `Saved · ${value.length.toLocaleString("en-US")} characters`;
  }

  function endEdit(save, fromRender = false) {
    const ed = editor;
    if (!ed) return;
    editor = null;
    clearTimeout(ed.saveTimer);
    clearTimeout(ed.blurTimer);
    const value = ed.ta.value;
    if (save && value !== ed.before) {
      if (!value.trim()) say("Empty text can't be saved, so I kept the previous version.", 3600);
      else if (value !== ed.item.text) {
        ed.seq++;
        ed.item.text = value;
        fingerprint(new Blob([value])).then((k) => { ed.item.key = k; return dbPut(ed.item); });
      }
    }
    unboostPanel();
    if (!fromRender) renderAll();
  }

  function boostPanel() {
    if (ui.state !== "open" || panel.offsetHeight >= 440) return;
    const { vh } = viewport();
    boost = { h: panel.offsetHeight, y: ui.y, setH: 0 };
    boosting = true;
    const target = Math.min(440, vh - 16);
    panel.style.height = `${target}px`;
    boost.setH = target;
    ui.y = clamp(ui.y - (target - boost.h), 0, Math.max(0, vh - target));
    panel.style.top = `${ui.y}px`;
    later(() => { boosting = false; }, 200);
  }

  function unboostPanel() {
    if (!boost) return;
    const b = boost;
    boost = null;
    if (Math.abs(panel.offsetHeight - b.setH) <= 1) {
      boosting = true;
      panel.style.height = `${b.h}px`;
      ui.y = b.y;
      place();
      later(() => { boosting = false; }, 200);
    }
  }

  // ---- backdrop pointer glow
  panel.addEventListener("pointermove", (e) => {
    if (!backdrop) return;
    const r = panel.getBoundingClientRect();
    backdrop.point(e.clientX - r.left, e.clientY - r.top);
  }, sig);
  panel.addEventListener("pointerleave", () => backdrop?.point(null), sig);

  // ---- panel buttons
  pasteBtn.addEventListener("click", (e) => { ripple(e.clientX, e.clientY); pasteFromClipboard(); }, sig);
  minBtn.addEventListener("click", minimize, sig);
  clearBtn.addEventListener("click", () => {
    if (!items.length) return;
    if (clearArmed) { clearTimeout(clearTimer); clearArmed = false; clearBtnLabel(); doClear(); return; }
    clearArmed = true;
    clearBtnLabel();
    clearTimeout(clearTimer);
    clearTimer = later(() => { clearArmed = false; clearBtnLabel(); }, 2600);
  }, sig);

  // ---- panel / chip dragging
  function movable(handle, thresholdKey, onMove, onTap) {
    let s = null;
    handle.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || e.target.closest("button:not(.jwtf-ps-chip)")) return;
      s = { x: e.clientX, y: e.clientY, moved: false, ox: onMove.origin() };
      handle.setPointerCapture(e.pointerId);
    }, sig);
    handle.addEventListener("pointermove", (e) => {
      if (!s) return;
      const dx = e.clientX - s.x, dy = e.clientY - s.y;
      if (!s.moved && Math.hypot(dx, dy) < thresholdKey) return;
      s.moved = true;
      onMove.apply(s.ox, dx, dy);
    }, sig);
    const end = (e) => {
      if (!s) return;
      const moved = s.moved;
      s = null;
      try { handle.releasePointerCapture(e.pointerId); } catch { /* already released */ }
      if (moved) saveUi(ui); else if (onTap && e.type === "pointerup") onTap();
    };
    handle.addEventListener("pointerup", end, sig);
    handle.addEventListener("pointercancel", end, sig);
  }

  movable(head, PANEL_DRAG_THRESHOLD, {
    origin: () => [ui.x, ui.y],
    apply: ([x, y], dx, dy) => { ui.x = x + dx; ui.y = y + dy; place(); },
  });
  movable(chip, PANEL_DRAG_THRESHOLD, {
    origin: () => [ui.cx, ui.cy],
    apply: ([x, y], dx, dy) => { ui.cx = x + dx; ui.cy = y + dy; place(); },
  }, expand);
  chip.addEventListener("click", (e) => { if (e.detail === 0) expand(); }, sig);

  // ---- resize persistence
  if (typeof ResizeObserver !== "undefined") {
    const ro = new ResizeObserver(() => {
      if (ui.state !== "open" || !enabled || boosting || boost) return;
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        const w = panel.offsetWidth, h = panel.offsetHeight;
        if (!w || !h) return;
        ui.w = w;
        ui.h = h;
        place();
        saveUi(ui);
      }, 150);
    });
    ro.observe(panel);
    cleanups.push(() => ro.disconnect());
  }
  window.addEventListener("resize", () => place(), sig);

  // ---- hover tracking and paste / drop
  for (const n of [panel, chip]) {
    n.addEventListener("pointerenter", () => { hovering = true; }, sig);
    n.addEventListener("pointerleave", () => { hovering = false; }, sig);
  }

  const isTextEntry = (n) => !!n && n.nodeType === 1 && (n.matches("input, textarea, select") || n.isContentEditable);

  window.addEventListener("paste", async (e) => {
    if (!enabled || root.hidden) return;
    const active = document.activeElement;
    if (isTextEntry(active) || isTextEntry(e.target)) return;
    if (!(hovering || root.contains(active))) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const r = panel.getBoundingClientRect();
    ripple(r.left + r.width / 2, r.top + r.height / 2);
    const data = e.clipboardData;
    if (!data) return;
    let files = Array.from(data.files || []);
    if (!files.length) files = Array.from(data.items || []).filter((i) => i.kind === "file").map((i) => i.getAsFile()).filter(Boolean);
    if (files.length) { report(await addFiles(files)); return; }
    report([await addText(data.getData("text/plain"))]);
  }, { signal: ac.signal, capture: true });

  panel.addEventListener("dragenter", (e) => { e.preventDefault(); dragDepth++; root.classList.add("drag-over"); }, sig);
  panel.addEventListener("dragover", (e) => { e.preventDefault(); e.stopPropagation(); }, sig);
  panel.addEventListener("dragleave", () => { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) root.classList.remove("drag-over"); }, sig);
  panel.addEventListener("drop", async (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepth = 0;
    root.classList.remove("drag-over");
    ripple(e.clientX, e.clientY);
    const files = Array.from(e.dataTransfer?.files || []);
    if (files.length) report(await addFiles(files));
    else report([await addText(e.dataTransfer?.getData("text/plain") || "")]);
  }, sig);

  // ---- card drag: reorder or drop on a Load Image node
  function nodeUnderPointer(x, y) {
    return imageNodeAtPoint(app.canvas, app.graph, x, y);
  }

  function showOutline(node) {
    if (!node) { outline.hidden = true; return; }
    const canvas = app.canvas.canvas;
    const rect = canvas.getBoundingClientRect();
    const ds = app.canvas.ds;
    const titleH = (globalThis.LiteGraph && globalThis.LiteGraph.NODE_TITLE_HEIGHT) || 30;
    const pad = 3;
    outline.style.left = `${rect.left + (node.pos[0] + ds.offset[0]) * ds.scale - pad}px`;
    outline.style.top = `${rect.top + (node.pos[1] - titleH + ds.offset[1]) * ds.scale - pad}px`;
    outline.style.width = `${node.size[0] * ds.scale + pad * 2}px`;
    outline.style.height = `${(node.size[1] + titleH) * ds.scale + pad * 2}px`;
    outline.hidden = false;
  }

  function cardAt(card, it) { return { card, it }; }

  list.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || (e.pointerType !== "mouse" && e.pointerType !== "pen")) return;
    const card = e.target.closest(".jwtf-ps-card");
    if (!card || e.target.closest(".jwtf-ps-del, .jwtf-ps-editor, .jwtf-ps-btn") || card.classList.contains("editing")) return;
    drag = { ...cardAt(card, card._item), id: e.pointerId, x: e.clientX, y: e.clientY, active: false, ghost: null, node: null, slot: -1, px: e.clientX, py: e.clientY, scrollTimer: 0 };
    card.setPointerCapture(e.pointerId);
  }, sig);

  list.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    drag.px = e.clientX;
    drag.py = e.clientY;
    if (!drag.active) {
      if (Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < DRAG_THRESHOLD) return;
      activateDrag();
    }
    updateDrag();
  }, sig);

  list.addEventListener("pointerup", (e) => { if (drag && e.pointerId === drag.id) finishDrag(e); }, sig);
  list.addEventListener("pointercancel", () => cancelDrag(), sig);

  function activateDrag() {
    const d = drag;
    d.active = true;
    d.card.classList.add("dragging");
    const ghost = el("div", "jwtf-ps-ghost");
    if (d.it.kind === "image") {
      const url = URL.createObjectURL(d.it.blob);
      urls.add(url);
      ghost.classList.add("img");
      ghost.append(el("img", "", { src: url, alt: "" }));
    } else {
      ghost.textContent = d.it.kind === "text" ? d.it.text.slice(0, 160) : d.it.name || "file";
    }
    root.append(ghost);
    d.ghost = ghost;
    document.body.style.cursor = "grabbing";
    window.addEventListener("keydown", onDragKey, { capture: true, signal: ac.signal });
    d.scrollTimer = setInterval(() => {
      if (!d.reorder) return;
      const r = list.getBoundingClientRect();
      if (d.py < r.top + 30) list.scrollTop -= 12;
      else if (d.py > r.bottom - 30) list.scrollTop += 12;
    }, 30);
  }

  function inPanel(x, y) {
    const r = panel.getBoundingClientRect();
    return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
  }

  function slotFor(y) {
    const others = [...list.children].filter((c) => c !== drag.card);
    for (let i = 0; i < others.length; i++) {
      const r = others[i].getBoundingClientRect();
      if (y < r.top + r.height / 2) return { index: i, others };
    }
    return { index: others.length, others };
  }

  function updateDrag() {
    const d = drag;
    d.ghost.style.left = `${d.px + 14}px`;
    d.ghost.style.top = `${d.py + 14}px`;
    d.reorder = inPanel(d.px, d.py);
    if (d.reorder) {
      d.node = null;
      outline.hidden = true;
      d.ghost.classList.remove("hit");
      const { index, others } = slotFor(d.py);
      d.slot = index;
      const lr = list.getBoundingClientRect();
      let y;
      if (!others.length) y = lr.top;
      else if (index < others.length) y = others[index].getBoundingClientRect().top - 2;
      else y = others[others.length - 1].getBoundingClientRect().bottom + 2;
      bar.style.left = `${lr.left + 4}px`;
      bar.style.width = `${lr.width - 8}px`;
      bar.style.top = `${clamp(y, lr.top, lr.bottom)}px`;
      bar.hidden = false;
    } else {
      bar.hidden = true;
      d.node = d.it.kind === "image" ? nodeUnderPointer(d.px, d.py) : null;
      showOutline(d.node);
      d.ghost.classList.toggle("hit", !!d.node);
    }
  }

  function teardownDrag() {
    const d = drag;
    drag = null;
    if (!d) return;
    clearInterval(d.scrollTimer);
    d.ghost?.remove();
    d.card.classList.remove("dragging");
    try { d.card.releasePointerCapture(d.id); } catch { /* released */ }
    bar.hidden = true;
    outline.hidden = true;
    document.body.style.cursor = "";
    window.removeEventListener("keydown", onDragKey, { capture: true });
  }

  function cancelDrag() {
    if (!drag) return;
    if (drag.active) suppressClickUntil = performance.now() + 60;
    teardownDrag();
  }

  function onDragKey(e) {
    if (e.key !== "Escape") return;
    e.preventDefault();
    e.stopPropagation();
    cancelDrag();
  }

  function finishDrag(e) {
    const d = drag;
    if (!d.active) { teardownDrag(); return; }
    d.px = e.clientX;
    d.py = e.clientY;
    updateDrag();
    suppressClickUntil = performance.now() + 60;
    const { it, node, reorder, slot } = d;
    teardownDrag();
    if (reorder) {
      const from = items.indexOf(it);
      if (from >= 0 && slot >= 0) moveItem(from, slot);
    } else if (node) uploadToNode(it, node);
    else if (it.kind === "image") say("Drop it on a Load Image node to use it, or inside the stack to reorder.", 3600);
  }

  async function uploadToNode(it, node) {
    try {
      const name = safeUploadName(it.name, it.id, it.blob.type || it.mime);
      const form = new FormData();
      form.append("image", new File([it.blob], name, { type: it.blob.type || "image/png" }));
      form.append("type", "input");
      form.append("overwrite", "false");
      const res = await api.fetchApi("/upload/image", { method: "POST", body: form });
      if (!res.ok) throw new Error(`upload failed (${res.status})`);
      const value = widgetValueFrom(await res.json());
      const w = node.widgets.find((x) => x.name === "image");
      const old = w.value;
      const values = w.options && w.options.values;
      if (Array.isArray(values) && !values.includes(value)) values.push(value);
      w.value = value;
      try { w.callback?.(value, app.canvas, node); } catch { /* best-effort preview refresh */ }
      try { node.onWidgetChanged?.(w.name, value, old, w); } catch { /* best effort */ }
      try { (node.graph ?? app.canvas?.graph ?? app.graph)?.change?.(); } catch { /* best effort */ }
      app.canvas?.setDirty?.(true, true);
      say(`Loaded into ${node.title || node.type}.`);
    } catch (err) {
      say(`Couldn't load it: ${err && err.message ? err.message : err}`, 4200);
    }
  }

  // ---- ages
  const ageTimer = setInterval(() => { if (enabled && ui.state === "open") refreshAges(); }, 30000);
  cleanups.push(() => clearInterval(ageTimer));

  // ---- load
  try {
    db = await openDb();
    const records = await txDone(db, "readonly", (s) => s.getAll());
    const { items: sorted, changed } = normalizeOrder(records || []);
    items = sorted;
    if (changed.length) await dbPutAll(changed);
  } catch {
    dbBroken = true;
    items = [];
  }
  applyState();
  renderAll();
  await enqueue(async () => { await evict(); renderAll(); });

  function destroy() {
    ac.abort();
    backdrop?.dispose();
    teardownDrag();
    for (const id of timers) clearTimeout(id);
    timers.clear();
    clearTimeout(toastTimer);
    clearTimeout(resizeTimer);
    clearTimeout(clearTimer);
    clearTimeout(copyPending);
    for (const fn of cleanups) fn();
    revokeUrls();
    try { db?.close(); } catch { /* ignore */ }
    root.remove();
    window[GUARD] = false;
  }

  return { setEnabled, setLimit, setBackdrop, destroy };
}
