// Image RefMod Bake / Apply (Qwen 2.1, Fibo 2, Flux 3): one DOM panel with an accent strip,
// reference cards, token meter, connect chips and data-driven widget hiding from /jezzwtf/refmod_lib.
// The strip uses plain <img> thumbnails (the WebGPU shader strip is not rebuilt).
import { app } from "../../../scripts/app.js";
import { api, chain, clamp, fetchJson, findWidget, h, injectCss, onWidget, setWidgetVisible } from "./_shared.js";

const KINDS = { JWTFUnifiedRefModBake: "bake", JWTFUnifiedRefModApply: "apply" };
const TOKEN_CAP = 16384;
const POLL_MS = 15000;
const OPTIONAL_APPLY = ["extra_image_scale", "ref_strength", "ref_on_negative", "frame_idx", "strength"];
const AUTO = "auto (from refmod)";

injectCss("jezzwtf-unified-panel", `
.jzup{box-sizing:border-box;width:100%;display:flex;flex-direction:column;gap:6px;padding:6px;font:12px system-ui,sans-serif;color:#dfe2ea;
 background:#16181d;border:1px solid #2c2f37;border-radius:8px}
.jzup .strip{position:relative;height:84px;border-radius:6px;overflow:hidden;display:flex;align-items:center;gap:8px;padding:0 10px;
 background:linear-gradient(120deg,#0e0f13,var(--acc,#22d3ee)33,#0e0f13)}
.jzup .strip img{height:64px;max-width:90px;object-fit:cover;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,.6);outline:1px solid var(--acc,#22d3ee)}
.jzup .badge{position:absolute;right:8px;top:6px;font:bold 10px system-ui,sans-serif;color:#10131a;background:var(--acc,#22d3ee);border-radius:8px;padding:1px 8px}
.jzup .card{display:flex;gap:8px;align-items:center;padding:5px;border:1px solid #2c2f37;border-radius:8px;background:#1b1d23}
.jzup .card img{width:44px;height:44px;object-fit:cover;border-radius:6px;flex:none}.jzup .card .ph{width:44px;height:44px;border-radius:6px;background:#2a2c33;flex:none}
.jzup .card .t{flex:1;min-width:0}.jzup .card .n{font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.jzup .card .s{font-size:10px;color:#8b8f99}
.jzup .chip{display:inline-block;font:bold 9px system-ui,sans-serif;border-radius:8px;padding:1px 7px;margin-right:4px;background:#2a2c33;color:#dfe2ea;cursor:default}
.jzup .chip.ok{background:#14532d;color:#86efac}.jzup .chip.bad{background:#7f1d1d;color:#fca5a5}.jzup .chip.btn{cursor:pointer}.jzup .chip.on{background:var(--acc,#22d3ee);color:#10131a}
.jzup .meter{height:8px;border-radius:4px;background:#101114;overflow:hidden}.jzup .meter b{display:block;height:100%;background:var(--acc,#22d3ee)}
.jzup .meter.over b{background:#f06a6a}
.jzup .foot{font-size:10px;color:#8b8f99;display:flex;justify-content:space-between}
.jzup .warn{font-size:11px;color:#f0b24a}.jzup .path{font:10px ui-monospace,Consolas,monospace;color:#8b8f99;word-break:break-all}
`);

const lib = { models: [], refmods: [], at: 0, pending: false };
const panels = new Set();

async function refreshLib(force = false) {
    if (lib.pending || (!force && Date.now() - lib.at < POLL_MS)) return;
    lib.pending = true;
    lib.at = Date.now();
    const data = await fetchJson("/jezzwtf/refmod_lib", null);
    lib.pending = false;
    if (!data) return;
    lib.models = data.models ?? [];
    lib.refmods = data.refmods ?? [];
    for (const p of panels) update(p);
}

const handlerOf = (key) => lib.models.find((m) => m.key === key) ?? null;
const refmodOf = (name) => lib.refmods.find((r) => r.name === name) ?? null;
const thumbUrl = (r) => api.apiURL(`/jezzwtf/refmod_lib/thumb?name=${encodeURIComponent(r.name)}&v=${r.stamp}`);
const linked = (node, name) => !!node.inputs?.find((i) => i.name === name && i.link != null);
const wv = (node, name, d) => findWidget(node, name)?.value ?? d;

function chosenRefmods(node) {
    return ["refmod_1", "refmod_2", "refmod_3"].map((k) => wv(node, k, "None")).filter((v) => v && v !== "None");
}

function effectiveHandler(node, kind) {
    const model = wv(node, "model", AUTO);
    if (model !== AUTO) return handlerOf(model);
    if (kind === "apply") {
        const first = chosenRefmods(node).map(refmodOf).find(Boolean);
        return first ? handlerOf(first.model) : null;
    }
    return null;
}

function applyHiding(node, kind, handler) {
    if (kind === "apply") {
        const uses = new Set(handler?.apply_uses ?? []);
        for (const n of OPTIONAL_APPLY) setWidgetVisible(node, findWidget(node, n), uses.has(n));
    } else {
        setWidgetVisible(node, findWidget(node, "scale_mode"), !!handler?.bake_uses?.includes("scale_mode"));
    }
}

function connectChips(node, needs) {
    return h("div", {}, h("span", { style: { color: "#8b8f99", fontSize: "10px", marginRight: "4px" } }, "connect:"),
        needs.map((n) => h("span.chip", { class: `chip ${linked(node, n) ? "ok" : "bad"}` }, `${n} ${linked(node, n) ? "ok" : "missing"}`)));
}

function strip(handler, thumbs) {
    const el = h("div.strip", { style: { "--acc": handler?.accent ?? "#22d3ee" } }, thumbs.slice(0, 3).map((r) => h("img", { src: thumbUrl(r), alt: "" })));
    el.style.setProperty("--acc", handler?.accent ?? "#22d3ee");
    el.append(h("span.badge", {}, handler?.label ?? "auto"));
    return el;
}

function applyBody(node, handler) {
    const names = chosenRefmods(node);
    const items = names.map((n) => ({ name: n, r: refmodOf(n) }));
    const explicit = wv(node, "model", AUTO) !== AUTO;
    const total = items.reduce((a, i) => a + (i.r?.tokens ?? 0), 0);
    const refs = items.reduce((a, i) => a + (i.r?.count ?? 0), 0);
    const models = new Set(items.filter((i) => i.r).map((i) => i.r.model));
    const body = [];
    for (const { name, r } of items) {
        const wrong = explicit && r && r.model !== wv(node, "model", "");
        body.push(h("div.card", {}, r?.thumb ? h("img", { src: thumbUrl(r) }) : h("div.ph"),
            h("div.t", {}, h("div.n", {}, name), h("div.s", {}, r ? `${r.count} refs · ${r.sizes.slice(0, 3).map((s) => `${s[0]}x${s[1]}`).join(", ")}` : "not found")),
            r && h("span.chip", {}, handlerOf(r.model)?.label ?? r.model), wrong && h("span.chip.bad", {}, "wrong model")));
    }
    const cap = TOKEN_CAP;
    body.push(h("div.meter", { class: total > cap ? "meter over" : "meter" }, h("b", { style: { width: `${clamp(100 * total / cap, 0, 100)}%` } })));
    body.push(h("div.foot", {}, h("span", {}, `${total} reference tokens / step`), h("span", {}, handler ? `max ${handler.max_refs} refs` : "")));
    if (handler && refs > handler.max_refs) body.push(h("div.warn", {}, `too many references: ${refs} > ${handler.max_refs}`));
    if (!explicit && models.size > 1) body.push(h("div.warn", {}, "mixed models: pick refmods that were baked for one model"));
    if (explicit && items.some((i) => i.r && i.r.model !== wv(node, "model", ""))) body.push(h("div.warn", {}, "a chosen refmod belongs to a different model"));
    if (handler) body.push(connectChips(node, handler.apply_needs ?? []));
    return { body, thumbs: items.map((i) => i.r).filter((r) => r?.thumb) };
}

function bakeBody(node, handler) {
    const body = [];
    const chips = h("div", {}, lib.models.map((m) => h("span.chip.btn", {
        class: `chip btn${wv(node, "model", "") === m.key ? " on" : ""}`, onclick: () => {
            const w = findWidget(node, "model");
            if (w) { w.value = m.key; w.callback?.(m.key); }
            update(node._jzUnified);
        },
    }, m.label)));
    body.push(chips);
    const sub = String(wv(node, "subfolder", "") || "").trim() || handler?.subfolder || "";
    const name = String(wv(node, "name", "my_character")).trim();
    const full = sub ? `${sub}/${name}` : name;
    const existing = refmodOf(full);
    if (existing) {
        body.push(h("div.card", {}, existing.thumb ? h("img", { src: thumbUrl(existing) }) : h("div.ph"),
            h("div.t", {}, h("div.n", {}, name), h("div.s", {}, `${existing.count} refs · ${existing.tokens} tokens`)), h("span.chip.ok", {}, "baked")));
        if (!wv(node, "overwrite", false)) body.push(h("div.warn", {}, "this file exists and will be skipped unless overwrite is on"));
    }
    body.push(h("div.path", {}, `models/refmods/${full}.safetensors`));
    if (handler) body.push(connectChips(node, [...(handler.bake_needs ?? []), "images"]));
    return { body, thumbs: existing?.thumb ? [existing] : [] };
}

function update(panel) {
    if (!panel) return;
    const { node, kind } = panel;
    const handler = effectiveHandler(node, kind);
    applyHiding(node, kind, handler);
    const { body, thumbs } = kind === "apply" ? applyBody(node, handler) : bakeBody(node, handler ?? handlerOf(wv(node, "model", "")));
    panel.root.replaceChildren(strip(handler ?? handlerOf(wv(node, "model", "")), thumbs), ...body);
    panel.root.style.setProperty("--acc", handler?.accent ?? "#22d3ee");
    requestAnimationFrame(() => {
        const hgt = panel.root.scrollHeight;
        if (hgt !== panel.height) { panel.height = hgt; node.setSize([Math.max(node.size[0], 320), node.computeSize([node.size[0], 0])[1]]); node.setDirtyCanvas(true, true); }
    });
    for (const n of chosenRefmods(node)) if (!refmodOf(n)) { refreshLib(false); break; }
}

function setup(node, kind) {
    const root = h("div.jzup");
    root.addEventListener("pointerdown", (e) => e.stopPropagation());
    const panel = { node, kind, root, height: 160 };
    node._jzUnified = panel;
    panels.add(panel);
    const w = node.addDOMWidget("refmod_panel", "jezzwtf_refmod_panel", root, { serialize: false, getMinHeight: () => panel.height });
    w.serialize = false;
    for (const n of ["model", "refmod_1", "refmod_2", "refmod_3", "name", "subfolder", "overwrite"]) onWidget(findWidget(node, n), () => update(panel));
    node.setSize([Math.max(node.size[0], 320), node.size[1]]);
    update(panel);
    refreshLib(true);
}

setInterval(() => { if (panels.size && !document.hidden) refreshLib(true); }, POLL_MS);

app.registerExtension({
    name: "JezzWTF.RefMod.UnifiedPanel",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const kind = KINDS[nodeData.name];
        if (!kind) return;
        const proto = nodeType.prototype;
        chain(proto, "onNodeCreated", function () { setup(this, kind); });
        chain(proto, "onConfigure", function () { update(this._jzUnified); });
        chain(proto, "onConnectionsChange", function () { update(this._jzUnified); });
        chain(proto, "onRemoved", function () { if (this._jzUnified) panels.delete(this._jzUnified); });
        if (kind === "bake") {
            chain(proto, "onExecuted", function () {
                setTimeout(async () => { await refreshLib(true); app.refreshComboInNodes?.(); }, 250);
            });
        }
    },
});
