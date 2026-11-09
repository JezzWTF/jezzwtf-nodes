// RefMod Bake / Loader / Apply: canvas-drawn character cards, slot toolbar, advanced toggle and
// the Apply curve editor. Draw-only: no new serialised widgets. Persists
// node.properties.jezzwtf_slots (1-4 visible slots) and node.properties.jezzwtf_adv.
import { app } from "../../../scripts/app.js";
import { api, chain, clamp, fetchJson, findWidget, onWidget, setWidgetVisible } from "./_shared.js";
import { DIRECTIONS, SHAPES, directionCurve } from "./curve_math.js";

const KINDS = { JWTFRefModBake: "bake", JWTFRefModLoader: "loader", JWTFRefModApply: "apply" };
const MAX_SLOTS = 4;
const NONE = "(none)";
const SOFT_BUDGET = 16384;
const CARD_H = 56;
const TOOLBAR_H = 26;
const METER_H = 22;
const CURVE_H = 112;
const PAD = 8;
const LIB_INTERVAL = 8000;

const SLOT_LABELS = [["mod", "character"], ["visual_strength", "face"], ["audio_strength", "voice"],
    ["strength", "master"], ["copies", "copies"], ["components", "use"]];
const BAKE_LABELS = {
    ref_resolution: "resolution", max_visual_tokens: "token cap", visual_budget: "on overflow",
    audio_type: "voice type", audio_max_seconds: "voice max s", audio_max_tokens: "voice token cap",
    folder_max_items: "folder items", folder_max_edge: "folder max px",
};
const ADV_NODE_WIDGETS = {
    bake: ["audio_type", "audio_max_seconds", "audio_max_tokens", "ref_resolution", "max_visual_tokens",
        "visual_budget", "folder_max_items", "folder_max_edge", "subfolder", "overwrite"],
    loader: ["show_info", "max_total_tokens"],
    apply: ["max_total_tokens", "curve_direction", "curve_shape", "curve_value", "scramble_seed",
        "scramble_mode", "scramble_keep"],
};

// --------------------------------------------------------------------------- library cache

const library = { entries: new Map(), fetchedAt: 0, pending: false };

async function refreshLibrary(force = false) {
    if (library.pending || (!force && Date.now() - library.fetchedAt < LIB_INTERVAL)) return;
    library.pending = true;
    library.fetchedAt = Date.now();
    const list = await fetchJson("/jezzwtf/refmods", []);
    if (Array.isArray(list)) library.entries = new Map(list.map((e) => [e.name, e]));
    library.pending = false;
    for (const n of app.graph?._nodes ?? []) if (KINDS[n.comfyClass]) n.setDirtyCanvas(true, false);
}

const thumbs = new Map();
function thumbFor(entry) {
    if (!entry?.thumb) return null;
    const url = api.apiURL(`/jezzwtf/refmods/thumb?name=${encodeURIComponent(entry.name)}&v=${entry.stamp}`);
    let t = thumbs.get(url);
    if (!t) {
        t = { img: new Image(), ok: false };
        t.img.onload = () => { t.ok = true; app.graph?.setDirtyCanvas(true, false); };
        t.img.src = url;
        thumbs.set(url, t);
    }
    return t.ok ? t.img : null;
}

// --------------------------------------------------------------------------- helpers

const isLinked = (node, name) => !!node.inputs?.find((i) => i.name === name && i.link != null);
const val = (node, name, d) => findWidget(node, name)?.value ?? d;
const modName = (node, i) => { const v = val(node, `mod_${i}`, NONE); return !v || v === NONE ? "" : String(v); };
const slotCount = (node) => clamp(node.properties?.jezzwtf_slots ?? 1, 1, MAX_SLOTS);

function highestUsedSlot(node) {
    let top = 1;
    for (let i = 1; i <= MAX_SLOTS; i++) if (modName(node, i)) top = i;
    return top;
}

function applyLabels(node, kind) {
    for (let i = 1; i <= MAX_SLOTS; i++) {
        for (const [base, label] of SLOT_LABELS) {
            const w = findWidget(node, `${base}_${i}`);
            if (w) w.label = i > 1 ? `${label} ${i}` : label;
        }
    }
    if (kind === "bake") for (const [k, label] of Object.entries(BAKE_LABELS)) { const w = findWidget(node, k); if (w) w.label = label; }
    const budget = findWidget(node, "max_total_tokens");
    if (budget) budget.label = "token budget";
}

function applyVisibility(node, kind) {
    if (kind === "bake") {
        const adv = !!node.properties.jezzwtf_adv;
        for (const n of ADV_NODE_WIDGETS.bake) setWidgetVisible(node, findWidget(node, n), adv);
    } else {
        const slots = slotCount(node), adv = !!node.properties.jezzwtf_adv;
        for (let i = 1; i <= MAX_SLOTS; i++) {
            const on = i <= slots;
            for (const base of ["mod", "visual_strength", "audio_strength"]) setWidgetVisible(node, findWidget(node, `${base}_${i}`), on);
            for (const base of ["strength", "copies", "components"]) setWidgetVisible(node, findWidget(node, `${base}_${i}`), on && adv);
        }
        for (const n of ADV_NODE_WIDGETS[kind]) setWidgetVisible(node, findWidget(node, n), adv);
    }
    node.setSize([Math.max(node.size[0], 320), node.computeSize()[1]]);
    node.setDirtyCanvas(true, true);
}

function panelHeight(node, kind) {
    if (kind === "bake") return TOOLBAR_H + CARD_H + 30;
    const rows = slotCount(node) * CARD_H;
    return TOOLBAR_H + rows + METER_H + (kind === "apply" ? CURVE_H : 0) + 8;
}

// --------------------------------------------------------------------------- drawing primitives

function rr(ctx, x, y, w, h, r) {
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y, w, h, r); else ctx.rect(x, y, w, h);
}

function chip(ctx, x, y, text, lit, color) {
    ctx.font = "bold 9px system-ui, sans-serif";
    const w = ctx.measureText(text).width + 10;
    rr(ctx, x, y, w, 14, 7);
    ctx.fillStyle = lit ? color : "rgba(255,255,255,.07)";
    ctx.fill();
    ctx.fillStyle = lit ? "#10131a" : "#6d7280";
    ctx.textAlign = "left";
    ctx.fillText(text, x + 5, y + 10.5);
    return w + 4;
}

function waveform(ctx, x, y, w, h, peaks, color) {
    const bars = 24, bw = w / bars;
    for (let i = 0; i < bars; i++) {
        let v = 0.12;
        if (peaks?.length) {
            const a = Math.floor(i * peaks.length / bars), b = Math.max(a + 1, Math.floor((i + 1) * peaks.length / bars));
            v = Math.max(0.08, ...peaks.slice(a, b));
        }
        const bh = Math.max(2, v * h);
        ctx.fillStyle = color;
        ctx.fillRect(x + i * bw + 1, y + (h - bh) / 2, Math.max(1, bw - 2), bh);
    }
}

function drawThumb(ctx, x, y, s, entry, name) {
    rr(ctx, x, y, s, s, 6);
    const img = thumbFor(entry);
    ctx.save();
    ctx.clip();
    if (img) ctx.drawImage(img, x, y, s, s);
    else {
        const g = ctx.createLinearGradient(x, y, x + s, y + s);
        g.addColorStop(0, "#3b4a7a");
        g.addColorStop(1, "#6a3b7a");
        ctx.fillStyle = g;
        ctx.fillRect(x, y, s, s);
        ctx.fillStyle = "#fff";
        ctx.font = "bold 20px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText((name || "?").replace(/^.*\//, "").charAt(0).toUpperCase() || "?", x + s / 2, y + s / 2 + 7);
    }
    ctx.restore();
}

// --------------------------------------------------------------------------- panel pieces

function drawToolbar(node, ctx, y, w, kind, hits) {
    const adv = !!node.properties.jezzwtf_adv;
    const buttons = [];
    if (kind !== "bake") {
        buttons.push(["add character", slotCount(node) < MAX_SLOTS, () => changeSlots(node, kind, +1)]);
        buttons.push(["remove", slotCount(node) > 1, () => changeSlots(node, kind, -1)]);
    }
    buttons.push([adv ? "advanced: on" : "advanced: off", true, () => toggleAdvanced(node, kind), adv]);
    let x = PAD;
    ctx.font = "11px system-ui, sans-serif";
    for (const [label, enabled, fn, on] of buttons) {
        const bw = ctx.measureText(label).width + 16;
        rr(ctx, x, y + 2, bw, TOOLBAR_H - 6, 6);
        ctx.fillStyle = on ? "#3c4f7a" : enabled ? "#2a2c33" : "#1d1e22";
        ctx.fill();
        ctx.strokeStyle = enabled ? "#4a4e5a" : "#2a2c33";
        ctx.stroke();
        ctx.fillStyle = enabled ? "#dfe2ea" : "#5b5f6a";
        ctx.textAlign = "left";
        ctx.fillText(label, x + 8, y + 16);
        if (enabled) hits.push({ x, y: y + 2, w: bw, h: TOOLBAR_H - 6, fn });
        x += bw + 6;
    }
}

function slotStats(node, i, entry) {
    const master = val(node, `strength_${i}`, 1), vs = val(node, `visual_strength_${i}`, 1);
    const as = val(node, `audio_strength_${i}`, 1), comp = val(node, `components_${i}`, "All");
    const copies = val(node, `copies_${i}`, 1);
    const face = !!entry && entry.faces > 0 && comp !== "Audio" && vs * master > 0;
    const voice = !!entry && (entry.audio_seconds > 0 || entry.audio_tokens > 0) && comp !== "Visual" && as * master > 0;
    const tokens = ((face ? entry.visual_tokens : 0) + (voice ? entry.audio_tokens : 0)) * copies;
    return { master, vs, as, copies, face, voice, tokens };
}

function drawSlotCard(node, ctx, y, w, i) {
    const name = modName(node, i);
    const entry = name ? library.entries.get(name) : null;
    rr(ctx, PAD, y + 2, w - PAD * 2, CARD_H - 4, 8);
    ctx.fillStyle = name ? "#20232b" : "#1a1c21";
    ctx.fill();
    ctx.strokeStyle = "#2f333d";
    ctx.stroke();
    if (!name) {
        ctx.fillStyle = "#5b5f6a";
        ctx.font = "11px system-ui, sans-serif";
        ctx.textAlign = "left";
        ctx.fillText(`slot ${i}: empty`, PAD + 12, y + CARD_H / 2 + 4);
        return 0;
    }
    const s = CARD_H - 12;
    drawThumb(ctx, PAD + 6, y + 6, s, entry, name);
    const st = slotStats(node, i, entry);
    const x0 = PAD + 6 + s + 8;
    ctx.fillStyle = "#e8eaf0";
    ctx.font = "bold 11px system-ui, sans-serif";
    ctx.textAlign = "left";
    const maxName = w - x0 - 80;
    let label = name.replace(/^.*\//, "");
    while (ctx.measureText(label).width > maxName && label.length > 3) label = label.slice(0, -2);
    ctx.fillText(label === name.replace(/^.*\//, "") ? label : `${label}...`, x0, y + 18);
    if (!entry) {
        ctx.fillStyle = "#f0b24a";
        ctx.font = "10px system-ui, sans-serif";
        ctx.fillText("not in the library", x0, y + 36);
        return 0;
    }
    let cx = x0;
    cx += chip(ctx, cx, y + 26, `FACE ${entry.faces} x ${Math.round(st.vs * 100)}%`, st.face, "#6ee7b7");
    chip(ctx, cx, y + 26, `VOICE ${entry.audio_seconds}s x ${Math.round(st.as * 100)}%`, st.voice, "#fbbf24");
    ctx.fillStyle = "#9aa1af";
    ctx.font = "10px system-ui, sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(`${st.tokens}${st.copies > 1 ? ` (x${st.copies})` : ""} tok`, w - PAD - 8, y + 18);
    waveform(ctx, x0, y + 42, w - x0 - PAD - 8, 9, entry.peaks, st.voice ? "#fbbf24" : "#4a4e5a");
    return st.tokens;
}

function drawMeter(node, ctx, y, w, total) {
    const budget = val(node, "max_total_tokens", 0);
    const cap = budget > 0 ? budget : SOFT_BUDGET;
    const over = total > cap;
    const bx = PAD, bw = w - PAD * 2;
    rr(ctx, bx, y + 6, bw, 8, 4);
    ctx.fillStyle = "#1a1c21";
    ctx.fill();
    rr(ctx, bx, y + 6, Math.max(4, bw * Math.min(1, total / cap)), 8, 4);
    ctx.fillStyle = over ? "#f06a6a" : "#6aa7ff";
    ctx.fill();
    ctx.fillStyle = over ? "#f06a6a" : "#9aa1af";
    ctx.font = "10px system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(`${total} / ${cap}${budget > 0 ? "" : " (soft)"} tokens${over ? " - over budget" : ""}`, bx, y + 24 - 2);
}

function drawBakeCard(node, ctx, y, w, hits) {
    const sub = String(val(node, "subfolder", "characters") || "").trim();
    const name = String(val(node, "name", "my_character")).trim();
    const full = sub ? `${sub}/${name}` : name;
    const entry = library.entries.get(full) ?? node._jzBaked ?? null;
    const images = isLinked(node, "images") || isLinked(node, "video_frames") || String(val(node, "folder", "")).trim() !== "";
    const audio = isLinked(node, "audio");
    rr(ctx, PAD, y + 2, w - PAD * 2, CARD_H - 4, 8);
    ctx.fillStyle = "#20232b";
    ctx.fill();
    ctx.strokeStyle = "#2f333d";
    ctx.stroke();
    const s = CARD_H - 12;
    drawThumb(ctx, PAD + 6, y + 6, s, entry?.name === full ? entry : null, name);
    const x0 = PAD + 6 + s + 8;
    ctx.fillStyle = "#e8eaf0";
    ctx.font = "bold 11px system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(name || "(unnamed)", x0, y + 18);
    let cx = x0;
    cx += chip(ctx, cx, y + 26, "FACES", images, "#6ee7b7");
    chip(ctx, cx, y + 26, "VOICE", audio, "#fbbf24");
    waveform(ctx, x0, y + 43, w - x0 - PAD - 8, 8, entry?.peaks, audio ? "#fbbf24" : "#4a4e5a");
    let status = "ready", color = "#6ee7b7";
    if (images && !isLinked(node, "vae")) { status = "connect the video VAE to bake the images"; color = "#f0b24a"; }
    else if (audio && !isLinked(node, "audio_vae")) { status = "connect the audio VAE to bake the audio"; color = "#f0b24a"; }
    else if (!images && !audio) { status = "connect images, a clip, a folder or audio"; color = "#9aa1af"; }
    else if (node._jzBaked) { status = `baked - ${(node._jzBaked.visual_tokens ?? 0) + (node._jzBaked.audio_tokens ?? 0)} tokens`; color = "#6aa7ff"; }
    ctx.fillStyle = color;
    ctx.font = "10px system-ui, sans-serif";
    ctx.fillText(status, PAD + 4, y + CARD_H + 14);
}

// --------------------------------------------------------------------------- curve editor (Apply)

function cycle(list, current, step) {
    const i = Math.max(0, list.indexOf(current));
    return list[(i + step + list.length) % list.length];
}

function setW(node, name, v) {
    const w = findWidget(node, name);
    if (!w) return;
    w.value = v;
    w.callback?.(v);
    node.setDirtyCanvas(true, true);
}

function drawCurveEditor(node, ctx, y, w, hits) {
    const dir = val(node, "curve_direction", "constant"), shape = val(node, "curve_shape", "linear");
    const value = val(node, "curve_value", 1);
    ctx.fillStyle = "#9aa1af";
    ctx.font = "10px system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("curve", PAD + 2, y + 12);
    let x = PAD + 36;
    for (const [text, key, list, cur] of [[dir.replace("concept_at_", "at "), "curve_direction", DIRECTIONS, dir],
        [shape, "curve_shape", SHAPES, shape]]) {
        const bw = ctx.measureText(text).width + 16;
        rr(ctx, x, y + 2, bw, 15, 7);
        ctx.fillStyle = "#2a2c33";
        ctx.fill();
        ctx.strokeStyle = "#4a4e5a";
        ctx.stroke();
        ctx.fillStyle = "#dfe2ea";
        ctx.fillText(text, x + 8, y + 13);
        hits.push({ x, y: y + 2, w: bw, h: 15, fn: (e) => setW(node, key, cycle(list, cur, e.shiftKey ? -1 : 1)) });
        x += bw + 6;
    }
    ctx.textAlign = "right";
    ctx.fillText(`value ${value.toFixed(2)}`, w - PAD - 2, y + 12);
    const px = PAD, py = y + 22, pw = w - PAD * 2, ph = CURVE_H - 34;
    rr(ctx, px, py, pw, ph, 6);
    ctx.fillStyle = "#14161a";
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,.06)";
    for (let g = 1; g < 4; g++) { ctx.beginPath(); ctx.moveTo(px, py + ph * g / 4); ctx.lineTo(px + pw, py + ph * g / 4); ctx.stroke(); }
    const frames = 48;
    const c = directionCurve(dir, shape, value, frames) ?? new Array(frames).fill(1);
    ctx.beginPath();
    c.forEach((v, i) => {
        const cx = px + 4 + (pw - 8) * i / (frames - 1), cy = py + ph - 4 - (ph - 8) * v;
        if (i) ctx.lineTo(cx, cy); else ctx.moveTo(cx, cy);
    });
    ctx.strokeStyle = "#6aa7ff";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.lineWidth = 1;
    ctx.fillStyle = "#6d7280";
    ctx.textAlign = "left";
    ctx.fillText("first frame", px + 4, py + ph - 3);
    ctx.textAlign = "right";
    ctx.fillText("last frame", px + pw - 4, py + ph - 3);
    hits.push({ x: px, y: py, w: pw, h: ph, drag: (pos) => setW(node, "curve_value", Math.round(clamp(1 - (pos[1] - py - 4) / (ph - 8), 0, 1) * 100) / 100) });
}

// --------------------------------------------------------------------------- actions

function changeSlots(node, kind, delta) {
    let n = slotCount(node);
    if (delta < 0 && n > 1) { setW(node, `mod_${n}`, NONE); n -= 1; }
    else if (delta > 0 && n < MAX_SLOTS) n += 1;
    node.properties.jezzwtf_slots = n;
    applyVisibility(node, kind);
}

function toggleAdvanced(node, kind) {
    node.properties.jezzwtf_adv = !node.properties.jezzwtf_adv;
    applyVisibility(node, kind);
}

// --------------------------------------------------------------------------- node wiring

function drawPanel(node, ctx, kind) {
    if (node.flags?.collapsed) return;
    refreshLibrary(false);
    const w = node.size[0], h = panelHeight(node, kind);
    let y = node.size[1] - h;
    const hits = [];
    drawToolbar(node, ctx, y, w, kind, hits);
    y += TOOLBAR_H;
    if (kind === "bake") drawBakeCard(node, ctx, y, w, hits);
    else {
        let total = 0;
        for (let i = 1; i <= slotCount(node); i++) { total += drawSlotCard(node, ctx, y, w, i); y += CARD_H; }
        drawMeter(node, ctx, y, w, total);
        y += METER_H;
        if (kind === "apply") drawCurveEditor(node, ctx, y + 4, w, hits);
    }
    node._jzHits = hits;
}

function setup(node, kind) {
    node.properties = node.properties ?? {};
    node.properties.jezzwtf_slots = clamp(node.properties.jezzwtf_slots ?? 1, 1, MAX_SLOTS);
    node.properties.jezzwtf_adv = !!node.properties.jezzwtf_adv;
    applyLabels(node, kind);
    if (kind !== "bake") {
        node.properties.jezzwtf_slots = Math.max(slotCount(node), highestUsedSlot(node));
        for (let i = 1; i <= MAX_SLOTS; i++) for (const base of ["mod", "visual_strength", "audio_strength", "strength", "copies", "components"]) {
            onWidget(findWidget(node, `${base}_${i}`), () => node.setDirtyCanvas(true, false));
        }
    } else for (const n of ["name", "subfolder", "folder", "overwrite"]) onWidget(findWidget(node, n), () => node.setDirtyCanvas(true, false));
    applyVisibility(node, kind);
    refreshLibrary(true);
}

app.registerExtension({
    name: "JezzWTF.RefMod.Cards",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const kind = KINDS[nodeData.name];
        if (!kind) return;
        const proto = nodeType.prototype;
        chain(proto, "onNodeCreated", function () { setup(this, kind); });
        chain(proto, "onConfigure", function () {
            this.properties = this.properties ?? {};
            if (kind !== "bake") this.properties.jezzwtf_slots = Math.max(slotCount(this), highestUsedSlot(this));
            applyLabels(this, kind);
            applyVisibility(this, kind);
            refreshLibrary(true);
        });
        chain(proto, "onConnectionsChange", function () { this.setDirtyCanvas(true, false); });
        chain(proto, "onDrawForeground", function (ctx) { drawPanel(this, ctx, kind); });
        const computeSize = proto.computeSize;
        proto.computeSize = function () {
            const s = computeSize ? computeSize.apply(this, arguments) : [320, 60];
            return [Math.max(320, s[0]), s[1] + panelHeight(this, kind)];
        };
        chain(proto, "onMouseDown", function (e, pos) {
            for (const hit of this._jzHits ?? []) {
                if (pos[0] < hit.x || pos[0] > hit.x + hit.w || pos[1] < hit.y || pos[1] > hit.y + hit.h) continue;
                if (hit.fn) { hit.fn(e); return true; }
                if (hit.drag) {
                    hit.drag(pos);
                    const move = (ev) => {
                        const p = app.canvas.convertEventToCanvasOffset(ev);
                        hit.drag([p[0] - this.pos[0], p[1] - this.pos[1]]);
                    };
                    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
                    window.addEventListener("pointermove", move);
                    window.addEventListener("pointerup", up);
                    return true;
                }
            }
            return false;
        });
        chain(proto, "getExtraMenuOptions", function (_canvas, options) {
            const extra = [];
            if (kind !== "bake") {
                if (slotCount(this) < MAX_SLOTS) extra.push({ content: "Add character", callback: () => changeSlots(this, kind, +1) });
                if (slotCount(this) > 1) extra.push({ content: "Remove character", callback: () => changeSlots(this, kind, -1) });
            }
            extra.push({ content: this.properties.jezzwtf_adv ? "Advanced: off" : "Advanced: on", callback: () => toggleAdvanced(this, kind) });
            options.unshift(...extra, null);
        });
        if (kind === "bake") {
            chain(proto, "onExecuted", function (message) {
                const entry = message?.refmod_entry?.[0];
                if (entry) this._jzBaked = entry;
                setTimeout(() => { refreshLibrary(true); app.refreshComboInNodes?.(); }, 250);
            });
        }
    },
});
