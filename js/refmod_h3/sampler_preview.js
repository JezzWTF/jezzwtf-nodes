// Live preview panel for Ultimate KSampler and H3 KSampler: per-step media, sigma/delta and step-time
// graphs, phase-coloured progress bar and a help popover. Listens to `kj_preview_override`
// (the preview wrapper's event), `jezzwtf.uk_phase`, core `progress` and `execution_start`.
import { app } from "../../../scripts/app.js";
import { api, chain, clamp, findWidget, h, injectCss, sameNode, setWidgetVisible } from "./_shared.js";

const NODES = new Set(["JWTFUltimateKSampler", "JWTFH3KSampler"]);
const PREVIEW_EVENT = "kj_preview_override";
const PHASE_EVENT = "jezzwtf.uk_phase";
const MIN_H = 380, MIN_H_COLLAPSED = 40, DEFAULT_SIZE = [440, 940];
const PHASE_COLOR = { idle: "#6b7280", queued: "#6b7280", sampling: "#f59e0b", decoding: "#22d3ee", done: "#22c55e" };
const KEY_COLLAPSED = "jezzwtf_uk_collapsed", KEY_PANEL_H = "jezzwtf_uk_panel_h";

injectCss("jezzwtf-sampler-preview", `
.jzsp{box-sizing:border-box;display:flex;flex-direction:column;gap:4px;width:100%;height:100%;padding:4px;font:12px system-ui,sans-serif;
 color:#dfe2ea;background:#16181d;border:1px solid #2c2f37;border-radius:8px;outline:none}
.jzsp .bar{display:flex;align-items:center;gap:6px}.jzsp .bar b{flex:1;font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:#9aa1af}
.jzsp .x{cursor:pointer;color:#9aa1af;padding:0 4px}.jzsp .x:hover{color:#fff}
.jzsp .media{position:relative;flex:1 1 auto;min-height:120px;background:#0d0e11 center/contain no-repeat;border-radius:6px;overflow:hidden;
 display:flex;align-items:center;justify-content:center}
.jzsp .media img,.jzsp .media video{max-width:100%;max-height:100%;object-fit:contain;cursor:pointer}
.jzsp .media .spec{position:absolute;left:0;right:0;bottom:0;height:34px;width:100%;object-fit:fill;opacity:.85;pointer-events:none}
.jzsp .media .mute{position:absolute;top:6px;right:6px;cursor:pointer;background:rgba(0,0,0,.55);border-radius:10px;padding:1px 8px;font-size:11px}
.jzsp .media .scrub{position:absolute;left:8px;right:8px;bottom:40px;width:calc(100% - 16px)}
.jzsp .empty{color:#5b5f6a}
.jzsp .grip{height:6px;cursor:ns-resize;background:linear-gradient(#2c2f37,#2c2f37) center/40px 2px no-repeat}
.jzsp .graphs{flex:0 0 auto;display:flex;flex-direction:column;gap:3px}.jzsp canvas{width:100%;display:block;background:#0f1013;border-radius:4px}
.jzsp .stat{font-size:10px;color:#8b8f99;display:flex;gap:10px}
.jzsp.collapsed .media,.jzsp.collapsed .graphs,.jzsp.collapsed .grip,.jzsp.collapsed .pbar{display:none}
.jzsp-help{position:fixed;z-index:10000;max-width:300px;padding:10px 12px;background:#20232b;color:#dfe2ea;border:1px solid #444a58;
 border-radius:8px;font:12px/1.5 system-ui,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.5)}
`);

const HELP = [
    "Live sampling preview. Each step is kept: hover the graph to see a step, click to lock it, Left/Right arrows step through.",
    "Click the image to pause a clip, Space pauses while the cursor is over the panel.",
    "Graph: dashed = sigma schedule, solid = change per step (delta), dotted = detail-boost curve when present.",
    "Step time switches to seconds when the first step takes over 1.5 s; click the time graph to toggle.",
].join("\n");

const panels = new Set();
const lastStart = new Map(); // source id -> step-0 payload without the image

const fresh = () => ({
    sigmas: [], dbCurve: null, total: 0, delta: [], stepMs: [], sigma: [], steps: new Map(), shown: null,
    locked: null, hover: null, phase: "idle", v: 0, max: 0, avgMs: 0, secs: null, paused: false, muted: true,
    queued: false,
});

const sourceOf = (node) => node._jzSource ?? String(node.id);
const matches = (node, id) => id != null && (sameNode(id, sourceOf(node)) || sameNode(id, node.id));

// --------------------------------------------------------------------------- drawing

function sizeCanvas(c, cssH) {
    const w = Math.max(10, c.clientWidth || 380), dpr = window.devicePixelRatio || 1;
    c.style.height = `${cssH}px`;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(cssH * dpr)) {
        c.width = Math.round(w * dpr);
        c.height = Math.round(cssH * dpr);
    }
    const ctx = c.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, cssH);
    return [ctx, w, cssH];
}

function drawGrid(ctx, w, hh) {
    ctx.strokeStyle = "rgba(255,255,255,.06)";
    ctx.lineWidth = 1;
    for (let i = 1; i < 4; i++) { ctx.beginPath(); ctx.moveTo(0, hh * i / 4); ctx.lineTo(w, hh * i / 4); ctx.stroke(); }
}

function plotLine(ctx, vals, x0, w, hh, lo, hi, color, dashed) {
    ctx.beginPath();
    let started = false;
    vals.forEach((v, i) => {
        if (v == null || !Number.isFinite(v)) { started = false; return; }
        const x = x0 + (vals.length > 1 ? (w - 2 * x0) * i / (vals.length - 1) : 0);
        const y = hh - 4 - (hh - 8) * ((v - lo) / ((hi - lo) || 1));
        if (started) ctx.lineTo(x, y); else ctx.moveTo(x, y);
        started = true;
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.setLineDash(dashed ? [4, 3] : []);
    ctx.stroke();
    ctx.setLineDash([]);
}

function drawSigma(panel) {
    const st = panel.state;
    const [ctx, w, hh] = sizeCanvas(panel.sigmaCanvas, panel.graphH);
    drawGrid(ctx, w, hh);
    const sig = st.sigmas;
    if (sig.length) {
        const lo = Math.min(0, ...sig), hi = Math.max(...sig);
        plotLine(ctx, sig, 6, w, hh, lo, hi, "#8b93a7", true);
        if (st.dbCurve) plotLine(ctx, st.dbCurve, 6, w, hh, 0, 1, "#a78bfa", true);
    }
    const deltas = st.delta;
    if (deltas.length) {
        const real = deltas.filter((d) => d != null);
        plotLine(ctx, deltas, 6, w, hh, 0, Math.max(1e-9, ...real), "#f59e0b", false);
    }
    const mark = st.locked ?? st.hover;
    const n = Math.max(1, (st.sigmas.length || st.total + 1) - 1);
    if (mark != null) {
        const x = 6 + (w - 12) * clamp(mark, 0, n) / n;
        ctx.strokeStyle = st.locked != null ? "#fbbf24" : "rgba(255,255,255,.5)";
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, hh); ctx.stroke();
        ctx.fillStyle = "#dfe2ea";
        ctx.font = "10px system-ui, sans-serif";
        const d = st.delta[mark - 1], s = st.sigmas[mark];
        ctx.textAlign = x > w / 2 ? "right" : "left";
        ctx.fillText(`step ${mark}${s != null ? `  sigma ${s.toFixed(3)}` : ""}${d != null ? `  delta ${d.toFixed(4)}` : ""}${st.locked != null ? "  (locked)" : ""}`,
            x + (x > w / 2 ? -4 : 4), 11);
    }
}

function drawTimes(panel) {
    const st = panel.state;
    const [ctx, w, hh] = sizeCanvas(panel.timeCanvas, 60);
    drawGrid(ctx, w, hh);
    const ms = st.stepMs;
    if (!ms.length) return;
    const secs = st.secs ?? (ms[0] > 1500);
    const vals = ms.map((v) => (v == null ? null : secs ? v / 1000 : v));
    const real = vals.filter((v) => v != null);
    plotLine(ctx, vals, 6, w, hh, 0, Math.max(1e-9, ...real), "#22d3ee", false);
    ctx.fillStyle = "#8b8f99";
    ctx.font = "10px system-ui, sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(`${Math.max(...real).toFixed(secs ? 2 : 0)} ${secs ? "s" : "ms"} max`, w - 4, 11);
}

function drawProgress(panel) {
    const st = panel.state;
    const [ctx, w, hh] = sizeCanvas(panel.barCanvas, 22);
    ctx.fillStyle = "#101114";
    ctx.fillRect(0, 0, w, hh);
    const frac = st.max > 0 ? clamp(st.v / st.max, 0, 1) : st.phase === "done" ? 1 : 0;
    const color = PHASE_COLOR[st.phase] ?? PHASE_COLOR.idle;
    const g = ctx.createLinearGradient(0, 0, w * frac, 0);
    g.addColorStop(0, color + "88");
    g.addColorStop(1, color);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w * frac, hh);
    ctx.font = "11px system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillStyle = "#f4f5f8";
    let text = st.queued ? "queued" : st.phase;
    if (st.phase === "sampling" && st.max > 0) text = `sampling ${st.v}/${st.max}`;
    ctx.fillText(`${text}${st.max > 0 ? `  ${Math.round(frac * 100)}%` : ""}`, 8, hh / 2 + 4);
    if (st.avgMs > 0 && st.max > 0 && st.phase === "sampling") {
        const eta = Math.max(0, st.max - st.v) * st.avgMs / 1000;
        ctx.textAlign = "right";
        ctx.fillText(`${(st.avgMs / 1000).toFixed(2)} s/step  ETA ${eta.toFixed(0)} s`, w - 8, hh / 2 + 4);
    }
}

function redraw(panel) {
    if (!panel.el.isConnected || panel.collapsed()) return;
    drawSigma(panel);
    drawTimes(panel);
    drawProgress(panel);
}

// --------------------------------------------------------------------------- media

function showStep(panel, idx) {
    const st = panel.state;
    const item = st.steps.get(idx);
    if (!item) return;
    st.shown = idx;
    const key = `${idx}:${item.src.length}`;
    if (panel.mediaKey === key) return;
    panel.mediaKey = key;
    panel.media.querySelectorAll("img.main,video.main,.spec,.mute,.scrub").forEach((e) => e.remove());
    panel.empty.style.display = "none";
    let el;
    if (item.mime === "video/mp4") {
        el = h("video.main", { src: item.src, loop: true, autoplay: true, muted: !item.audio || st.muted, playsInline: true });
        el.muted = !item.audio || st.muted;
        const rate = item.audio ? 1 : clamp((panel.previewFps() || item.fps) / (item.fps || panel.previewFps() || 12), 1 / 16, 16);
        el.playbackRate = rate;
        el.addEventListener("click", () => togglePause(panel));
        const scrub = h("input.scrub", { type: "range", min: 0, max: 1000, value: 0, step: 1 });
        scrub.addEventListener("input", () => { el.pause(); if (el.duration) el.currentTime = el.duration * scrub.value / 1000; });
        el.addEventListener("timeupdate", () => { if (el.duration && document.activeElement !== scrub) scrub.value = String(Math.round(1000 * el.currentTime / el.duration)); });
        panel.media.append(el, scrub);
        if (st.paused) el.pause();
    } else {
        el = h("img.main", { src: item.src });
        el.addEventListener("click", () => togglePause(panel));
        panel.media.append(el);
    }
    if (item.audio) {
        panel.media.append(h("div.mute", { onclick: () => { st.muted = !st.muted; const v = panel.media.querySelector("video.main"); if (v) v.muted = st.muted; m.textContent = st.muted ? "audio off" : "audio on"; } }));
        const m = panel.media.querySelector(".mute");
        m.textContent = st.muted ? "audio off" : "audio on";
        if (item.spec) panel.media.append(h("img.spec", { src: `data:image/png;base64,${item.spec}` }));
    }
}

function togglePause(panel) {
    const st = panel.state;
    st.paused = !st.paused;
    const v = panel.media.querySelector("video.main");
    if (v) { if (st.paused) v.pause(); else v.play().catch(() => {}); }
}

// --------------------------------------------------------------------------- events

function onPreview(detail) {
    for (const panel of panels) {
        if (!matches(panel.node, detail.node_id)) continue;
        const st = panel.state;
        if (detail.step === 0) {
            st.sigmas = detail.sigmas ?? [];
            st.dbCurve = detail.db_curve ?? null;
            st.total = detail.total ?? st.sigmas.length - 1;
            st.delta = []; st.stepMs = []; st.sigma = []; st.steps.clear(); st.locked = null; st.hover = null;
            st.phase = "sampling"; st.queued = false;
            const { image, ...rest } = detail;
            lastStart.set(sourceOf(panel.node), rest);
        } else {
            st.delta[detail.step - 1] = detail.delta ?? null;
            st.stepMs[detail.step - 1] = detail.step_ms ?? null;
            st.avgMs = detail.avg_step_ms ?? st.avgMs;
            st.total = detail.total ?? st.total;
        }
        if (detail.image) {
            st.steps.set(detail.step, { src: `data:${detail.mime ?? "image/jpeg"};base64,${detail.image}`,
                mime: detail.mime ?? "image/jpeg", fps: detail.fps, audio: !!detail.audio, spec: detail.audio_spec });
            if (st.locked == null) showStep(panel, detail.step);
        }
        redraw(panel);
    }
}

function replayStart(panel) {
    const rest = lastStart.get(sourceOf(panel.node));
    if (rest) { const st = panel.state; st.sigmas = rest.sigmas ?? []; st.dbCurve = rest.db_curve ?? null; st.total = rest.total ?? 0; redraw(panel); }
}

function setupEvents() {
    api.addEventListener(PREVIEW_EVENT, (e) => onPreview(e.detail ?? {}));
    api.addEventListener(PHASE_EVENT, (e) => {
        const d = e.detail ?? {};
        for (const p of panels) if (matches(p.node, d.node) || matches(p.node, d.node_raw)) {
            p.state.phase = d.phase; p.state.queued = false;
            if (d.phase === "done") p.state.v = p.state.max || p.state.v;
            redraw(p);
        }
    });
    api.addEventListener("progress", (e) => {
        const d = e.detail ?? {};
        for (const p of panels) if (matches(p.node, d.node)) {
            p.state.v = d.value ?? 0; p.state.max = d.max ?? 0;
            if (p.state.phase === "idle" || p.state.phase === "done") p.state.phase = "sampling";
            redraw(p);
        }
    });
    api.addEventListener("execution_start", () => {
        for (const p of panels) { const st = p.state; st.phase = "idle"; st.queued = true; st.v = 0; st.max = 0; st.avgMs = 0; redraw(p); }
    });
    // a failed or cancelled run never sends "done"; reset the bar instead of leaving it mid-sample
    const abort = () => {
        for (const p of panels) { const st = p.state; st.phase = "idle"; st.queued = false; st.v = 0; st.max = 0; redraw(p); }
    };
    api.addEventListener("execution_error", abort);
    api.addEventListener("execution_interrupted", abort);
}

// --------------------------------------------------------------------------- panel

function buildPanel(node) {
    node.properties = node.properties ?? {};
    const panel = { node, state: fresh(), mediaKey: "", graphH: clamp(node.properties[KEY_PANEL_H] ?? 110, 60, 400) };
    panel.title = h("b", {}, node.comfyClass === "JWTFH3KSampler" ? "H3 sampler preview" : "Sampler preview");
    panel.x = h("span.x", { title: "minimise", onclick: () => setCollapsed(panel, !panel.collapsed()) }, "✕");
    panel.empty = h("div.empty", {}, "waiting for the first step");
    panel.media = h("div.media", {}, panel.empty);
    panel.sigmaCanvas = h("canvas");
    panel.timeCanvas = h("canvas");
    panel.barCanvas = h("canvas.pbar");
    const grip = h("div.grip");
    panel.graphs = h("div.graphs", {}, panel.sigmaCanvas, panel.timeCanvas);
    panel.el = h("div.jzsp", { tabIndex: 0 }, h("div.bar", {}, panel.title, panel.x), panel.media, grip, panel.graphs, panel.barCanvas);
    panel.collapsed = () => !!node.properties[KEY_COLLAPSED];
    panel.previewFps = () => findWidget(node, "preview_fps")?.value ?? 12;

    const stepAt = (ev) => {
        const r = panel.sigmaCanvas.getBoundingClientRect();
        const n = Math.max(1, (panel.state.sigmas.length || panel.state.total + 1) - 1);
        return clamp(Math.round(((ev.clientX - r.left - 6) / Math.max(1, r.width - 12)) * n), 0, n);
    };
    const pick = (idx) => { if (panel.state.steps.has(idx)) showStep(panel, idx); redraw(panel); };
    panel.sigmaCanvas.addEventListener("pointermove", (ev) => { panel.state.hover = stepAt(ev); if (panel.state.locked == null) pick(panel.state.hover); else redraw(panel); });
    panel.sigmaCanvas.addEventListener("pointerleave", () => { panel.state.hover = null; redraw(panel); });
    panel.sigmaCanvas.addEventListener("click", (ev) => {
        const st = panel.state, idx = stepAt(ev);
        st.locked = st.locked === idx ? null : idx;
        if (st.locked != null) pick(st.locked);
        redraw(panel);
    });
    panel.timeCanvas.addEventListener("click", () => { panel.state.secs = !(panel.state.secs ?? (panel.state.stepMs[0] > 1500)); redraw(panel); });
    panel.el.addEventListener("keydown", (ev) => {
        const st = panel.state;
        if (ev.code === "Space") { ev.preventDefault(); togglePause(panel); }
        else if ((ev.key === "ArrowLeft" || ev.key === "ArrowRight") && st.locked != null) {
            ev.preventDefault();
            st.locked = clamp(st.locked + (ev.key === "ArrowLeft" ? -1 : 1), 0, Math.max(1, st.sigmas.length - 1 || st.total));
            pick(st.locked);
        }
    });
    // resizable graphs panel
    grip.addEventListener("pointerdown", (ev) => {
        ev.preventDefault();
        const y0 = ev.clientY, h0 = panel.graphH;
        const move = (m) => { panel.graphH = clamp(h0 - (m.clientY - y0), 60, 400); node.properties[KEY_PANEL_H] = panel.graphH; redraw(panel); };
        const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
    });
    for (const t of ["pointerdown", "wheel"]) panel.el.addEventListener(t, (ev) => ev.stopPropagation(), { passive: true });
    return panel;
}

function setCollapsed(panel, on) {
    const node = panel.node;
    if (on === panel.collapsed()) return;
    if (on) node._jzRestoreH = node.size[1];
    node.properties[KEY_COLLAPSED] = on;
    panel.el.classList.toggle("collapsed", on);
    panel.x.textContent = on ? "▢" : "✕";
    node.setSize(on ? [node.size[0], node.computeSize()[1]] : [node.size[0], Math.max(node._jzRestoreH ?? DEFAULT_SIZE[1], node.computeSize()[1])]);
    node.setDirtyCanvas(true, true);
    redraw(panel);
}

function applyH3Visibility(node) {
    if (node.comfyClass !== "JWTFH3KSampler") return;
    const linked = (n) => !!node.inputs?.find((i) => i.name === n && i.link != null);
    setWidgetVisible(node, findWidget(node, "sampler_name"), !linked("sampler"));
    setWidgetVisible(node, findWidget(node, "seed"), !linked("noise"));
}

function drawHelpBadge(node, ctx) {
    if (node.flags?.collapsed) return;
    const x = node.size[0] - 22, y = -15;
    ctx.fillStyle = "#facc15";
    ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#1b1c20";
    ctx.font = "bold 12px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("?", x, y + 4);
}

function openHelp(node, ev) {
    document.querySelectorAll(".jzsp-help").forEach((e) => e.remove());
    const pop = h("div.jzsp-help", { style: { left: `${ev.clientX + 8}px`, top: `${ev.clientY + 8}px`, whiteSpace: "pre-line" } }, HELP);
    document.body.append(pop);
    const close = (e) => { if (!pop.contains(e.target)) { pop.remove(); window.removeEventListener("pointerdown", close, true); } };
    setTimeout(() => window.addEventListener("pointerdown", close, true), 0);
}

app.registerExtension({
    name: "JezzWTF.RefMod.SamplerPreview",
    setup() { setupEvents(); },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!NODES.has(nodeData.name)) return;
        const proto = nodeType.prototype;
        chain(proto, "onNodeCreated", function () {
            const panel = buildPanel(this);
            this._jzPanel = panel;
            panels.add(panel);
            const w = this.addDOMWidget("preview", "jezzwtf_preview", panel.el, {
                serialize: false, hideOnZoom: false,
                getMinHeight: () => (panel.collapsed() ? MIN_H_COLLAPSED : MIN_H),
            });
            w.serialize = false;
            this.setSize([Math.max(DEFAULT_SIZE[0], this.size[0]), Math.max(DEFAULT_SIZE[1], this.size[1])]);
            applyH3Visibility(this);
            replayStart(panel);
            if (panel.collapsed()) { panel.el.classList.add("collapsed"); panel.x.textContent = "▢"; }
            requestAnimationFrame(() => redraw(panel));
        });
        chain(proto, "onConfigure", function () {
            const p = this._jzPanel;
            if (!p) return;
            p.graphH = clamp(this.properties?.[KEY_PANEL_H] ?? p.graphH, 60, 400);
            p.el.classList.toggle("collapsed", p.collapsed());
            applyH3Visibility(this);
        });
        chain(proto, "onConnectionsChange", function () { applyH3Visibility(this); });
        chain(proto, "onResize", function () { const p = this._jzPanel; if (p) requestAnimationFrame(() => redraw(p)); });
        chain(proto, "onRemoved", function () { if (this._jzPanel) panels.delete(this._jzPanel); });
        chain(proto, "onExecuted", function (message) {
            const id = message?.jezzwtf_source_id?.[0];
            if (id != null) this._jzSource = String(id);
        });
        chain(proto, "onDrawForeground", function (ctx) { drawHelpBadge(this, ctx); });
        chain(proto, "onMouseDown", function (ev, pos) {
            if (pos[1] < 0 && Math.hypot(pos[0] - (this.size[0] - 22), pos[1] + 15) < 10) { openHelp(this, ev); return true; }
            return false;
        });
    },
});
