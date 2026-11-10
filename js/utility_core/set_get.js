import { app } from "../../../scripts/app.js";
import { chain, findWidget, getLink, injectCss, onWidget } from "./_shared.js";

// Remote Set / Get: key dropdown, colour sync, floating key badge, and a prompt
// rewrite that wires each Get to its Set so execution order is always right.

const SET = "JWTFSet";
const GET = "JWTFGet";
const PLACEHOLDER = "select a key...";
const LINK_INPUT = "set_link";
const COLORS = {
    Void: "#0a0a0a", Neon: "#00f3ff", Plasma: "#bc13fe", Toxic: "#39ff14", Flare: "#ff5e00",
    Blood: "#ff0000", Quantum: "#0044ff", Gold: "#ffaa00", Abyss: "#ff007f", Ghost: "#e0e0e0",
    Rose: "#ff0055", Matrix: "#00ff41", Nebula: "#4b0082",
};

injectCss("jwtf-setget", `
.jwtf-sg-badge { position: absolute; z-index: 5; pointer-events: none; transform-origin: 0 0; white-space: nowrap;
  font: 700 11px/1 ui-monospace, Consolas, monospace; letter-spacing: .06em; padding: 3px 7px; border-radius: 6px;
  color: #fff; background: #222; border: 1px solid #666; }
`);

function darken(hex, factor) {
    const n = parseInt(hex.slice(1), 16);
    const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => Math.trunc(v * factor));
    return "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");
}

function allNodes() {
    const out = [];
    const seen = new Set();
    const walk = (graph) => {
        if (!graph || seen.has(graph)) return;
        seen.add(graph);
        out.push(...(graph._nodes ?? graph.nodes ?? []));
        const subs = graph.subgraphs;
        if (subs) for (const sg of (typeof subs.values === "function" ? subs.values() : Object.values(subs))) walk(sg);
    };
    walk(app.graph);
    walk(app.canvas?.graph);
    return out;
}

const keyOf = (node) => String(findWidget(node, "key")?.value ?? "");
const setNodes = () => allNodes().filter((n) => n.comfyClass === SET);

function paintLinks(node, color) {
    const g = node.graph;
    for (const inp of node.inputs ?? []) {
        const l = getLink(g, inp.link);
        if (l) l.color = color ?? undefined;
    }
    for (const out of node.outputs ?? []) {
        for (const id of out.links ?? []) {
            const l = getLink(g, id);
            if (l) l.color = color ?? undefined;
        }
    }
}

function applyColor(node, name) {
    const hex = COLORS[name];
    node._jwtfHex = hex ?? null;
    if (hex) {
        node.color = darken(hex, 0.55);
        node.bgcolor = darken(hex, 0.35);
        node.boxcolor = hex;
    } else {
        delete node.color;
        delete node.bgcolor;
        delete node.boxcolor;
    }
    paintLinks(node, hex);
    updateBadgeStyle(node);
    node.setDirtyCanvas?.(true, true);
}

function syncGet(node) {
    const key = keyOf(node);
    const match = setNodes().find((s) => keyOf(s) === key);
    applyColor(node, match ? findWidget(match, "color")?.value : "Default");
}

function recolorGetsFor(key) {
    for (const n of allNodes()) if (n.comfyClass === GET && keyOf(n) === key) syncGet(n);
}

// ---- floating badge ---------------------------------------------------------

const badges = new Set();

function ensureBadge(node) {
    if (node._jwtfBadge) return node._jwtfBadge;
    const el = document.createElement("div");
    el.className = "jwtf-sg-badge";
    el.style.display = "none";
    document.body.appendChild(el);
    node._jwtfBadge = el;
    badges.add(node);
    updateBadgeStyle(node);
    return el;
}

function updateBadgeStyle(node) {
    const el = node._jwtfBadge;
    if (!el) return;
    const hex = node._jwtfHex;
    el.style.background = hex ? darken(hex, 0.35) : "#26282e";
    el.style.borderColor = hex ?? "#555";
    el.style.boxShadow = hex ? `0 0 8px ${hex}88` : "none";
}

function positionBadge(node) {
    const el = ensureBadge(node);
    const key = keyOf(node);
    const text = (node.comfyClass === SET ? "⚡ " : "") + key.toUpperCase();
    if (el.textContent !== text) el.textContent = text;
    const canvas = app.canvas;
    if (!canvas?.canvas || node.flags?.collapsed || !key || key === PLACEHOLDER) {
        el.style.display = "none";
        return;
    }
    const { offset, scale } = canvas.ds;
    const rect = canvas.canvas.getBoundingClientRect();
    const x = rect.left + window.scrollX + (node.pos[0] + offset[0]) * scale;
    const y = rect.top + window.scrollY + (node.pos[1] + node.size[1] + offset[1]) * scale + 4 * scale;
    el.style.left = `${x}px`;
    el.style.top = `${y}px`;
    el.style.transform = `scale(${scale})`;
    el.style.display = "";
    node._jwtfDrawnAt = performance.now();
}

// Hide badges whose node stopped drawing (off screen, other graph, etc.).
setInterval(() => {
    const now = performance.now();
    for (const n of badges) {
        if (n._jwtfBadge && now - (n._jwtfDrawnAt ?? 0) > 200) n._jwtfBadge.style.display = "none";
    }
}, 200);

function removeBadge(node) {
    node._jwtfBadge?.remove();
    node._jwtfBadge = null;
    badges.delete(node);
}

// ---- prompt rewrite -----------------------------------------------------------

function injectSetLinks(output) {
    if (!output) return;
    const sets = {};
    for (const [id, n] of Object.entries(output)) {
        if (n?.class_type === SET && typeof n.inputs?.key === "string") sets[n.inputs.key] = id;
    }
    for (const n of Object.values(output)) {
        if (n?.class_type !== GET || typeof n.inputs?.key !== "string") continue;
        const src = sets[n.inputs.key];
        if (src != null && n.inputs[LINK_INPUT] == null) n.inputs[LINK_INPUT] = [src, 0];
    }
}

function removeLinkSocket(node) {
    const idx = node.inputs?.findIndex((i) => i.name === LINK_INPUT) ?? -1;
    if (idx >= 0) node.removeInput(idx);
}

app.registerExtension({
    name: "JezzWTF.UtilityCore.SetGet",

    setup() {
        const orig = app.graphToPrompt;
        app.graphToPrompt = async function (...args) {
            const res = await orig.apply(this, args);
            try { injectSetLinks(res?.output); } catch (e) { console.warn("[jezzwtf] set/get rewrite failed", e); }
            return res;
        };
    },

    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== SET && nodeData.name !== GET) return;
        const isSet = nodeData.name === SET;

        chain(nodeType.prototype, "onNodeCreated", function () {
            const node = this;
            const keyW = findWidget(node, "key");
            if (isSet) {
                let timer = 0;
                let lastKey = keyOf(node);
                onWidget(keyW, () => {
                    clearTimeout(timer);
                    timer = setTimeout(() => {
                        const v = String(keyW.value ?? "").trim();
                        if (v && !v.startsWith("set_")) keyW.value = `set_${v}`;
                        recolorGetsFor(lastKey);
                        lastKey = keyOf(node);
                        recolorGetsFor(lastKey);
                        node.setDirtyCanvas(true, true);
                    }, 400);
                });
                const colorW = findWidget(node, "color");
                onWidget(colorW, (v) => {
                    applyColor(node, v);
                    recolorGetsFor(keyOf(node));
                });
                setTimeout(() => applyColor(node, colorW?.value), 100);
            } else {
                removeLinkSocket(node);
                if (keyW) {
                    keyW.options = keyW.options ?? {};
                    Object.defineProperty(keyW.options, "values", {
                        configurable: true,
                        enumerable: true,
                        get: () => [PLACEHOLDER, ...new Set(setNodes().map(keyOf).filter(Boolean))],
                        set: () => {},
                    });
                    onWidget(keyW, () => syncGet(node));
                }
                setTimeout(() => syncGet(node), 100);
            }
        });

        chain(nodeType.prototype, "onConfigure", function () {
            if (!isSet) removeLinkSocket(this);
            setTimeout(() => (isSet ? applyColor(this, findWidget(this, "color")?.value) : syncGet(this)), 100);
        });

        chain(nodeType.prototype, "onConnectionsChange", function () {
            if (this._jwtfHex) setTimeout(() => paintLinks(this, this._jwtfHex), 0);
        });

        chain(nodeType.prototype, "onDrawBackground", function (ctx) {
            if (!this._jwtfHex || this.flags?.collapsed) return;
            ctx.save();
            ctx.fillStyle = this.bgcolor;
            ctx.beginPath();
            ctx.roundRect(0, 0, this.size[0], this.size[1], [0, 0, 10, 10]);
            ctx.fill();
            ctx.restore();
        });

        chain(nodeType.prototype, "onDrawForeground", function () {
            positionBadge(this);
        });

        chain(nodeType.prototype, "onRemoved", function () {
            removeBadge(this);
            if (isSet) setTimeout(() => recolorGetsFor(keyOf(this)), 0);
        });
    },
});
