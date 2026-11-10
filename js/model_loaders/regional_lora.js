// Region editor for JWTFRegionalLoRA: two coloured regions on a canvas -> the hidden `regions` JSON.
import { app } from "../../../scripts/app.js";
import { chain, clamp, findWidget, fitNode, h, hideWidget, injectCss, setWidgetValue } from "./_shared.js";

const NODE = "JWTFRegionalLoRA";
const STAGE_H = 232;
const MIN_SIZE = 0.05;
const COLORS = { a: "#4f8cff", b: "#ff5fa8" };
const PRESETS = [
    ["50/50", [[0, 0, 0.5, 1], [0.5, 0, 0.5, 1]]],
    ["33/67", [[0, 0, 1 / 3, 1], [1 / 3, 0, 2 / 3, 1]]],
    ["67/33", [[0, 0, 2 / 3, 1], [2 / 3, 0, 1 / 3, 1]]],
    ["Top/Bottom", [[0, 0, 1, 0.5], [0, 0.5, 1, 0.5]]],
    ["Reset", [[0, 0, 0.5, 1], [0.5, 0, 0.5, 1]]],
];

injectCss("jwtf-ml-regional", `
.jwtf-rg-stage { position: relative; height: ${STAGE_H}px; border-radius: 6px; background:
  repeating-conic-gradient(#202228 0% 25%, #1a1b20 0% 50%) 0 0 / 20px 20px; border: 1px solid #30333b; overflow: hidden; }
.jwtf-rg-box { position: absolute; display: flex; border: 2px solid; border-radius: 4px; min-width: 24px; min-height: 24px; }
.jwtf-rg-box textarea { flex: 1; width: 100%; height: 100%; border: 0; background: transparent; resize: none; outline: none;
  color: #f1f1f1; font: 11px/1.35 system-ui, sans-serif; padding: 22px 4px 4px; user-select: text; }
.jwtf-rg-badge { position: absolute; left: -1px; top: -1px; padding: 1px 7px; font: 700 10px system-ui, sans-serif; color: #fff;
  border-radius: 3px 0 4px 0; cursor: move; touch-action: none; z-index: 1; }
.jwtf-rg-size { position: absolute; right: 0; bottom: 0; width: 12px; height: 12px; cursor: nwse-resize; touch-action: none; z-index: 1; }
.jwtf-rg-foot { font-size: 11px; color: #8b8f99; display: flex; gap: 10px; flex-wrap: wrap; }
.jwtf-rg-foot .warn { color: #fbbf24; }
`);

const finite = (v, d) => (Number.isFinite(Number(v)) ? Number(v) : d);
const defaults = () => [
    { char: "a", x: 0, y: 0, w: 0.5, h: 1, text: "" },
    { char: "b", x: 0.5, y: 0, w: 0.5, h: 1, text: "" },
];

function parse(raw) {
    let data;
    try { data = JSON.parse(raw || "{}"); } catch { data = {}; }
    const list = Array.isArray(data) ? data : Array.isArray(data?.regions) ? data.regions : [];
    const glob = !Array.isArray(data) && typeof data?.global === "string" ? data.global : "";
    const out = defaults();
    list.slice(0, 2).forEach((r, i) => {
        out[i] = {
            char: i === 0 ? "a" : "b",
            x: clamp(finite(r?.x, out[i].x), 0, 1), y: clamp(finite(r?.y, out[i].y), 0, 1),
            w: clamp(finite(r?.w, out[i].w), MIN_SIZE, 1), h: clamp(finite(r?.h, out[i].h), MIN_SIZE, 1),
            text: typeof r?.text === "string" ? r.text : "",
        };
        out[i].x = Math.min(out[i].x, 1 - out[i].w);
        out[i].y = Math.min(out[i].y, 1 - out[i].h);
    });
    return { regions: out, glob };
}

// Intersection / union areas of the two boxes, as fractions of the unit square.
function areas(a, b) {
    const ox = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
    const oy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
    const overlap = ox * oy;
    const aa = a.w * a.h;
    const bb = b.w * b.h;
    return { a: aa, b: bb, overlap, gap: Math.max(0, 1 - (aa + bb - overlap)) };
}

function setupRegional(node) {
    const regionsW = findWidget(node, "regions");
    const featherW = findWidget(node, "feather");
    const hideNative = () => { hideWidget(regionsW); hideWidget(featherW); };
    hideNative();

    // Scrub stale non-numeric values left by older workflows.
    const scrub = () => {
        const bad = (v) => typeof v === "string" && !Number.isFinite(Number(v));
        for (const [name, d] of [["feather", 0.06], ["strength_a", 1], ["strength_b", 1]]) {
            const w = findWidget(node, name);
            if (w && bad(w.value)) w.value = d;
        }
        if (featherW) featherW.value = clamp(finite(featherW.value, 0.06), 0, 0.3);
    };
    scrub();

    let { regions, glob } = parse(regionsW?.value);
    let lastWritten = null;
    const boxes = [];

    const stage = h("div.jwtf-rg-stage");
    const presetRow = h("div.jwtf-ml-row.jwtf-ml-wrap", {}, ...PRESETS.map(([label, rects]) => h("button.jwtf-ml-btn", {
        onclick: () => {
            rects.forEach(([x, y, w, hh], i) => Object.assign(regions[i], { x, y, w, h: hh }));
            commit(true);
        },
    }, label)));
    const featherIn = h("input.jwtf-ml-input", { type: "number", min: "0", max: "0.3", step: "0.01", style: { width: "64px" } });
    const globalTa = h("textarea.jwtf-ml-ta", { rows: 2, placeholder: "Global prompt (shared by both regions)", spellcheck: false });
    const foot = h("div.jwtf-rg-foot");
    const root = h("div.jwtf-ml", { style: { userSelect: "none" } },
        stage, presetRow,
        h("div.jwtf-ml-row", {}, h("span.jwtf-ml-muted", {}, "Feather"), featherIn), globalTa, foot);

    function write() {
        const json = JSON.stringify({ regions: regions.map((r) => ({
            char: r.char, x: +r.x.toFixed(4), y: +r.y.toFixed(4), w: +r.w.toFixed(4), h: +r.h.toFixed(4), text: r.text,
        })), global: glob });
        lastWritten = json;
        if (regionsW) regionsW.value = json;
        node.setDirtyCanvas(true, true);
    }
    function commit(layout) {
        write();
        if (layout) place();
        readout();
    }

    function place() {
        boxes.forEach((b, i) => {
            const r = regions[i];
            Object.assign(b.el.style, {
                left: `${r.x * 100}%`, top: `${r.y * 100}%`, width: `${r.w * 100}%`, height: `${r.h * 100}%`,
            });
            b.badge.textContent = `${r.char.toUpperCase()}  ${r.text.length}`;
        });
    }

    function readout() {
        const a = areas(regions[0], regions[1]);
        const pct = (v) => `${(v * 100).toFixed(1)}%`;
        foot.replaceChildren(h("span", {}, `A ${pct(a.a)}`), h("span", {}, `B ${pct(a.b)}`),
            h("span", { className: a.overlap > 0.002 ? "warn" : "" }, `Overlap ${pct(a.overlap)}`),
            h("span", { className: a.gap > 0.002 ? "warn" : "" }, `Gap ${pct(a.gap)}`));
    }

    function drag(ev, i, mode) {
        ev.preventDefault();
        ev.stopPropagation();
        const rect = stage.getBoundingClientRect();
        const r = regions[i];
        const start = { x: ev.clientX, y: ev.clientY, rx: r.x, ry: r.y, rw: r.w, rh: r.h };
        const target = ev.currentTarget;
        target.setPointerCapture(ev.pointerId);
        const move = (e) => {
            const dx = (e.clientX - start.x) / rect.width;
            const dy = (e.clientY - start.y) / rect.height;
            if (mode === "move") {
                r.x = clamp(start.rx + dx, 0, 1 - r.w);
                r.y = clamp(start.ry + dy, 0, 1 - r.h);
            } else {
                r.w = clamp(start.rw + dx, MIN_SIZE, 1 - r.x);
                r.h = clamp(start.rh + dy, MIN_SIZE, 1 - r.y);
            }
            commit(true);
        };
        const up = () => {
            target.removeEventListener("pointermove", move);
            target.removeEventListener("pointerup", up);
            target.removeEventListener("pointercancel", up);
        };
        target.addEventListener("pointermove", move);
        target.addEventListener("pointerup", up);
        target.addEventListener("pointercancel", up);
    }

    regions.forEach((r, i) => {
        const color = COLORS[r.char];
        const ta = h("textarea", { placeholder: `Prompt for ${r.char.toUpperCase()}`, spellcheck: false, value: r.text });
        const badge = h("div.jwtf-rg-badge", { style: { background: color } });
        const size = h("div.jwtf-rg-size", { style: { background: `linear-gradient(135deg, transparent 50%, ${color} 50%)` } });
        const el = h("div.jwtf-rg-box", { style: { borderColor: color, background: `${color}26` } }, badge, ta, size);
        badge.addEventListener("pointerdown", (e) => drag(e, i, "move"));
        size.addEventListener("pointerdown", (e) => drag(e, i, "size"));
        ta.addEventListener("input", () => { regions[i].text = ta.value; commit(true); });
        ta.addEventListener("keydown", (e) => e.stopPropagation());
        stage.append(el);
        boxes.push({ el, badge, ta });
    });

    featherIn.addEventListener("change", () => {
        const v = clamp(finite(featherIn.value, 0.06), 0, 0.3);
        featherIn.value = String(v);
        setWidgetValue(featherW, v);
    });
    featherIn.addEventListener("keydown", (e) => e.stopPropagation());
    globalTa.addEventListener("input", () => { glob = globalTa.value; commit(false); });
    globalTa.addEventListener("keydown", (e) => e.stopPropagation());

    function reload() {
        hideNative();
        scrub();
        const raw = String(regionsW?.value ?? "");
        if (raw !== lastWritten) ({ regions, glob } = parse(raw));
        boxes.forEach((b, i) => { b.ta.value = regions[i].text; });
        globalTa.value = glob;
        featherIn.value = String(featherW?.value ?? 0.06);
        place();
        readout();
        // Normalise whatever was loaded (stale shapes, 1 or 3 regions) into the canonical two-region JSON.
        write();
    }

    const widget = node.addDOMWidget("jwtf_regions", "jwtf_regions", root, {
        serialize: false, getMinHeight: () => STAGE_H + 150, hideOnZoom: false,
    });
    widget.computeSize = (w) => [w, STAGE_H + 150];
    node._jwtfSync = reload;
    reload();
    node.setSize([Math.max(node.size[0], 380), Math.max(node.size[1], 560)]);
    setTimeout(() => fitNode(node, 380), 60);
}

app.registerExtension({
    name: "JezzWTF.ModelLoaders.RegionalLoRA",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE) return;
        chain(nodeType.prototype, "onNodeCreated", function () { setupRegional(this); });
        chain(nodeType.prototype, "onConfigure", function () { setTimeout(() => this._jwtfSync?.(), 0); });
        chain(nodeType.prototype, "onDrawForeground", function () {
            const w = findWidget(this, "regions");
            if (w && !w.hidden) { hideWidget(w); hideWidget(findWidget(this, "feather")); }
        });
    },
});
