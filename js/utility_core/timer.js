import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { chain } from "./_shared.js";
import { attributeItems, pathMatches } from "./timer_core.js";

// Batch Timer: a stopwatch drawn straight on the node canvas. The server counts finished
// items (`jezzwtf.timer_update`); this file owns the clock, the stats and the backdrop.

const TYPE = "JWTFTimer";
const EVENT = "jezzwtf.timer_update";
const GPU_SETTING = "JezzWTF.Timer.WebGPU";
const BEEP_SETTING = "JezzWTF.Timer.Beep";
const ACCENTS = ["#4ade80", "#00bfff", "#ffcc00", "#ff007f", "#ffffff"];
const TINT = { DONE: "#4ade80", INTERRUPTED: "#f59e0b", ERROR: "#ff00aa" };
const MIN_W = 300;
const MIN_BODY_H = 190;
const MAX_DURATIONS = 64;

const timers = new Set();
let lastQueueRemaining; // undefined until the first `status` event
let resumed = false;

// ---- state ----------------------------------------------------------------------------

function freshState() {
    return {
        state: "READY", paused: false,
        base: 0, syncAt: 0, // elapsed seconds at `syncAt` (performance.now ms)
        current: 0, total: 0, durations: [], lastItemAt: 0, runId: "", pendingReset: false,
        finishedAt: 0, pulseAt: 0, shown: 0, idleTimer: 0,
    };
}

const now = () => performance.now();
const isLive = (t) => t.state === "RUNNING" && !t.paused;

function elapsed(t) {
    return isLive(t) ? t.base + (now() - t.syncAt) / 1000 : t.base;
}

function totalOf(node, t) {
    return t.total || Number(node.widgets?.find((w) => w.name === "total_images")?.value) || 1;
}

function startRun(t, atElapsed = 0) {
    Object.assign(t, freshState(), { state: "RUNNING", base: atElapsed, syncAt: now(), lastItemAt: now() });
    ensureLoop();
}

function settingOn(id, fallback) {
    try {
        const v = app.extensionManager?.setting?.get?.(id) ?? app.ui?.settings?.getSettingValue?.(id);
        return v == null ? fallback : !!v;
    } catch {
        return fallback;
    }
}

function beep() {
    try {
        const ctx = new AudioContext();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = 880;
        gain.gain.setValueAtTime(0.2, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
        osc.connect(gain).connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + 0.6);
        osc.onended = () => ctx.close();
    } catch { /* audio blocked */ }
}

const isComplete = (t) => t.total > 0 && t.current >= t.total;

const rootGraph = () => app.rootGraph ?? app.graph;

function postResetIds(ids) {
    api.fetchApi("/jezzwtf/timer/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_ids: ids }),
    }).catch(() => { /* server unreachable */ });
}

/** Exact server keys of this node: its own id at the root, plus every execution path seen for it. */
function postReset(node) {
    const ids = new Set(node._jwtfPaths ?? []);
    if (!node.graph || node.graph === rootGraph()) ids.add(String(node.id));
    postResetIds([...ids]);
}

function finish(node, state) {
    const t = node._jwtfTimer;
    if (t.state !== "RUNNING") return;
    t.base = elapsed(t);
    t.paused = false;
    t.state = state;
    t.finishedAt = Date.now() / 1000;
    if (state === "DONE") {
        t.current = t.total = totalOf(node, t);
        if (settingOn(BEEP_SETTING, false)) beep();
        postReset(node);
    } else if (lastQueueRemaining === 0) {
        postReset(node); // the run died and nothing is queued: the server must not carry its counts forward
    } else {
        t.pendingReset = true; // more prompts are queued; reset once the queue drains (see onStatus)
    }
    ensureLoop();
    node.setDirtyCanvas(true, false);
}

function resetNode(node) {
    node._jwtfTimer = freshState();
    postReset(node);
    ensureLoop();
    node.setDirtyCanvas(true, false);
}

function matchesId(node, id) {
    if (!pathMatches(node, id, rootGraph())) return false;
    (node._jwtfPaths ??= new Set()).add(String(id));
    return true;
}

function applyUpdate(node, d) {
    const t = node._jwtfTimer;
    const cur = Number(d.current), total = Number(d.total);
    let late = false;
    const runId = typeof d.run_id === "string" ? d.run_id : "";
    if (t.state !== "RUNNING" || cur < t.current || (runId && t.runId && runId !== t.runId)) {
        startRun(t, Math.max(0, Number(d.now) - Number(d.started_at)));
        late = true;
        t.current = Math.max(0, cur - 1);
    }
    if (runId) t.runId = runId;
    t.total = total;
    const n = cur - t.current;
    if (n > 0) {
        if (late) t.lastItemAt = now();
        else attributeItems(t, n, now(), MAX_DURATIONS);
        t.pulseAt = now();
    }
    t.current = cur;
    ensureLoop();
    node.setDirtyCanvas(true, false);
}

// ---- stats ----------------------------------------------------------------------------

export function averagePerItem(t, el) {
    if (t.state === "DONE") return t.current > 0 ? el / t.current : 0;
    let d = t.durations.slice(-10);
    if (d.length >= 2) d = d.slice(1); // drop the warm-up item
    return d.length ? d.reduce((a, b) => a + b, 0) / d.length : 0;
}

function etaOf(t, avg) {
    if (t.state !== "RUNNING" || t.paused || t.current === 0) return 0;
    return Math.max(0, t.total - t.current) * avg;
}

function fmt(sec) {
    sec = Math.max(0, sec);
    const hh = Math.floor(sec / 3600), mm = Math.floor((sec % 3600) / 60), ss = Math.floor(sec % 60);
    return [hh, mm, ss].map((v) => String(v).padStart(2, "0")).join(":");
}

function fmtShort(sec) {
    if (!(sec > 0)) return "--";
    const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
    return m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m` : m > 0 ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}

const clock = (epochSec) => new Date(epochSec * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

// ---- redraw loop ----------------------------------------------------------------------

let loop = 0;
function animating(node) {
    const t = node._jwtfTimer;
    const target = t.total > 0 ? t.current / t.total : 0;
    return t.state === "RUNNING" || Math.abs(t.shown - target) > 0.002 || now() - t.pulseAt < 900;
}

function ensureLoop() {
    if (loop) return;
    loop = setInterval(() => {
        const any = [...timers].some(animating);
        app.canvas?.setDirty?.(true, true);
        if (!any) {
            clearInterval(loop);
            loop = 0;
        }
    }, 33);
}

// ---- backdrop -------------------------------------------------------------------------

const WGSL = /* wgsl */ `
struct U { res: vec2f, t: f32, energy: f32, accent: vec3f, progress: f32, pulse: f32, mode: f32, pad: vec2f };
@group(0) @binding(0) var<uniform> u: U;
@vertex fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {
  var p = array<vec2f, 3>(vec2f(-1.0, -1.0), vec2f(3.0, -1.0), vec2f(-1.0, 3.0));
  return vec4f(p[i], 0.0, 1.0);
}
fn hash(p: vec2f) -> f32 { return fract(sin(dot(p, vec2f(127.1, 311.7))) * 43758.5453); }
fn noise(p: vec2f) -> f32 {
  let i = floor(p); let f = fract(p); let s = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2f(1.0, 0.0)), s.x), mix(hash(i + vec2f(0.0, 1.0)), hash(i + vec2f(1.0, 1.0)), s.x), s.y);
}
fn fbm(p: vec2f) -> f32 {
  var v = 0.0; var a = 0.5; var q = p;
  for (var k = 0; k < 4; k++) { v += a * noise(q); q = q * 2.03 + vec2f(1.7, 9.2); a *= 0.5; }
  return v;
}
@fragment fn fs(@builtin(position) pos: vec4f) -> @location(0) vec4f {
  let uv = pos.xy / u.res;
  let asp = u.res.x / u.res.y;
  let p = vec2f(uv.x * asp, uv.y) * 2.0;
  let t = u.t * 0.15 * (0.4 + u.energy);
  let w = vec2f(fbm(p + vec2f(t, 0.0)), fbm(p + vec2f(0.0, -t) + 3.1));
  let f = fbm(p + 1.8 * w + t);
  var col = mix(vec3f(0.06, 0.07, 0.09), u.accent * 0.55, f * f * (0.4 + 0.8 * u.energy));
  let bot = 1.0 - uv.y;
  col += u.accent * smoothstep(0.035, 0.0, bot) * step(uv.x, u.progress) * 0.9;
  let hd = (uv.x - u.progress) * asp * 14.0;
  col += u.accent * exp(-hd * hd) * exp(-bot * 30.0) * 0.8;
  let rd = distance(uv * vec2f(asp, 1.0), vec2f(u.progress * asp, 1.0));
  let rr = (rd - (1.0 - u.pulse) * 0.9) * 10.0;
  col += u.accent * u.pulse * exp(-rr * rr) * 0.5;
  if (u.mode > 0.5 && u.mode < 1.5) { col = vec3f(dot(col, vec3f(0.3, 0.59, 0.11))); }
  if (u.mode > 1.5) { col = mix(col, vec3f(0.9, 0.05, 0.1) * (0.3 + 0.7 * noise(vec2f(u.t * 30.0, 0.0))), 0.35); }
  return vec4f(col, 1.0);
}`;

const gpu = { state: "idle", device: null, pipeline: null, bind: null, buf: null, canvas: null, ctx: null, format: "" };

async function initGpu() {
    gpu.state = "loading";
    try {
        if (!navigator.gpu || typeof OffscreenCanvas === "undefined") throw new Error("WebGPU unavailable");
        const adapter = await navigator.gpu.requestAdapter();
        const device = await adapter?.requestDevice();
        if (!device) throw new Error("no device");
        device.lost.then(() => { gpu.state = "failed"; });
        gpu.format = navigator.gpu.getPreferredCanvasFormat();
        device.pushErrorScope("validation");
        const module = device.createShaderModule({ code: WGSL });
        const pipeline = device.createRenderPipeline({
            layout: "auto",
            vertex: { module, entryPoint: "vs" },
            fragment: { module, entryPoint: "fs", targets: [{ format: gpu.format }] },
        });
        const buf = device.createBuffer({ size: 48, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
        const bind = device.createBindGroup({ layout: pipeline.getBindGroupLayout(0), entries: [{ binding: 0, resource: { buffer: buf } }] });
        const err = await device.popErrorScope();
        if (err) throw new Error(err.message);
        gpu.canvas = new OffscreenCanvas(2, 2);
        gpu.ctx = gpu.canvas.getContext("webgpu");
        if (!gpu.ctx) throw new Error("no webgpu context");
        Object.assign(gpu, { device, pipeline, buf, bind, state: "ready" });
    } catch (e) {
        console.info("[JezzWTF] Timer backdrop: using 2D fallback:", e?.message ?? e);
        gpu.state = "failed";
    }
}

function hexRgb(hex) {
    const n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => v / 255);
}

/** Render the GPU backdrop into the offscreen canvas and blit it. Returns false to use 2D. */
function drawGpuBackdrop(ctx, node, x, y, w, h, tint, t) {
    if (gpu.state === "idle") initGpu();
    if (gpu.state !== "ready" || app.canvas?.low_quality || !settingOn(GPU_SETTING, true)) return false;
    try {
        const cw = Math.max(2, Math.round(w / 2)), ch = Math.max(2, Math.round(h / 2));
        if (gpu.canvas.width !== cw || gpu.canvas.height !== ch) {
            gpu.canvas.width = cw;
            gpu.canvas.height = ch;
        }
        gpu.ctx.configure({ device: gpu.device, format: gpu.format, alphaMode: "opaque" });
        const live = isLive(t);
        const energy = { RUNNING: t.paused ? 0.15 : 1, READY: 0.2, DONE: 0.5, INTERRUPTED: 0.3, ERROR: 0.9 }[t.state] ?? 0.3;
        const pulse = Math.max(0, 1 - (now() - t.pulseAt) / 900);
        const mode = t.state === "ERROR" ? 2 : t.paused ? 1 : 0;
        const [r, g, b] = hexRgb(tint);
        gpu.device.queue.writeBuffer(gpu.buf, 0, new Float32Array([
            cw, ch, now() / 1000, live ? energy : energy * 0.6, r, g, b, t.shown, pulse, mode, 0, 0]));
        const enc = gpu.device.createCommandEncoder();
        const pass = enc.beginRenderPass({ colorAttachments: [{
            view: gpu.ctx.getCurrentTexture().createView(), loadOp: "clear", storeOp: "store", clearValue: [0, 0, 0, 1] }] });
        pass.setPipeline(gpu.pipeline);
        pass.setBindGroup(0, gpu.bind);
        pass.draw(3);
        pass.end();
        gpu.device.queue.submit([enc.finish()]);
        ctx.drawImage(gpu.canvas, x, y, w, h);
        return true;
    } catch (e) {
        console.info("[JezzWTF] Timer backdrop failed, using 2D:", e?.message ?? e);
        gpu.state = "failed";
        return false;
    }
}

function drawFallbackBackdrop(ctx, x, y, w, h, tint, t) {
    const rg = ctx.createRadialGradient(x + w / 2, y + h * 0.35, 0, x + w / 2, y + h * 0.35, w * 0.6);
    rg.addColorStop(0, tint + (t.state === "READY" ? "18" : "30"));
    rg.addColorStop(1, "transparent");
    ctx.fillStyle = rg;
    ctx.fillRect(x, y, w, h);
    const lg = ctx.createLinearGradient(0, y, 0, y + h);
    lg.addColorStop(0, "transparent");
    lg.addColorStop(1, "#0007");
    ctx.fillStyle = lg;
    ctx.fillRect(x, y, w, h);
}

// ---- drawing --------------------------------------------------------------------------

function rr(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.roundRect(x, y, w, h, r);
}

function bodyTop(node) {
    const last = node.widgets?.[node.widgets.length - 1];
    return last ? (last.last_y ?? 40) + 28 : 40;
}

function draw(node, ctx) {
    const t = node._jwtfTimer;
    node._jwtfHits = [];
    if (node.flags?.collapsed) return;
    const top = bodyTop(node);
    const W = node.size[0] - 8;
    const H = node.size[1] - top - 6;
    if (W < 140 || H < 100) return;
    const X = 4;
    const k = Math.max(0.75, Math.min(1.7, Math.min(W / 300, H / 190)));
    const accent = ACCENTS.includes(node.properties?.accent) ? node.properties.accent : ACCENTS[0];
    const tint = TINT[t.state] ?? accent;
    const live = isLive(t);
    const el = elapsed(t);
    const total = totalOf(node, t);
    const target = total > 0 ? Math.min(1, t.current / total) : 0;
    t.shown += (target - t.shown) * 0.2;
    const blink = Math.floor(Date.now() / 500) % 2 === 0;
    const pad = 10 * k;

    ctx.save();
    ctx.translate(X, top);
    rr(ctx, 0, 0, W, H, 8 * k);
    ctx.fillStyle = "#15171c";
    ctx.fill();
    ctx.save();
    ctx.clip();
    if (!drawGpuBackdrop(ctx, node, 0, 0, W, H, tint, t)) drawFallbackBackdrop(ctx, 0, 0, W, H, tint, t);
    ctx.restore();

    // top row: brand + status chip
    ctx.textBaseline = "middle";
    ctx.textAlign = "left";
    ctx.font = `700 ${10 * k}px system-ui`;
    ctx.fillStyle = "#9aa0ad";
    ctx.fillText("BATCH TIMER", pad, pad + 3 * k);
    const label = t.state === "RUNNING" && t.paused ? "PAUSED" : t.state;
    ctx.textAlign = "right";
    ctx.fillStyle = tint;
    ctx.fillText(label, W - pad, pad + 3 * k);
    const lw = ctx.measureText(label).width;
    ctx.globalAlpha = live ? 0.5 + 0.5 * Math.sin(Date.now() / 200) : 1;
    ctx.beginPath();
    ctx.arc(W - pad - lw - 8 * k, pad + 3 * k, 3.5 * k, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;

    // clock
    const parts = fmt(el).split(":");
    const tenth = Math.floor((el % 1) * 10);
    const main = parts.join(live && !blink ? " " : ":");
    ctx.font = `700 ${30 * k}px ui-monospace, Consolas, monospace`;
    const mw = ctx.measureText(main).width;
    ctx.font = `600 ${16 * k}px ui-monospace, Consolas, monospace`;
    const tw = ctx.measureText(`.${tenth}`).width;
    const cx = (W - mw - tw) / 2;
    const cy = pad + 30 * k;
    ctx.textAlign = "left";
    ctx.fillStyle = "#f2f4f8";
    ctx.globalAlpha = t.state === "READY" ? 0.55 : 1;
    ctx.font = `700 ${30 * k}px ui-monospace, Consolas, monospace`;
    ctx.fillText(main, cx, cy);
    ctx.font = `600 ${16 * k}px ui-monospace, Consolas, monospace`;
    ctx.globalAlpha *= 0.7;
    ctx.fillText(`.${tenth}`, cx + mw, cy + 5 * k);
    ctx.globalAlpha = 1;

    // readout + percent + progress bar
    const ry = cy + 24 * k;
    ctx.font = `600 ${11 * k}px system-ui`;
    ctx.fillStyle = "#c9ccd4";
    ctx.textAlign = "left";
    ctx.fillText(`${t.current} / ${total}`, pad, ry);
    ctx.textAlign = "right";
    ctx.fillText(`${Math.floor(target * 100)}%`, W - pad, ry);
    const by = ry + 9 * k, bh = 7 * k, bw = W - pad * 2;
    rr(ctx, pad, by, bw, bh, bh / 2);
    ctx.fillStyle = "#ffffff18";
    ctx.fill();
    if (t.shown > 0.002) {
        rr(ctx, pad, by, Math.max(bh, bw * t.shown), bh, bh / 2);
        ctx.fillStyle = tint;
        ctx.fill();
    } else if (t.state === "RUNNING" && !t.paused) {
        const sweep = ((Date.now() % 1400) / 1400) * (bw + 40 * k) - 40 * k;
        ctx.save();
        rr(ctx, pad, by, bw, bh, bh / 2);
        ctx.clip();
        ctx.fillStyle = tint + "88";
        ctx.fillRect(pad + sweep, by, 40 * k, bh);
        ctx.restore();
    }

    // stats
    const avg = averagePerItem(t, el);
    const eta = etaOf(t, avg);
    const done = t.state === "DONE";
    const stats = [
        ["AVG/IT", avg > 0 ? fmtShort(avg) : "--"],
        ["ETA", live && t.current > 0 ? fmtShort(eta) : "--"],
        [done ? "TOTAL" : "EST. TOTAL", done ? fmtShort(el) : t.current > 0 && live ? fmtShort(el + eta) : "--"],
        [done ? "FINISHED" : "FINISH", done && t.finishedAt ? clock(t.finishedAt) : live && t.current > 0 ? clock(Date.now() / 1000 + eta) : "--"],
    ];
    const sy = by + bh + 14 * k;
    const colW = bw / 4;
    ctx.textAlign = "center";
    stats.forEach(([name, value], i) => {
        const x = pad + colW * i + colW / 2;
        ctx.font = `700 ${8 * k}px system-ui`;
        ctx.fillStyle = "#8b8f99";
        ctx.fillText(name, x, sy);
        ctx.font = `600 ${11 * k}px ui-monospace, Consolas, monospace`;
        ctx.fillStyle = "#e6e8ee";
        ctx.fillText(value, x, sy + 13 * k);
    });

    // bottom row: swatches + PAUSE/RESUME + RESET
    const fy = H - 14 * k;
    const sw = 12 * k;
    ACCENTS.forEach((c, i) => {
        const x = pad + i * (sw + 5 * k);
        rr(ctx, x, fy - sw / 2, sw, sw, 3 * k);
        ctx.fillStyle = c;
        ctx.fill();
        if (c === accent) {
            ctx.strokeStyle = "#fff";
            ctx.lineWidth = 1.5;
            ctx.stroke();
        }
        node._jwtfHits.push({ x: X + x, y: top + fy - sw / 2, w: sw, h: sw, act: () => {
            node.properties = node.properties ?? {};
            node.properties.accent = c;
            node.graph?.change?.();
        } });
    });
    const button = (text, right, enabled, act) => {
        ctx.font = `700 ${9.5 * k}px system-ui`;
        const bw2 = ctx.measureText(text).width + 14 * k;
        const bx = right - bw2;
        rr(ctx, bx, fy - 9 * k, bw2, 18 * k, 5 * k);
        ctx.fillStyle = enabled ? "#2a2c33" : "#1d1e22";
        ctx.fill();
        ctx.strokeStyle = enabled ? "#3a3d46" : "#26282d";
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.fillStyle = enabled ? "#e6e8ee" : "#555";
        ctx.textAlign = "center";
        ctx.fillText(text, bx + bw2 / 2, fy);
        if (enabled) node._jwtfHits.push({ x: X + bx, y: top + fy - 9 * k, w: bw2, h: 18 * k, act });
        return bx - 6 * k;
    };
    const next = button("RESET", W - pad, true, () => resetNode(node));
    button(t.paused ? "RESUME" : "PAUSE", next, t.state === "RUNNING", () => {
        if (t.paused) {
            t.syncAt = now();
            t.paused = false;
        } else {
            t.base = elapsed(t);
            t.paused = true;
        }
        ensureLoop();
    });
    ctx.restore();
}

function hit(node, pos) {
    return node._jwtfHits?.find((r) => pos[0] >= r.x && pos[0] <= r.x + r.w && pos[1] >= r.y && pos[1] <= r.y + r.h);
}

// ---- resume after reload ----------------------------------------------------------------

async function resumeFromServer() {
    if (resumed) return;
    resumed = true;
    try {
        const res = await api.fetchApi("/jezzwtf/timer/state");
        if (!res.ok) return;
        const { now: serverNow, runs } = await res.json();
        for (const node of timers) {
            const t = node._jwtfTimer;
            if (t.state !== "READY") continue;
            const key = Object.keys(runs ?? {}).find((id) => matchesId(node, id));
            const run = key ? runs[key] : null;
            if (!run?.active) continue;
            if (run.stale || lastQueueRemaining === 0) {
                postResetIds([key]); // abandoned run: never resume it as RUNNING
                continue;
            }
            startRun(t, Math.max(0, serverNow - run.started_at));
            t.runId = typeof run.run_id === "string" ? run.run_id : "";
            t.total = run.total;
            t.current = run.completed;
            const stamps = [run.started_at, ...run.stamps];
            t.durations = stamps.slice(1).map((s, i) => s - stamps[i]).slice(-MAX_DURATIONS);
            const lastStamp = stamps[stamps.length - 1];
            t.lastItemAt = now() - Math.max(0, serverNow - lastStamp) * 1000;
        }
    } catch { /* server unreachable: stay READY */ }
}

// ---- extension --------------------------------------------------------------------------

function onStatus(detail) {
    const info = detail?.exec_info ?? detail?.status?.exec_info;
    if (!info || typeof info.queue_remaining !== "number") return;
    lastQueueRemaining = info.queue_remaining;
    for (const node of timers) {
        const t = node._jwtfTimer;
        clearTimeout(t.idleTimer);
        if (info.queue_remaining === 0 && t.pendingReset) {
            t.pendingReset = false;
            postReset(node);
        }
        if (info.queue_remaining !== 0 || t.state !== "RUNNING") continue;
        t.idleTimer = setTimeout(() => {
            if (lastQueueRemaining === 0) finish(node, isComplete(t) ? "DONE" : "INTERRUPTED");
        }, 1500);
    }
}

app.registerExtension({
    name: "JezzWTF.UtilityCore.Timer",
    settings: [
        { id: GPU_SETTING, name: "Batch Timer: WebGPU backdrop", type: "boolean", defaultValue: true,
            category: ["JezzWTF", "Batch Timer", "WebGPU"] },
        { id: BEEP_SETTING, name: "Batch Timer: beep when done", type: "boolean", defaultValue: false,
            category: ["JezzWTF", "Batch Timer", "Beep"] },
    ],

    setup() {
        api.addEventListener("execution_start", () => {
            let armed = false;
            for (const node of timers) {
                if ((node.mode ?? 0) === 0 && node._jwtfTimer.state !== "RUNNING") {
                    startRun(node._jwtfTimer, 0);
                    armed = true;
                }
            }
            // Tell the server when the batch really began, so late joiners count item 1.
            if (armed) api.fetchApi("/jezzwtf/timer/arm", { method: "POST" }).catch(() => { /* offline */ });
        });
        api.addEventListener(EVENT, (e) => {
            const d = e.detail ?? {};
            for (const node of timers) if (matchesId(node, d.node_id)) applyUpdate(node, d);
        });
        api.addEventListener("execution_success", () => {
            for (const node of timers) {
                const t = node._jwtfTimer;
                if (t.state !== "RUNNING") continue;
                if (t.current >= totalOf(node, t) && t.current > 0) finish(node, "DONE");
                else if (t.current === 0) resetNode(node); // armed, but this node never fired
            }
        });
        api.addEventListener("execution_error", () => { for (const n of timers) finish(n, "ERROR"); });
        api.addEventListener("execution_interrupted", () => { for (const n of timers) finish(n, "INTERRUPTED"); });
        api.addEventListener("status", (e) => onStatus(e.detail));
    },

    afterConfigureGraph() {
        setTimeout(resumeFromServer, 0);
    },

    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== TYPE) return;
        chain(nodeType.prototype, "onNodeCreated", function () {
            this._jwtfTimer = freshState();
            this.properties = this.properties ?? {};
            this.properties.accent = this.properties.accent ?? ACCENTS[0];
            timers.add(this);
            const minH = this.computeSize()[1] + MIN_BODY_H;
            this.setSize([Math.max(this.size[0], MIN_W), Math.max(this.size[1], minH)]);
        });
        chain(nodeType.prototype, "onResize", function (size) {
            size[0] = Math.max(size[0], MIN_W);
            size[1] = Math.max(size[1], this.computeSize()[1] + MIN_BODY_H);
        });
        chain(nodeType.prototype, "onDrawForeground", function (ctx) { draw(this, ctx); });
        chain(nodeType.prototype, "onRemoved", function () {
            clearTimeout(this._jwtfTimer?.idleTimer);
            timers.delete(this);
        });
        const origDown = nodeType.prototype.onMouseDown;
        nodeType.prototype.onMouseDown = function (e, pos, canvas) {
            const r = hit(this, pos);
            if (r) {
                r.act();
                this.setDirtyCanvas(true, false);
                return true;
            }
            return origDown?.call(this, e, pos, canvas);
        };
        const origMove = nodeType.prototype.onMouseMove;
        nodeType.prototype.onMouseMove = function (e, pos, canvas) {
            const el = app.canvas?.canvas;
            if (el) el.style.cursor = hit(this, pos) ? "pointer" : "";
            return origMove?.call(this, e, pos, canvas);
        };
    },
});
