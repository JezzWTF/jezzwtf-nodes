// Ultimate Model Loader: every data widget is hidden (and stays serialised) behind one sectioned
// DOM panel: drag-to-reorder sections, editable headings, switches, searchable combos and a
// right-click "convert to input" menu. Headings and order are real widgets (heading_*, section_order).
import { app } from "../../../scripts/app.js";
import { api, chain, findWidget, h, injectCss, sameNode, setWidgetVisible } from "./_shared.js";

const NODE = "JWTFUltimateModelLoader";
const STATUS_EVENT = "jezzwtf.uml_status";
const MIN_W = 280;
const MAX_ITEMS = 300;
const DEFAULT_ORDER = ["model", "engine", "clips", "vaes"];

const SECTIONS = {
    model: { heading: "heading_model", title: "Model", rows: [
        ["model_name", "diffusion model"], ["quant_format", "quantisation"], ["model_type", "model type"]] },
    engine: { heading: "heading_engine", title: "Efficiencies", rows: [
        ["kitchen", "comfy-kitchen INT8"], ["sage2", "SageAttention 2"], ["sage3", "SageAttention 3"],
        ["triton", "Triton backend"], ["flash2", "FlashAttention 2"], ["pytorch", "PyTorch SDPA"],
        ["sparse", "block-sparse attention"], ["vsa", "video sparse attention"]] },
    clips: { heading: "heading_clips", title: "Text Encoders", rows: [
        ["clip1_name", "main encoder"], ["clip1_type", "type"], ["clip1_device", "device"],
        ["clip2_enabled", "second encoder"], ["clip2_name", "enhancer encoder"], ["clip2_type", "type"],
        ["clip2_device", "device"]] },
    vaes: { heading: "heading_vaes", title: "VAEs", rows: [
        ["vae_name", "video / default VAE"], ["audio_vae_enabled", "audio VAE"], ["audio_vae_name", "audio VAE file"]] },
};
const DATA_WIDGETS = [...Object.values(SECTIONS).flatMap((s) => [s.heading, ...s.rows.map((r) => r[0])]), "section_order"];

injectCss("jezzwtf-loader-panel", `
.jzlp{box-sizing:border-box;width:100%;display:flex;flex-direction:column;gap:6px;padding:6px;font:12px system-ui,sans-serif;color:#dfe2ea;
 background:#16181d;border:1px solid #2c2f37;border-radius:8px}
.jzlp .status{display:flex;align-items:center;gap:8px;min-height:22px}
.jzlp .status canvas{width:34px;height:16px;border-radius:4px;flex:none}
.jzlp .status span{font-size:11px;color:#9aa1af;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.jzlp .status span.ok{color:#6ee7b7}
.jzlp .sec{border:1px solid #2c2f37;border-radius:6px;background:#1b1d23;position:relative}
.jzlp .sec.drop-up::before,.jzlp .sec.drop-down::after{content:"";position:absolute;left:0;right:0;height:2px;background:#6aa7ff}
.jzlp .sec.drop-up::before{top:-4px}.jzlp .sec.drop-down::after{bottom:-4px}
.jzlp .sec.dragging{opacity:.5}
.jzlp .hd{display:flex;align-items:center;gap:6px;padding:4px 6px}
.jzlp .grip{cursor:grab;color:#6d7280;user-select:none;touch-action:none}
.jzlp .hd input{flex:1;min-width:0;background:transparent;border:1px solid transparent;border-radius:4px;color:#e8eaf0;font:bold 11px system-ui,sans-serif;
 letter-spacing:.05em;text-transform:uppercase;padding:1px 4px}
.jzlp .hd input:hover,.jzlp .hd input:focus{border-color:#3a3d46;outline:none;background:#121317}
.jzlp .chev{cursor:pointer;color:#9aa1af;width:16px;text-align:center;user-select:none}
.jzlp .body{display:grid;gap:4px;padding:2px 8px 8px}.jzlp .sec.closed .body{display:none}
.jzlp .row{display:grid;grid-template-columns:42% 1fr;align-items:center;gap:6px}
.jzlp .row.wired{opacity:.5}
.jzlp .row label{color:#9aa1af;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.jzlp .row input[type=text]{width:100%;box-sizing:border-box;background:#121317;border:1px solid #30333b;border-radius:5px;color:#e6e6e6;padding:3px 6px;font:inherit}
.jzlp .row input[type=text]:focus{outline:none;border-color:#5672b4}
.jzlp .sw{width:30px;height:16px;border-radius:8px;background:#30333b;position:relative;cursor:pointer;justify-self:start;transition:background .15s}
.jzlp .sw::after{content:"";position:absolute;top:2px;left:2px;width:12px;height:12px;border-radius:6px;background:#dfe2ea;transition:left .15s}
.jzlp .sw.on{background:#3c6fe0}.jzlp .sw.on::after{left:16px}
.jzlp-dd{position:fixed;z-index:10000;max-height:240px;overflow:auto;background:#20232b;border:1px solid #444a58;border-radius:6px;font:12px system-ui,sans-serif;color:#dfe2ea;
 box-shadow:0 8px 24px rgba(0,0,0,.5)}
.jzlp-dd div{padding:3px 8px;cursor:pointer;white-space:nowrap}.jzlp-dd div.act,.jzlp-dd div:hover{background:#3c4f7a}.jzlp-dd .more{color:#8b8f99;cursor:default}
`);

// --------------------------------------------------------------------------- helpers

const orderOf = (node) => {
    const seen = [];
    for (const k of String(findWidget(node, "section_order")?.value ?? "").split(",").map((s) => s.trim())) {
        if (SECTIONS[k] && !seen.includes(k)) seen.push(k);
    }
    return [...seen, ...DEFAULT_ORDER.filter((k) => !seen.includes(k))];
};

function setValue(node, name, v) {
    const w = findWidget(node, name);
    if (!w) return;
    w.value = v;
    w.callback?.(v);
    node.graph?.setDirtyCanvas?.(true, true);
}

const wiredInput = (node, name) => node.inputs?.find((i) => i.name === name) ?? null;
const isWired = (node, name) => wiredInput(node, name)?.link != null;

function promote(node, name) {
    const w = findWidget(node, name);
    if (!w || wiredInput(node, name)) return;
    const type = w.type === "toggle" || typeof w.value === "boolean" ? "BOOLEAN" : w.type === "combo" ? "COMBO" : "STRING";
    try { node.addInput(name, type, { widget: { name } }); } catch (e) { console.warn("[jezzwtf] could not add input", name, e); }
    node.setDirtyCanvas(true, true);
}

// --------------------------------------------------------------------------- combo with a body-appended dropdown

let openDropdown = null;
function closeDropdown() {
    if (!openDropdown) return;
    openDropdown.el.remove();
    for (const [t, fn] of openDropdown.listeners) window.removeEventListener(t, fn, true);
    openDropdown = null;
}

function comboRow(node, name, label, panel) {
    const input = h("input", { type: "text", spellcheck: false, autocomplete: "off" });
    const values = () => (findWidget(node, name)?.options?.values ?? []).map(String);
    let typing = false, active = 0, shown = [];
    const commit = (v) => { setValue(node, name, v); input.value = v; closeDropdown(); typing = false; input.blur(); };
    const render = () => {
        closeDropdown();
        const q = input.value.trim().toLowerCase();
        const all = values();
        shown = (typing && q ? all.filter((v) => v.toLowerCase().includes(q)) : all);
        const list = shown.slice(0, MAX_ITEMS);
        active = Math.min(active, Math.max(0, list.length - 1));
        const el = h("div.jzlp-dd", {}, list.map((v, i) => h("div", {
            class: i === active ? "act" : "", onpointerdown: (e) => { e.preventDefault(); commit(v); },
        }, v)));
        if (shown.length > MAX_ITEMS) el.append(h("div.more", {}, `${shown.length - MAX_ITEMS} more...`));
        const r = input.getBoundingClientRect();
        Object.assign(el.style, { left: `${r.left}px`, top: `${r.bottom + 2}px`, minWidth: `${r.width}px` });
        document.body.append(el);
        const outside = (e) => { if (!el.contains(e.target) && e.target !== input) closeDropdown(); };
        const listeners = [["pointerdown", outside], ["wheel", (e) => { if (!el.contains(e.target)) closeDropdown(); }], ["blur", closeDropdown]];
        for (const [t, fn] of listeners) window.addEventListener(t, fn, true);
        openDropdown = { el, listeners };
    };
    input.addEventListener("focus", () => { typing = false; input.select(); render(); });
    input.addEventListener("input", () => { typing = true; active = 0; render(); });
    input.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); active = Math.max(0, Math.min(shown.length - 1, active + (e.key === "ArrowDown" ? 1 : -1))); render(); }
        else if (e.key === "Enter") { e.preventDefault(); if (shown[active] != null) commit(shown[active]); }
        else if (e.key === "Escape") { closeDropdown(); input.value = String(findWidget(node, name)?.value ?? ""); input.blur(); }
    });
    input.addEventListener("blur", () => {
        setTimeout(() => {
            const cur = String(findWidget(node, name)?.value ?? "");
            const typed = input.value.trim();
            if (typed !== cur && values().includes(typed)) setValue(node, name, typed); // exact match commits
            input.value = String(findWidget(node, name)?.value ?? "");
            typing = false;
        }, 0);
    });
    return {
        name, el: h("div.row", { dataset: { name } }, h("label", { title: name }, label), input),
        sync() { if (document.activeElement !== input) input.value = String(findWidget(node, name)?.value ?? ""); input.disabled = isWired(node, name); },
    };
}

function switchRow(node, name, label) {
    const sw = h("div.sw", { onclick: () => { if (!isWired(node, name)) setValue(node, name, !findWidget(node, name)?.value); } });
    return {
        name, el: h("div.row", { dataset: { name } }, h("label", { title: name }, label), sw),
        sync() { sw.classList.toggle("on", !!findWidget(node, name)?.value); },
    };
}

// --------------------------------------------------------------------------- panel

function buildPanel(node) {
    const root = h("div.jzlp");
    const statusText = h("span", {}, "not loaded yet");
    const canvas = h("canvas", { width: 68, height: 32 });
    const panel = { node, root, statusText, canvas, rows: [], closed: new Set(), loading: false, tick: 0 };
    root.addEventListener("pointerdown", (e) => e.stopPropagation());
    root.addEventListener("mousedown", (e) => e.stopPropagation());
    root.addEventListener("wheel", (e) => e.stopPropagation(), { passive: true });
    root.addEventListener("contextmenu", (e) => {
        const row = e.target.closest?.(".row");
        if (!row) return;
        e.preventDefault();
        e.stopPropagation();
        const name = row.dataset.name;
        const items = DATA_WIDGETS.includes(name) && !name.startsWith("heading") && name !== "section_order"
            ? [{ content: wiredInput(node, name) ? "Already an input" : "Convert to input", disabled: !!wiredInput(node, name), callback: () => { promote(node, name); render(panel); } }]
            : [];
        if (items.length) new globalThis.LiteGraph.ContextMenu(items, { event: e });
    });
    return panel;
}

function render(panel) {
    const { node, root } = panel;
    root.replaceChildren();
    panel.rows = [];
    panel.lastOrder = orderOf(node).join(",");
    root.append(h("div.status", {}, panel.canvas, panel.statusText));
    for (const key of orderOf(node)) root.append(sectionEl(panel, key));
    measure(panel);
}

function sectionEl(panel, key) {
    const { node } = panel;
    const def = SECTIONS[key];
    const body = h("div.body");
    for (const [name, label] of def.rows) {
        const w = findWidget(node, name);
        if (!w) continue;
        const row = w.type === "toggle" || typeof w.value === "boolean" ? switchRow(node, name, label) : comboRow(node, name, label, panel);
        panel.rows.push(row);
        row.sync();
        body.append(row.el);
    }
    const heading = h("input", { type: "text", value: String(findWidget(node, def.heading)?.value || def.title), spellcheck: false });
    heading.addEventListener("change", () => setValue(node, def.heading, heading.value.trim() || def.title));
    heading.addEventListener("keydown", (e) => { if (e.key === "Enter") heading.blur(); e.stopPropagation(); });
    const chev = h("span.chev", {}, panel.closed.has(key) ? "▸" : "▾");
    const grip = h("span.grip", { title: "drag to reorder" }, "⋮⋮");
    const sec = h("div.sec", { class: panel.closed.has(key) ? "sec closed" : "sec", dataset: { key } }, h("div.hd", {}, grip, heading, chev), body);
    chev.addEventListener("click", () => { if (panel.closed.has(key)) panel.closed.delete(key); else panel.closed.add(key); render(panel); });
    grip.addEventListener("pointerdown", (e) => startDrag(panel, key, sec, e));
    return sec;
}

function startDrag(panel, key, secEl, ev) {
    ev.preventDefault();
    ev.stopPropagation();
    secEl.classList.add("dragging");
    let target = null, after = false;
    const secs = () => [...panel.root.querySelectorAll(".sec")];
    const move = (e) => {
        secs().forEach((s) => s.classList.remove("drop-up", "drop-down"));
        target = null;
        for (const s of secs()) {
            if (s === secEl) continue;
            const r = s.getBoundingClientRect();
            if (e.clientY >= r.top && e.clientY <= r.bottom) {
                target = s.dataset.key;
                after = e.clientY > r.top + r.height / 2;
                s.classList.add(after ? "drop-down" : "drop-up");
            }
        }
    };
    const up = () => {
        window.removeEventListener("pointermove", move, true);
        window.removeEventListener("pointerup", up, true);
        if (target) {
            const order = orderOf(panel.node).filter((k) => k !== key);
            order.splice(order.indexOf(target) + (after ? 1 : 0), 0, key);
            setValue(panel.node, "section_order", order.join(","));
        }
        render(panel);
    };
    window.addEventListener("pointermove", move, true);
    window.addEventListener("pointerup", up, true);
}

function measure(panel) {
    const { node, root } = panel;
    requestAnimationFrame(() => {
        const hgt = root.scrollHeight;
        if (hgt > 0 && hgt !== panel.height) {
            panel.height = hgt;
            node.setSize([Math.max(node.size[0], MIN_W), node.computeSize([node.size[0], 0])[1]]);
            node.setDirtyCanvas(true, true);
        }
    });
}

function paintStatus(panel) {
    const c = panel.canvas, ctx = c.getContext("2d");
    const t = (panel.tick += panel.loading ? 0.08 : 0.02);
    const g = ctx.createLinearGradient(0, 0, c.width, 0);
    const a = 0.5 + 0.5 * Math.sin(t);
    g.addColorStop(0, panel.ok ? `rgba(110,231,183,${0.4 + a * 0.5})` : `rgba(106,167,255,${0.3 + a * 0.5})`);
    g.addColorStop(1, panel.loading ? `rgba(250,204,21,${0.4 + a * 0.5})` : "rgba(60,79,122,.6)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, c.width, c.height);
}

function statusLine(d) {
    const quant = d.quant_detected?.length ? d.quant_detected.join("+") : "bf16";
    const bits = [`loaded ✓ ${d.model} — ${quant}`, `attn:${d.backend ?? "default"}`];
    if (d.sparse) bits.push("sparse");
    if (d.vsa) bits.push("vsa");
    if (d.clip2) bits.push("2×clip");
    if (d.audio_vae) bits.push("audio-vae");
    return bits.join(" · ");
}

const panels = new Set();

// Repaint the status strip once per state change; animate only while a panel is loading and the tab is visible.
let raf = 0;
function frame() {
    raf = 0;
    let busy = false;
    for (const p of panels) if (p.root.isConnected) { paintStatus(p); busy = busy || p.loading; }
    if (busy && !document.hidden) raf = requestAnimationFrame(frame);
}
function kick() { if (!raf) raf = requestAnimationFrame(frame); }

function findNodeById(id) {
    for (const g of [app.canvas?.graph, app.graph, app.rootGraph]) {
        for (const n of g?._nodes ?? []) if (n.comfyClass === NODE && sameNode(n.id, id)) return n;
    }
    return null;
}

app.registerExtension({
    name: "JezzWTF.RefMod.LoaderPanel",
    setup() {
        api.addEventListener(STATUS_EVENT, (e) => {
            const n = findNodeById(e.detail?.node);
            if (!n?._jzLoader) return;
            const p = n._jzLoader;
            p.ok = true; p.loading = false;
            p.statusText.textContent = statusLine(e.detail);
            p.statusText.className = "ok";
            kick();
        });
        api.addEventListener("executing", (e) => {
            const id = e.detail?.node ?? e.detail;
            for (const p of panels) {
                const was = p.loading;
                p.loading = id != null && sameNode(id, p.node.id);
                if (p.loading) { p.statusText.textContent = "loading..."; p.statusText.className = ""; p.ok = false; }
                else if (was && !p.ok) p.statusText.textContent = "not loaded yet";
            }
            kick();
        });
        document.addEventListener("visibilitychange", () => { if (!document.hidden) kick(); });
        kick();
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE) return;
        const proto = nodeType.prototype;
        chain(proto, "onNodeCreated", function () {
            const panel = buildPanel(this);
            this._jzLoader = panel;
            panels.add(panel);
            for (const name of DATA_WIDGETS) setWidgetVisible(this, findWidget(this, name), false);
            const w = this.addDOMWidget("loader_panel", "jezzwtf_loader_panel", panel.root, {
                serialize: false, getMinHeight: () => panel.height ?? 240,
            });
            w.serialize = false;
            this.setSize([Math.max(MIN_W, this.size[0], 340), this.size[1]]);
            render(panel);
            kick();
        });
        chain(proto, "onConfigure", function () {
            if (this._jzLoader) { for (const name of DATA_WIDGETS) setWidgetVisible(this, findWidget(this, name), false); render(this._jzLoader); }
        });
        chain(proto, "onConnectionsChange", function () { if (this._jzLoader) this._jzLoader.rows.forEach((r) => { r.el.classList.toggle("wired", isWired(this, r.name)); r.sync(); }); });
        chain(proto, "onRemoved", function () { if (this._jzLoader) panels.delete(this._jzLoader); closeDropdown(); });
        // re-sync rows from widget values changed elsewhere (undo, load, other editors)
        chain(proto, "onDrawForeground", function () {
            const p = this._jzLoader;
            if (!p) return;
            for (const r of p.rows) { r.sync(); r.el.classList.toggle("wired", isWired(this, r.name)); }
            const order = orderOf(this).join(",");
            if (order !== p.lastOrder) { p.lastOrder = order; render(p); }
        });
        const computeSize = proto.computeSize;
        proto.computeSize = function () {
            const s = computeSize ? computeSize.apply(this, arguments) : [MIN_W, 120];
            return [Math.max(MIN_W, s[0]), s[1]];
        };
    },
});
