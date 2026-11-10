// Timeline editor for JWTFPromptRelayTimeline. Drives the hidden `timeline_data`, `local_prompts`
// and `segment_lengths` widgets (all still serialised); fps / time_units only affect the display.
import { app } from "../../../scripts/app.js";
import { chain, clamp, findWidget, fitNode, h, hideWidget, injectCss, setWidgetValue } from "./_shared.js";

const NODE = "JWTFPromptRelayTimeline";
const RULER_H = 22;
const LANE_H = 64;
const CANVAS_H = RULER_H + LANE_H + 4;
const HANDLE = 6;
const DRAG_START = 6;
const HISTORY = 50;
const PALETTE = ["#4f8cff", "#ff5fa8", "#34d399", "#fbbf24", "#a78bfa", "#fb7185", "#22d3ee", "#f97316", "#84cc16", "#e879f9"];
const FRAME_STEPS = [1, 2, 4, 5, 8, 10, 16, 20, 25, 50, 100];
const SECOND_STEPS = [0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
const PANEL_H = CANVAS_H + 190;

injectCss("jwtf-ml-timeline", `
.jwtf-tl-canvas { display: block; width: 100%; height: ${CANVAS_H}px; border-radius: 6px; background: #121317;
  border: 1px solid #30333b; touch-action: none; }
.jwtf-tl-ta { height: 62px; }
.jwtf-tl-tok { font-size: 11px; color: #8b8f99; } .jwtf-tl-tok.hi { color: #fbbf24; }
.jwtf-ml:focus { outline: none; }
`);

const num = (v, d) => (Number.isFinite(Number(v)) ? Number(v) : d);

function nextColor(segs) {
    const used = new Set(segs.map((s) => s.color));
    const free = PALETTE.find((c) => !used.has(c));
    return free ?? `hsl(${(segs.length * 137.508) % 360}, 55%, 55%)`;
}

function defaultSegments(max) {
    const a = Math.max(1, Math.floor(max / 2));
    return [
        { prompt: "", length: a, color: PALETTE[0] },
        { prompt: "", length: Math.max(1, max - a), color: PALETTE[1] },
    ];
}

function parseTimeline(raw, max) {
    try {
        const data = JSON.parse(raw);
        if (Array.isArray(data?.segments) && data.segments.length) {
            return data.segments.map((s, i) => ({
                prompt: typeof s?.prompt === "string" ? s.prompt : "",
                length: Math.max(1, Math.round(num(s?.length, 1))),
                color: typeof s?.color === "string" ? s.color : PALETTE[i % PALETTE.length],
            }));
        }
    } catch { /* fall through to the default */ }
    return defaultSegments(max);
}

const cleanPrompt = (text) => String(text ?? "").replace(/\|/g, " ").replace(/\s+/g, " ").trim();

function niceStep(steps, minStep) {
    return steps.find((s) => s >= minStep) ?? steps[steps.length - 1];
}

function setupTimeline(node) {
    const timelineW = findWidget(node, "timeline_data");
    const promptsW = findWidget(node, "local_prompts");
    const lengthsW = findWidget(node, "segment_lengths");
    const maxW = findWidget(node, "max_frames");
    const hideNative = () => { hideWidget(timelineW); hideWidget(promptsW); hideWidget(lengthsW); };
    hideNative();

    const getMax = () => Math.max(1, Math.round(num(maxW?.value, 129)));
    const getFps = () => Math.max(0.1, num(findWidget(node, "fps")?.value, 24));
    const seconds = () => findWidget(node, "time_units")?.value === "seconds";

    let segs = parseTimeline(String(timelineW?.value ?? ""), getMax());
    let sel = 0;
    let undo = [];
    let redo = [];
    let lastMax = getMax();
    let lastWritten = null;
    let hover = -1;
    let hoverEdge = -1;
    let drag = null; // {kind: "edge"|"move", idx, ...}
    let animating = false;
    const dispX = new WeakMap(); // segment -> displayed x (frames), eased while reordering

    const canvas = h("canvas.jwtf-tl-canvas");
    const ctx = canvas.getContext("2d");
    const ta = h("textarea.jwtf-ml-ta.jwtf-tl-ta", { placeholder: "Prompt for the selected segment", spellcheck: false });
    const tok = h("span.jwtf-tl-tok");
    const lenIn = h("input.jwtf-ml-input", { type: "number", style: { width: "78px" } });
    const lenUnit = h("span.jwtf-ml-muted");
    const total = h("span.jwtf-ml-muted.jwtf-ml-grow");
    const btn = (label, fn, title) => h("button.jwtf-ml-btn", { onclick: fn, title }, label);
    const undoBtn = btn("Undo", () => doUndo(), "Ctrl+Z");
    const redoBtn = btn("Redo", () => doRedo(), "Ctrl+Shift+Z");
    const delBtn = btn("Delete", () => removeSel(), "Delete");
    const root = h("div.jwtf-ml", { tabIndex: 0 },
        canvas,
        h("div.jwtf-ml-row", {}, h("span.jwtf-ml-muted", {}, "Length"), lenIn, lenUnit, total, tok),
        ta,
        h("div.jwtf-ml-row.jwtf-ml-wrap", {}, undoBtn, redoBtn, btn("Add", () => addSeg()), btn("Duplicate", () => dupSel(), "Ctrl+D"),
            btn("Equalize", () => equalize()), delBtn));

    // ------------------------------------------------------------- model
    const snapshot = () => JSON.stringify(segs);
    function pushUndo(before = snapshot()) {
        if (undo[undo.length - 1] === before) return;
        undo.push(before);
        if (undo.length > HISTORY) undo.shift();
        redo = [];
    }
    function restore(json) {
        segs = JSON.parse(json);
        sel = clamp(sel, 0, segs.length - 1);
        commit();
    }
    function doUndo() {
        if (!undo.length) return;
        redo.push(snapshot());
        restore(undo.pop());
    }
    function doRedo() {
        if (!redo.length) return;
        undo.push(snapshot());
        restore(redo.pop());
    }
    const sum = (arr = segs) => arr.reduce((t, s) => t + s.length, 0);

    function trimToFit(protect = -1) {
        let over = sum() - getMax();
        for (let i = segs.length - 1; i >= 0 && over > 0; i--) {
            if (i === protect) continue;
            const take = Math.min(over, segs[i].length - 1);
            segs[i].length -= take;
            over -= take;
        }
        if (over > 0 && protect >= 0 && segs[protect]) segs[protect].length = Math.max(1, segs[protect].length - over);
    }

    // Shifting resize: segment `idx` gets `newLen`; later segments absorb the change, then idx itself if still over.
    function setLen(idx, newLen, baseline) {
        baseline.forEach((l, i) => { segs[i].length = l; });
        segs[idx].length = Math.max(1, Math.round(newLen));
        const max = getMax();
        let over = sum() - max;
        for (let i = idx + 1; i < segs.length && over > 0; i++) {
            const take = Math.min(over, segs[i].length - 1);
            segs[i].length -= take;
            over -= take;
        }
        if (over > 0) segs[idx].length = Math.max(1, segs[idx].length - over);
    }

    function addSeg() {
        pushUndo();
        const n = segs.length;
        const len = Math.max(1, Math.floor(getMax() / (n + 1)));
        segs.push({ prompt: "", length: len, color: nextColor(segs) });
        sel = segs.length - 1;
        trimToFit(sel);
        commit();
    }
    function dupSel() {
        if (!segs[sel]) return;
        pushUndo();
        const src = segs[sel];
        const half = Math.max(1, Math.floor(src.length / 2));
        src.length = Math.max(1, src.length - half);
        segs.splice(sel + 1, 0, { prompt: src.prompt, length: half, color: nextColor(segs) });
        sel += 1;
        trimToFit(sel);
        commit();
    }
    function equalize() {
        pushUndo();
        const max = getMax();
        const n = segs.length;
        const base = Math.max(1, Math.floor(max / n));
        const extra = Math.max(0, max - base * n);
        segs.forEach((s, i) => { s.length = base + (i < extra ? 1 : 0); });
        commit();
    }
    function removeSel() {
        if (segs.length <= 1) return;
        pushUndo();
        segs.splice(sel, 1);
        sel = clamp(sel, 0, segs.length - 1);
        commit();
    }

    // ------------------------------------------------------------- persistence
    function write() {
        const json = JSON.stringify({ segments: segs });
        lastWritten = json;
        setWidgetValue(timelineW, json);
        // "|" separates segments in the text widget, so it cannot appear inside a prompt.
        setWidgetValue(promptsW, segs.map((s) => cleanPrompt(s.prompt)).join(" | "));
        setWidgetValue(lengthsW, segs.map((s) => s.length).join(", "));
        node.setDirtyCanvas(true, true);
    }
    function commit() {
        write();
        refreshControls();
        draw();
    }

    // ------------------------------------------------------------- controls
    function refreshControls() {
        const s = segs[sel];
        if (s && document.activeElement !== ta && ta.value !== s.prompt) ta.value = s.prompt;
        ta.disabled = !s;
        const words = (ta.value.trim().match(/\S+/g) ?? []).length;
        const est = Math.ceil(words * 1.3);
        const empties = segs.map((x, i) => (cleanPrompt(x.prompt) ? 0 : i + 1)).filter(Boolean);
        tok.textContent = empties.length ? `Segment ${empties.join(", ")} needs a prompt` : `~${est} tokens`;
        tok.classList.toggle("hi", est > 60 || empties.length > 0);
        if (s && document.activeElement !== lenIn) {
            lenIn.value = seconds() ? String(+(s.length / getFps()).toFixed(3)) : String(s.length);
        }
        lenIn.step = seconds() ? String(+(1 / getFps()).toFixed(4)) : "1";
        lenUnit.textContent = seconds() ? "s" : "fr";
        total.textContent = `Total: ${seconds() ? +(sum() / getFps()).toFixed(2) : sum()} / ${seconds() ? +(getMax() / getFps()).toFixed(2) : getMax()}`;
        undoBtn.disabled = !undo.length;
        redoBtn.disabled = !redo.length;
        delBtn.disabled = segs.length <= 1;
    }

    let promptT = 0;
    const commitPrompt = () => {
        clearTimeout(promptT);
        const s = segs[sel];
        if (!s || s.prompt === ta.value) return;
        pushUndo();
        s.prompt = ta.value;
        commit();
    };
    ta.addEventListener("input", () => {
        if (ta.value.includes("|")) ta.value = ta.value.replace(/\|/g, " ");
        const words = (ta.value.trim().match(/\S+/g) ?? []).length;
        tok.textContent = `~${Math.ceil(words * 1.3)} tokens`;
        clearTimeout(promptT);
        promptT = setTimeout(commitPrompt, 120);
    });
    ta.addEventListener("blur", commitPrompt);
    ta.addEventListener("keydown", (e) => e.stopPropagation());

    lenIn.addEventListener("keydown", (e) => e.stopPropagation());
    lenIn.addEventListener("change", () => {
        const s = segs[sel];
        const v = parseFloat(lenIn.value);
        if (!s || !Number.isFinite(v)) { refreshControls(); return; }
        pushUndo();
        const frames = seconds() ? Math.round(v * getFps()) : Math.round(v);
        setLen(sel, frames, segs.map((x) => x.length));
        commit();
    });

    root.addEventListener("keydown", (e) => {
        if (e.target !== root && e.target !== canvas) return;
        const mod = e.ctrlKey || e.metaKey;
        if (e.key === "Delete" || e.key === "Backspace") { removeSel(); e.preventDefault(); }
        else if (mod && e.key.toLowerCase() === "z") { (e.shiftKey ? doRedo : doUndo)(); e.preventDefault(); }
        else if (mod && e.key.toLowerCase() === "y") { doRedo(); e.preventDefault(); }
        else if (mod && e.key.toLowerCase() === "d") { dupSel(); e.preventDefault(); }
        else if (e.key === "ArrowLeft") { sel = clamp(sel - 1, 0, segs.length - 1); refreshControls(); draw(); e.preventDefault(); }
        else if (e.key === "ArrowRight") { sel = clamp(sel + 1, 0, segs.length - 1); refreshControls(); draw(); e.preventDefault(); }
        else return;
        e.stopPropagation();
    });

    // ------------------------------------------------------------- canvas
    const ppf = () => (canvas.clientWidth || 1) / getMax();

    function layoutOrder() {
        // Target start frame per segment, with a dragged segment shown in its prospective slot.
        const order = segs.map((_, i) => i);
        if (drag?.kind === "move" && drag.active) {
            order.splice(order.indexOf(drag.idx), 1);
            order.splice(drag.target, 0, drag.idx);
        }
        const pos = new Map();
        let cursor = 0;
        for (const i of order) { pos.set(segs[i], cursor); cursor += segs[i].length; }
        return pos;
    }

    function wrapText(text, maxW) {
        const words = text.split(/\s+/).filter(Boolean);
        const lines = [];
        let line = "";
        for (const w of words) {
            const t = line ? `${line} ${w}` : w;
            if (ctx.measureText(t).width > maxW && line) { lines.push(line); line = w; } else line = t;
        }
        if (line) lines.push(line);
        return lines;
    }

    function fmtTime(frames) {
        return seconds() ? `${+(frames / getFps()).toFixed(2)}s` : String(frames);
    }

    function draw() {
        const dpr = window.devicePixelRatio || 1;
        const w = canvas.clientWidth || 300;
        if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(CANVAS_H * dpr)) {
            canvas.width = Math.round(w * dpr);
            canvas.height = Math.round(CANVAS_H * dpr);
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, CANVAS_H);
        const k = ppf();
        const max = getMax();

        // ruler
        ctx.font = "10px system-ui, sans-serif";
        ctx.textBaseline = "middle";
        ctx.fillStyle = "#8b8f99";
        ctx.strokeStyle = "#3a3d46";
        const unit = seconds() ? getFps() : 1;
        const step = niceStep(seconds() ? SECOND_STEPS : FRAME_STEPS, 60 / (k * unit)) * unit; // in frames
        for (let f = 0; f <= max + 1e-6; f += step) {
            const x = Math.round(f * k) + 0.5;
            ctx.beginPath(); ctx.moveTo(x, RULER_H - 6); ctx.lineTo(x, RULER_H); ctx.stroke();
            ctx.textAlign = f === 0 ? "left" : "center";
            ctx.fillText(seconds() ? `${+(f / unit).toFixed(2)}s` : String(Math.round(f)), x + (f === 0 ? 2 : 0), RULER_H / 2 - 1);
        }
        ctx.strokeStyle = "#8b8f99";
        ctx.beginPath(); ctx.moveTo(max * k - 0.5, 2); ctx.lineTo(max * k - 0.5, RULER_H + LANE_H); ctx.stroke();

        // blocks
        const pos = layoutOrder();
        let moving = false;
        const draws = [];
        segs.forEach((s, i) => {
            let x = pos.get(s) * k;
            if (drag?.kind === "move" && drag.active && drag.idx === i) {
                x = drag.x;
            } else {
                const cur = dispX.get(s) ?? x;
                const nx = Math.abs(cur - x) < 0.3 ? x : cur + (x - cur) * 0.15;
                if (nx !== x) moving = true;
                dispX.set(s, nx);
                x = nx;
            }
            draws.push([s, i, x]);
        });
        draws.sort((a, b) => (drag?.active && drag.idx === a[1] ? 1 : 0) - (drag?.active && drag.idx === b[1] ? 1 : 0));
        let startFrame = 0;
        const starts = [];
        segs.forEach((s) => { starts.push(startFrame); startFrame += s.length; });
        for (const [s, i, x] of draws) {
            const bw = Math.max(2, s.length * k - 2);
            const y = RULER_H;
            const lifted = drag?.active && drag.idx === i && drag.kind === "move";
            ctx.globalAlpha = lifted ? 0.85 : i === sel ? 1 : hover === i ? 0.8 : 0.62;
            ctx.fillStyle = s.color;
            ctx.beginPath(); ctx.roundRect(x + 1, y, bw, LANE_H, 5); ctx.fill();
            ctx.globalAlpha = 1;
            if (i === sel) {
                ctx.strokeStyle = "#fff"; ctx.lineWidth = 2;
                ctx.beginPath(); ctx.roundRect(x + 1, y, bw, LANE_H, 5); ctx.stroke();
                ctx.lineWidth = 1;
            }
            ctx.save();
            ctx.beginPath(); ctx.rect(x + 4, y, Math.max(0, bw - 8), LANE_H); ctx.clip();
            ctx.fillStyle = "#fff";
            ctx.textAlign = "left";
            ctx.font = "11px system-ui, sans-serif";
            const lines = s.prompt ? wrapText(s.prompt, bw - 10).slice(0, 2) : [];
            if (s.prompt && wrapText(s.prompt, bw - 10).length > 2) lines[1] = `${lines[1]}…`;
            if (!lines.length) { ctx.fillStyle = "rgba(255,255,255,.55)"; lines.push("(empty)"); }
            lines.forEach((ln, li) => ctx.fillText(ln, x + 6, y + 14 + li * 14));
            ctx.font = "10px system-ui, sans-serif";
            ctx.fillStyle = "rgba(255,255,255,.8)";
            ctx.fillText(`${fmtTime(starts[i])}–${fmtTime(starts[i] + s.length)} (${fmtTime(s.length)})`, x + 6, y + LANE_H - 9);
            ctx.restore();
            // boundary handle
            ctx.fillStyle = hoverEdge === i || (drag?.kind === "edge" && drag.idx === i) ? "#fff" : "rgba(255,255,255,.55)";
            ctx.fillRect(x + bw - 1, y + 16, 3, LANE_H - 32);
        }
        if (moving && !animating) {
            animating = true;
            requestAnimationFrame(() => { animating = false; draw(); });
        }
    }

    function edgeAt(px) {
        const k = ppf();
        let f = 0;
        for (let i = 0; i < segs.length; i++) {
            f += segs[i].length;
            if (Math.abs(px - f * k) <= HANDLE) return i;
        }
        return -1;
    }
    function blockAt(px) {
        const k = ppf();
        let f = 0;
        for (let i = 0; i < segs.length; i++) {
            if (px >= f * k && px < (f + segs[i].length) * k) return i;
            f += segs[i].length;
        }
        return -1;
    }
    const localX = (e) => e.clientX - canvas.getBoundingClientRect().left;

    canvas.addEventListener("pointermove", (e) => {
        const px = localX(e);
        if (drag) return;
        const edge = edgeAt(px);
        const b = blockAt(px);
        if (edge !== hoverEdge || b !== hover) {
            hoverEdge = edge;
            hover = b;
            canvas.style.cursor = edge >= 0 ? "ew-resize" : b >= 0 ? "grab" : "default";
            draw();
        }
    });
    canvas.addEventListener("pointerleave", () => {
        if (drag) return;
        hover = hoverEdge = -1;
        draw();
    });

    canvas.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        e.stopPropagation();
        root.focus({ preventScroll: true });
        const px = localX(e);
        const edge = edgeAt(px);
        canvas.setPointerCapture(e.pointerId);
        if (edge >= 0) {
            drag = { kind: "edge", idx: edge, before: snapshot(), baseline: segs.map((s) => s.length), startX: px, startLen: segs[edge].length };
            sel = edge;
        } else {
            const b = blockAt(px);
            if (b < 0) return;
            sel = b;
            const startFrame = segs.slice(0, b).reduce((t, s) => t + s.length, 0);
            drag = { kind: "move", idx: b, before: snapshot(), startX: px, grabDx: px - startFrame * ppf(), active: false, target: b, x: 0 };
            refreshControls();
        }
        draw();
    });
    canvas.addEventListener("pointermove", (e) => {
        if (!drag) return;
        const px = localX(e);
        const k = ppf();
        if (drag.kind === "edge") {
            setLen(drag.idx, drag.startLen + Math.round((px - drag.startX) / k), drag.baseline);
            write();
            refreshControls();
            draw();
            return;
        }
        if (!drag.active && Math.abs(px - drag.startX) <= DRAG_START) return;
        drag.active = true;
        drag.x = px - drag.grabDx;
        const centre = drag.x + (segs[drag.idx].length * k) / 2;
        // Nearest slot centre among the layout with the dragged segment removed.
        const rest = segs.filter((_, i) => i !== drag.idx);
        let best = 0;
        let bestD = Infinity;
        let f = 0;
        for (let slot = 0; slot <= rest.length; slot++) {
            const c = (f + segs[drag.idx].length / 2) * k;
            const d = Math.abs(c - centre);
            if (d < bestD) { bestD = d; best = slot; }
            if (slot < rest.length) f += rest[slot].length;
        }
        drag.target = best;
        draw();
    });
    const finish = () => {
        const d = drag;
        drag = null;
        if (!d) return;
        if (d.kind === "edge") {
            if (snapshot() !== d.before) pushUndo(d.before);
        } else if (d.active && d.target !== d.idx) {
            pushUndo(d.before);
            const [item] = segs.splice(d.idx, 1);
            segs.splice(d.target, 0, item);
            sel = d.target;
        }
        commit();
    };
    canvas.addEventListener("pointerup", finish);
    canvas.addEventListener("pointercancel", finish);

    // ------------------------------------------------------------- sync
    function onMaxChange() {
        const m = getMax();
        if (m !== lastMax) {
            lastMax = m;
            if (sum() > m) { pushUndo(); trimToFit(); write(); }
        }
        refreshControls();
        draw();
    }
    for (const name of ["max_frames", "fps", "time_units"]) {
        const w = findWidget(node, name);
        if (!w) continue;
        const orig = w.callback;
        w.callback = function (...a) {
            const r = orig?.apply(this, a);
            onMaxChange();
            return r;
        };
    }

    function reload() {
        hideNative();
        const fpsW = findWidget(node, "fps");
        const unitsW = findWidget(node, "time_units");
        if (fpsW && !Number.isFinite(Number(fpsW.value))) fpsW.value = 24;
        if (unitsW && !unitsW.value) unitsW.value = "frames";
        const raw = String(timelineW?.value ?? "");
        if (raw !== lastWritten) {
            segs = parseTimeline(raw, getMax());
            undo = [];
            redo = [];
        }
        sel = clamp(sel, 0, segs.length - 1);
        lastMax = getMax();
        ta.value = segs[sel]?.prompt ?? "";
        refreshControls();
        draw();
    }

    const widget = node.addDOMWidget("jwtf_timeline", "jwtf_timeline", root, {
        serialize: false, getMinHeight: () => PANEL_H, hideOnZoom: false,
    });
    widget.computeSize = (w) => [w, PANEL_H];
    node._jwtfSync = reload;
    new ResizeObserver(() => draw()).observe(canvas);
    setTimeout(() => {
        reload();
        if (!String(timelineW?.value ?? "").trim()) write();
    }, 0);
    node.setSize([Math.max(node.size[0], 440), Math.max(node.size[1], 560)]);
    setTimeout(() => fitNode(node, 440), 80);
}

app.registerExtension({
    name: "JezzWTF.ModelLoaders.PromptRelayTimeline",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE) return;
        chain(nodeType.prototype, "onNodeCreated", function () { setupTimeline(this); });
        chain(nodeType.prototype, "onConfigure", function () { setTimeout(() => this._jwtfSync?.(), 0); });
    },
});
