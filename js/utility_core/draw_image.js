import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { chain, findWidget, h, hideWidget, injectCss, onWidget } from "./_shared.js";
import { collidesWithOther, dropTexture } from "./draw_core.js";

// Draw Image: a layered sketch pad that saves a flattened PNG the Python node loads like
// Load Image. Layers, undo, zoom/pan, pressure, WebGPU compositing (2D fallback) and
// debounced serial uploads to input/jezzwtf_draw/.

const TYPE = "JWTFDrawImage";
const SUBFOLDER = "jezzwtf_draw";
const MAX_LAYERS = 12;
const MAX_UNDO = 25;
const SAVE_DELAY = 700;
const SWATCHES = ["#000000", "#ffffff", "#e53935", "#fb8c00", "#fdd835", "#43a047", "#1e88e5", "#8e24aa"];
const MIN_ZOOM = 1;
const MAX_ZOOM = 40;

injectCss("jwtf-draw", `
.jwtf-dr { box-sizing: border-box; width: 100%; height: 100%; display: flex; flex-direction: column; gap: 6px;
  padding: 6px; background: #1b1c20; border: 1px solid #2c2e35; border-radius: 8px; color: #ddd;
  font: 12px system-ui, sans-serif; position: relative; overflow: hidden; user-select: none; }
.jwtf-dr-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.jwtf-dr-bar .sep { width: 1px; height: 18px; background: #3a3d46; }
.jwtf-dr-main { display: flex; gap: 6px; flex: 1 1 auto; min-height: 0; }
.jwtf-dr-vp { position: relative; flex: 1 1 auto; min-width: 0; overflow: hidden; background: #0e0f12;
  border-radius: 6px; outline: none; touch-action: none; cursor: crosshair; }
.jwtf-dr-vp.pan { cursor: grab; }
.jwtf-dr-vp canvas.stage { position: absolute; display: none; box-shadow: 0 0 0 1px #000a; }
.jwtf-dr-vp canvas.stage.on { display: block; }
.jwtf-dr-vp canvas.stage.checker { background: repeating-conic-gradient(#b9b9b9 0 25%, #fff 0 50%) 0 0 / 16px 16px; }
.jwtf-dr-ring { position: absolute; border: 1px solid #fff; border-radius: 50%; pointer-events: none;
  box-shadow: 0 0 0 1px #000; display: none; transform: translate(-50%, -50%); }
.jwtf-dr-side { width: 176px; flex: none; display: flex; flex-direction: column; gap: 6px; overflow: auto; }
.jwtf-dr-wheel { display: block; border-radius: 50%; cursor: crosshair; touch-action: none; align-self: center; }
.jwtf-dr-sw { display: flex; flex-wrap: wrap; gap: 4px; }
.jwtf-dr-sw button { width: 18px; height: 18px; padding: 0; border: 1px solid #555; border-radius: 4px; cursor: pointer; }
.jwtf-dr-layers { display: flex; flex-direction: column; gap: 3px; }
.jwtf-dr-layer { display: flex; align-items: center; gap: 4px; padding: 2px; border: 1px solid transparent;
  border-radius: 6px; cursor: pointer; }
.jwtf-dr-layer.active { background: #2a3550; border-color: #5672b4; }
.jwtf-dr-layer canvas { width: 34px; height: 34px; border-radius: 3px; flex: none;
  background: repeating-conic-gradient(#999 0 25%, #ddd 0 50%) 0 0 / 8px 8px; }
.jwtf-dr-layer .nm { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.jwtf-dr-layer button { padding: 0 4px; font-size: 11px; line-height: 18px; }
.jwtf-dr-menu { position: absolute; z-index: 10; background: #23252b; border: 1px solid #3a3d46; border-radius: 6px;
  padding: 3px; display: flex; flex-direction: column; min-width: 120px; box-shadow: 0 4px 14px #0008; }
.jwtf-dr-menu button { text-align: left; background: none; border: 0; color: #ddd; padding: 4px 8px; border-radius: 4px;
  font: inherit; cursor: pointer; }
.jwtf-dr-menu button:hover { background: #3c4f7a; }
.jwtf-dr-toast { position: absolute; left: 50%; bottom: 12px; transform: translateX(-50%); background: #000c; color: #fff;
  padding: 4px 10px; border-radius: 12px; pointer-events: none; transition: opacity .3s; }
`);

// ---- pure helpers -------------------------------------------------------------------------

export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const uid8 = () => Array.from({ length: 8 }, () => Math.floor(Math.random() * 36).toString(36)).join("");

export function hsvToRgb(hh, s, v) {
    const f = (n) => {
        const k = (n + hh / 60) % 6;
        return v - v * s * Math.max(0, Math.min(k, 4 - k, 1));
    };
    return [f(5), f(3), f(1)].map((c) => Math.round(c * 255));
}

export function rgbToHsv(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
    let hh = 0;
    if (d) {
        if (max === r) hh = ((g - b) / d) % 6;
        else if (max === g) hh = (b - r) / d + 2;
        else hh = (r - g) / d + 4;
        hh *= 60;
        if (hh < 0) hh += 360;
    }
    return [hh, max ? d / max : 0, max];
}

const hex2 = (n) => n.toString(16).padStart(2, "0");
export const rgbToHex = ([r, g, b]) => `#${hex2(r)}${hex2(g)}${hex2(b)}`;

/** Pen pressure -> width factor: 0.1 + 0.9p, 0.5 when the device reports 0; others use 1. */
export function mapPressure(e) {
    if (e.pointerType !== "pen") return 1;
    return e.pressure === 0 ? 0.5 : 0.1 + 0.9 * e.pressure;
}

export const smoothPressure = (prev, next) => (prev == null ? next : 0.6 * prev + 0.4 * next);

/** Wheel delta -> zoom multiplier (pixel/line/page modes normalised; ctrl = trackpad pinch). */
export function wheelFactor(e, pageH = 800) {
    const dy = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? pageH : 1);
    return Math.exp(-dy * (e.ctrlKey ? 0.01 : 0.0015));
}

const newCanvas = (w, h) => {
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    return c;
};

function stamp() {
    const d = new Date(), p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

const toBlob = (canvas) => new Promise((res, rej) => canvas.toBlob((b) => (b ? res(b) : rej(new Error("toBlob failed"))), "image/png"));

// ---- WebGPU compositor (shared device) -----------------------------------------------------

const WGSL = /* wgsl */ `
@group(0) @binding(0) var tex: texture_2d<f32>;
@group(0) @binding(1) var smp: sampler;
@vertex fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {
  var p = array<vec2f, 3>(vec2f(-1.0, -1.0), vec2f(3.0, -1.0), vec2f(-1.0, 3.0));
  return vec4f(p[i], 0.0, 1.0);
}
@fragment fn fs(@builtin(position) pos: vec4f) -> @location(0) vec4f {
  let dim = vec2f(textureDimensions(tex));
  return textureSample(tex, smp, pos.xy / dim);
}`;

const gpu = { state: "idle", device: null, format: "", pipeline: null, sampler: null, listeners: new Set() };

function gpuFail(reason) {
    if (gpu.state === "failed") return;
    console.info("[JezzWTF] Draw Image: using 2D compositor:", reason?.message ?? reason);
    gpu.state = "failed";
    for (const fn of gpu.listeners) fn();
}

async function initGpu() {
    if (gpu.state !== "idle") return;
    gpu.state = "loading";
    try {
        if (!navigator.gpu) throw new Error("WebGPU unavailable");
        const adapter = await navigator.gpu.requestAdapter();
        const device = await adapter?.requestDevice();
        if (!device) throw new Error("no device");
        device.lost.then((info) => gpuFail(info?.message ?? "device lost"));
        gpu.format = navigator.gpu.getPreferredCanvasFormat();
        device.pushErrorScope("validation");
        const module = device.createShaderModule({ code: WGSL });
        const blend = { color: { srcFactor: "one", dstFactor: "one-minus-src-alpha" }, alpha: { srcFactor: "one", dstFactor: "one-minus-src-alpha" } };
        gpu.pipeline = device.createRenderPipeline({
            layout: "auto",
            vertex: { module, entryPoint: "vs" },
            fragment: { module, entryPoint: "fs", targets: [{ format: gpu.format, blend }] },
        });
        gpu.sampler = device.createSampler({ magFilter: "nearest", minFilter: "nearest" });
        const err = await device.popErrorScope();
        if (err) throw new Error(err.message);
        gpu.device = device;
        gpu.state = "ready";
        for (const fn of gpu.listeners) fn();
    } catch (e) {
        gpuFail(e);
    }
}

// ---- editor ---------------------------------------------------------------------------------

const editors = new Set();

function createEditor(node) {
    const W = { width: findWidget(node, "width"), height: findWidget(node, "height"), background: findWidget(node, "background"),
        image: findWidget(node, "image"), state: findWidget(node, "drawing_state") };
    hideWidget(node, W.image);
    hideWidget(node, W.state);

    const ed = {
        node, uid: uid8(), counter: 1, layers: [], activeId: "", undo: [],
        tool: "brush", size: 6, hsv: [0, 0, 0],
        view: { zoom: 1, tx: 0, ty: 0 },
        useGpu: false, dirty: new Map(), pendingFlat: false, saveTimer: 0, chain: Promise.resolve(), restoring: Promise.resolve(),
        renderQueued: false, thumbsDirty: new Set(), spaceDown: false, lastPointerType: "mouse",
    };
    const doc = () => ({ w: Number(W.width?.value) || 1024, h: Number(W.height?.value) || 1024 });
    const bg = () => String(W.background?.value ?? "white");

    // -- layers --------------------------------------------------------------------------------
    const makeLayer = (name, id = uid8()) => {
        const { w, h } = doc();
        const canvas = newCanvas(w, h);
        return { id, name, visible: true, canvas, ctx: canvas.getContext("2d", { willReadFrequently: false }), rev: 1, tex: null };
    };
    const layerById = (id) => ed.layers.find((l) => l.id === id);
    const active = () => layerById(ed.activeId) ?? ed.layers[ed.layers.length - 1];

    function touch(layer, { flat = true } = {}) {
        if (layer) {
            layer.rev++;
            ed.dirty.set(layer.id, layer.rev);
            ed.thumbsDirty.add(layer.id);
        }
        if (flat) ed.pendingFlat = true;
        scheduleRender();
        scheduleSave();
    }

    function pushUndo(entry) {
        ed.undo.push(entry);
        if (ed.undo.length > MAX_UNDO) ed.undo.shift();
    }

    function resetLayers() {
        ed.counter = 1;
        const layer = makeLayer("Layer 1");
        ed.layers = [layer];
        ed.activeId = layer.id;
        return layer;
    }

    function clearAll({ record = true } = {}) {
        if (record) pushUndo({ type: "clear", layers: ed.layers, active: ed.activeId, counter: ed.counter });
        for (const l of ed.layers) dropTexture(l);
        const layer = resetLayers();
        ed.dirty.clear();
        touch(layer);
        // Other layer files are stale but never deleted; the new state simply stops listing them.
        renderLayerList();
    }

    function addLayer() {
        if (ed.layers.length >= MAX_LAYERS) return toast(`At most ${MAX_LAYERS} layers`);
        const layer = makeLayer(`Layer ${++ed.counter}`);
        const at = ed.layers.indexOf(active()) + 1;
        ed.layers.splice(at, 0, layer);
        ed.activeId = layer.id;
        pushUndo({ type: "add", id: layer.id });
        touch(layer);
        renderLayerList();
    }

    function removeLayer(id) {
        if (ed.layers.length <= 1) return clearAll();
        const index = ed.layers.findIndex((l) => l.id === id);
        if (index < 0) return;
        const [layer] = ed.layers.splice(index, 1);
        dropTexture(layer);
        pushUndo({ type: "remove", layer, index, active: ed.activeId });
        if (ed.activeId === id) ed.activeId = ed.layers[Math.min(index, ed.layers.length - 1)].id;
        touch(null);
        renderLayerList();
    }

    function moveLayer(id, dir) {
        const from = ed.layers.findIndex((l) => l.id === id);
        const to = from + dir;
        if (from < 0 || to < 0 || to >= ed.layers.length) return;
        const [layer] = ed.layers.splice(from, 1);
        ed.layers.splice(to, 0, layer);
        pushUndo({ type: "move", id, from, to });
        touch(null);
        renderLayerList();
    }

    function undo() {
        const e = ed.undo.pop();
        if (!e) return;
        if (e.type === "stroke") {
            const layer = layerById(e.layerId);
            if (!layer) return;
            layer.ctx.clearRect(e.x, e.y, e.w, e.h);
            layer.ctx.drawImage(e.img, e.x, e.y);
            touch(layer);
        } else if (e.type === "add") {
            const i = ed.layers.findIndex((l) => l.id === e.id);
            if (i >= 0) {
                ed.layers.splice(i, 1);
                if (ed.activeId === e.id) ed.activeId = ed.layers[Math.min(i, ed.layers.length - 1)].id;
            }
            touch(null);
        } else if (e.type === "remove") {
            ed.layers.splice(e.index, 0, e.layer);
            dropTexture(e.layer);
            ed.activeId = e.active;
            touch(e.layer);
        } else if (e.type === "move") {
            const i = ed.layers.findIndex((l) => l.id === e.id);
            if (i >= 0) {
                const [layer] = ed.layers.splice(i, 1);
                ed.layers.splice(e.from, 0, layer);
            }
            touch(null);
        } else if (e.type === "clear") {
            ed.layers = e.layers;
            ed.activeId = e.active;
            ed.counter = e.counter;
            for (const l of ed.layers) {
                dropTexture(l);
                touch(l);
            }
        }
        renderLayerList();
    }

    // -- compositing ---------------------------------------------------------------------------
    const root = h("div.jwtf-dr", { tabIndex: -1 });
    const vp = h("div.jwtf-dr-vp", { tabIndex: 0 });
    const canvas2d = h("canvas.stage", {});
    const canvasGpu = h("canvas.stage", {});
    const ring = h("div.jwtf-dr-ring");
    vp.append(canvas2d, canvasGpu, ring);
    let gpuCtx = null;

    const stageCanvas = () => (ed.useGpu ? canvasGpu : canvas2d);

    function composeFlat() {
        const { w, h: hh } = doc();
        const out = newCanvas(w, hh);
        const c = out.getContext("2d");
        if (bg() !== "transparent") {
            c.fillStyle = bg() === "black" ? "#000" : "#fff";
            c.fillRect(0, 0, w, hh);
        }
        for (const l of ed.layers) if (l.visible) c.drawImage(l.canvas, 0, 0);
        return out;
    }

    function renderGpu() {
        const { w, h: hh } = doc();
        const dev = gpu.device;
        if (canvasGpu.width !== w || canvasGpu.height !== hh) {
            canvasGpu.width = w;
            canvasGpu.height = hh;
            for (const l of ed.layers) dropTexture(l);
        }
        if (!gpuCtx) {
            gpuCtx = canvasGpu.getContext("webgpu");
            if (!gpuCtx) throw new Error("no webgpu context");
        }
        gpuCtx.configure({ device: dev, format: gpu.format, alphaMode: "premultiplied" });
        const clear = bg() === "white" ? [1, 1, 1, 1] : bg() === "black" ? [0, 0, 0, 1] : [0, 0, 0, 0];
        const enc = dev.createCommandEncoder();
        const pass = enc.beginRenderPass({ colorAttachments: [{
            view: gpuCtx.getCurrentTexture().createView(), loadOp: "clear", storeOp: "store", clearValue: clear }] });
        pass.setPipeline(gpu.pipeline);
        for (const l of ed.layers) {
            if (!l.visible) continue;
            if (!l.tex || l.tex.w !== w || l.tex.h !== hh) {
                const texture = dev.createTexture({ size: [w, hh], format: "rgba8unorm",
                    usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST | GPUTextureUsage.RENDER_ATTACHMENT });
                const bind = dev.createBindGroup({ layout: gpu.pipeline.getBindGroupLayout(0),
                    entries: [{ binding: 0, resource: texture.createView() }, { binding: 1, resource: gpu.sampler }] });
                l.tex = { texture, bind, rev: -1, w, h: hh };
            }
            if (l.tex.rev !== l.rev) {
                dev.queue.copyExternalImageToTexture({ source: l.canvas }, { texture: l.tex.texture, premultipliedAlpha: true }, [w, hh]);
                l.tex.rev = l.rev;
            }
            pass.setBindGroup(0, l.tex.bind);
            pass.draw(3);
        }
        pass.end();
        dev.queue.submit([enc.finish()]);
    }

    function render() {
        ed.renderQueued = false;
        const { w, h: hh } = doc();
        canvas2d.classList.toggle("checker", bg() === "transparent");
        canvasGpu.classList.toggle("checker", bg() === "transparent");
        if (ed.useGpu && gpu.state === "ready") {
            try {
                renderGpu();
                return;
            } catch (e) {
                gpuFail(e);
                return;
            }
        }
        if (canvas2d.width !== w || canvas2d.height !== hh) {
            canvas2d.width = w;
            canvas2d.height = hh;
        }
        const c = canvas2d.getContext("2d");
        c.clearRect(0, 0, w, hh);
        if (bg() !== "transparent") {
            c.fillStyle = bg() === "black" ? "#000" : "#fff";
            c.fillRect(0, 0, w, hh);
        }
        for (const l of ed.layers) if (l.visible) c.drawImage(l.canvas, 0, 0);
    }

    function scheduleRender() {
        if (ed.renderQueued) return;
        ed.renderQueued = true;
        requestAnimationFrame(() => {
            render();
            refreshThumbs();
        });
    }

    function pickBackend() {
        const want = gpu.state === "ready";
        if (want !== ed.useGpu) {
            ed.useGpu = want;
            applyView();
            scheduleRender();
        }
    }
    gpu.listeners.add(pickBackend);
    initGpu();

    // -- view ----------------------------------------------------------------------------------
    const layoutScale = () => {
        const r = vp.getBoundingClientRect();
        return vp.offsetWidth ? r.width / vp.offsetWidth : 1; // ComfyUI's own graph zoom
    };
    const fitScale = () => {
        const { w, h: hh } = doc();
        return Math.max(0.0001, Math.min((vp.clientWidth - 16) / w, (vp.clientHeight - 16) / hh));
    };

    function geometry() {
        const { w, h: hh } = doc();
        const f = fitScale() * ed.view.zoom;
        const dw = w * f, dh = hh * f;
        return { f, dw, dh, left: (vp.clientWidth - dw) / 2 + ed.view.tx, top: (vp.clientHeight - dh) / 2 + ed.view.ty };
    }

    function clampPan() {
        const { dw, dh } = geometry();
        const keep = 48;
        const maxX = (vp.clientWidth + dw) / 2 - keep, maxY = (vp.clientHeight + dh) / 2 - keep;
        ed.view.tx = clamp(ed.view.tx, -maxX, maxX);
        ed.view.ty = clamp(ed.view.ty, -maxY, maxY);
    }

    function applyView() {
        clampPan();
        const g = geometry();
        const pixelated = g.f * layoutScale() >= 2;
        for (const c of [canvas2d, canvasGpu]) {
            c.style.width = `${g.dw}px`;
            c.style.height = `${g.dh}px`;
            c.style.left = `${g.left}px`;
            c.style.top = `${g.top}px`;
            c.style.imageRendering = pixelated ? "pixelated" : "auto";
            c.classList.toggle("on", c === stageCanvas());
        }
        zoomLabel.textContent = `${Math.round(g.f * 100)}%`;
    }

    function zoomAt(factor, cx = vp.clientWidth / 2, cy = vp.clientHeight / 2) {
        const before = geometry();
        const { w, h: hh } = doc();
        const docX = (cx - before.left) / (before.dw / w), docY = (cy - before.top) / (before.dh / hh);
        ed.view.zoom = clamp(ed.view.zoom * factor, MIN_ZOOM, MAX_ZOOM);
        const f = fitScale() * ed.view.zoom;
        const dw = w * f, dh = hh * f;
        ed.view.tx = cx - docX * f - (vp.clientWidth - dw) / 2;
        ed.view.ty = cy - docY * f - (vp.clientHeight - dh) / 2;
        applyView();
    }

    const fit = () => { ed.view = { zoom: 1, tx: 0, ty: 0 }; applyView(); };
    const oneToOne = () => { ed.view = { zoom: clamp(1 / fitScale(), MIN_ZOOM, MAX_ZOOM), tx: 0, ty: 0 }; applyView(); };

    /** Client coords -> layout coords inside the viewport (undoes ComfyUI's graph zoom). */
    function toViewport(e) {
        const r = vp.getBoundingClientRect(), s = layoutScale();
        return [(e.clientX - r.left) / s, (e.clientY - r.top) / s];
    }

    function toDoc(e) {
        const r = stageCanvas().getBoundingClientRect();
        const { w, h: hh } = doc();
        return [(e.clientX - r.left) * (w / r.width), (e.clientY - r.top) * (hh / r.height)];
    }

    // -- strokes -------------------------------------------------------------------------------
    let stroke = null;
    const snap = newCanvas(1, 1);

    function brushWidth(pressure) {
        return Math.max(0.5, ed.size * pressure);
    }

    function dab(layer, erase, p0, p1, w0, w1) {
        const c = layer.ctx;
        c.save();
        c.globalCompositeOperation = erase ? "destination-out" : "source-over";
        const color = rgbToHex(hsvToRgb(...ed.hsv));
        c.strokeStyle = color;
        c.fillStyle = color;
        c.lineCap = "round";
        c.lineJoin = "round";
        if (!p1) {
            c.beginPath();
            c.arc(p0[0], p0[1], w0 / 2, 0, Math.PI * 2);
            c.fill();
        } else {
            c.lineWidth = (w0 + w1) / 2;
            c.beginPath();
            c.moveTo(p0[0], p0[1]);
            c.lineTo(p1[0], p1[1]);
            c.stroke();
        }
        c.restore();
    }

    function growBox(box, p, w) {
        const r = w / 2 + 2;
        box.x0 = Math.min(box.x0, p[0] - r);
        box.y0 = Math.min(box.y0, p[1] - r);
        box.x1 = Math.max(box.x1, p[0] + r);
        box.y1 = Math.max(box.y1, p[1] + r);
    }

    function beginStroke(e) {
        const layer = active();
        if (!layer) return;
        if (!layer.visible) {
            layer.visible = true;
            renderLayerList();
        }
        const { w, h: hh } = doc();
        if (snap.width !== w || snap.height !== hh) {
            snap.width = w;
            snap.height = hh;
        }
        const sc = snap.getContext("2d");
        sc.clearRect(0, 0, w, hh);
        sc.drawImage(layer.canvas, 0, 0);
        const erase = ed.tool === "eraser" || (e.pointerType === "pen" && (e.buttons & 32) !== 0);
        const pressure = smoothPressure(null, mapPressure(e));
        const p = toDoc(e);
        const wd = brushWidth(pressure);
        stroke = { layer, erase, pointerId: e.pointerId, last: p, pressure, width: wd,
            box: { x0: p[0], y0: p[1], x1: p[0], y1: p[1] } };
        growBox(stroke.box, p, wd);
        vp.setPointerCapture?.(e.pointerId);
        dab(layer, erase, p, null, wd, wd);
        touch(layer, { flat: false });
    }

    function continueStroke(e) {
        if (!stroke || e.pointerId !== stroke.pointerId) return;
        const events = e.getCoalescedEvents?.() ?? [];
        for (const ev of events.length ? events : [e]) {
            const p = toDoc(ev);
            stroke.pressure = smoothPressure(stroke.pressure, mapPressure(ev));
            const wd = brushWidth(stroke.pressure);
            dab(stroke.layer, stroke.erase, stroke.last, p, stroke.width, wd);
            growBox(stroke.box, p, Math.max(wd, stroke.width));
            stroke.last = p;
            stroke.width = wd;
        }
        touch(stroke.layer, { flat: false });
    }

    function endStroke() {
        if (!stroke) return;
        const { layer, box } = stroke;
        const { w, h: hh } = doc();
        const x = clamp(Math.floor(box.x0), 0, w), y = clamp(Math.floor(box.y0), 0, hh);
        const cw = clamp(Math.ceil(box.x1), 0, w) - x, ch = clamp(Math.ceil(box.y1), 0, hh) - y;
        if (cw > 0 && ch > 0) {
            const img = newCanvas(cw, ch);
            img.getContext("2d").drawImage(snap, x, y, cw, ch, 0, 0, cw, ch);
            pushUndo({ type: "stroke", layerId: layer.id, x, y, w: cw, h: ch, img });
        }
        stroke = null;
        touch(layer);
    }

    /** A second finger landed: drop the half-drawn stroke instead of keeping a stray dot. */
    function cancelStroke() {
        if (!stroke) return;
        const { layer } = stroke;
        layer.ctx.clearRect(0, 0, layer.canvas.width, layer.canvas.height);
        layer.ctx.drawImage(snap, 0, 0);
        stroke = null;
        touch(layer);
    }

    // -- pointer wiring ------------------------------------------------------------------------
    const touches = new Map();
    let panning = null, pinch = null;

    function updateRing(e, hide = false) {
        const g = geometry();
        const show = !hide && ed.tool !== "pan" && !ed.spaceDown && e;
        if (!show) {
            ring.style.display = "none";
            return;
        }
        const [x, y] = toViewport(e);
        const d = Math.max(2, brushWidth(stroke?.pressure ?? mapPressure(e)) * g.f);
        Object.assign(ring.style, { display: "block", left: `${x}px`, top: `${y}px`, width: `${d}px`, height: `${d}px` });
    }

    function pinchState() {
        const [a, b] = [...touches.values()];
        return { dist: Math.hypot(a.x - b.x, a.y - b.y) || 1, mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 };
    }

    vp.addEventListener("pointerdown", (e) => {
        vp.focus({ preventScroll: true });
        closeMenu();
        ed.lastPointerType = e.pointerType;
        if (e.pointerType === "touch") {
            touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
            if (touches.size === 2) {
                cancelStroke();
                pinch = pinchState();
                return;
            }
            if (touches.size > 2) return;
        }
        const wantPan = e.button === 1 || (e.button === 0 && (ed.tool === "pan" || ed.spaceDown));
        if (wantPan) {
            panning = { id: e.pointerId, x: e.clientX, y: e.clientY };
            vp.setPointerCapture?.(e.pointerId);
            vp.classList.add("pan");
            e.preventDefault();
            return;
        }
        if (e.button !== 0) return;
        beginStroke(e);
    });

    vp.addEventListener("pointermove", (e) => {
        if (e.pointerType === "touch" && touches.has(e.pointerId)) {
            touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
            if (touches.size === 2 && pinch) {
                const s = pinchState(), ls = layoutScale(), r = vp.getBoundingClientRect();
                zoomAt(s.dist / pinch.dist, (s.mx - r.left) / ls, (s.my - r.top) / ls);
                ed.view.tx += (s.mx - pinch.mx) / ls;
                ed.view.ty += (s.my - pinch.my) / ls;
                applyView();
                pinch = s;
                return;
            }
        }
        if (panning && e.pointerId === panning.id) {
            const ls = layoutScale();
            ed.view.tx += (e.clientX - panning.x) / ls;
            ed.view.ty += (e.clientY - panning.y) / ls;
            panning.x = e.clientX;
            panning.y = e.clientY;
            applyView();
            return;
        }
        continueStroke(e);
        updateRing(e);
    });

    const release = (e) => {
        touches.delete(e.pointerId);
        if (touches.size < 2) pinch = null;
        if (panning && e.pointerId === panning.id) {
            panning = null;
            vp.classList.toggle("pan", ed.tool === "pan");
        }
        if (stroke && e.pointerId === stroke.pointerId) endStroke();
        vp.releasePointerCapture?.(e.pointerId);
    };
    vp.addEventListener("pointerup", release);
    vp.addEventListener("pointercancel", release);
    vp.addEventListener("pointerleave", () => { if (!stroke) updateRing(null, true); });

    vp.addEventListener("wheel", (e) => {
        e.preventDefault();
        const [cx, cy] = toViewport(e);
        zoomAt(wheelFactor(e, vp.clientHeight), cx, cy);
    }, { passive: false });

    // Keys: the editor owns them while focused; nothing leaks to graph shortcuts.
    root.addEventListener("keydown", (e) => {
        if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
            e.stopPropagation();
            return;
        }
        let handled = true;
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") undo();
        else if (e.key === "+" || e.key === "=") zoomAt(1.25);
        else if (e.key === "-" || e.key === "_") zoomAt(1 / 1.25);
        else if (e.key === "0") fit();
        else if (e.key === " ") {
            ed.spaceDown = true;
            vp.classList.add("pan");
        } else handled = false;
        if (handled) e.preventDefault();
        e.stopPropagation();
    });
    root.addEventListener("keyup", (e) => {
        if (e.key === " ") {
            ed.spaceDown = false;
            vp.classList.toggle("pan", ed.tool === "pan");
        }
        e.stopPropagation();
    });
    // Keep graph pointer/wheel behaviour (drag-select, zoom, context menus) out of the editor.
    for (const type of ["pointerdown", "pointermove", "pointerup", "wheel", "mousedown", "dblclick", "contextmenu"]) {
        root.addEventListener(type, (e) => e.stopPropagation());
    }

    // -- context menu + toast ------------------------------------------------------------------
    let menu = null;
    function closeMenu() {
        menu?.remove();
        menu = null;
    }
    function toast(text) {
        const t = h("div.jwtf-dr-toast", {}, text);
        root.append(t);
        setTimeout(() => { t.style.opacity = "0"; }, 1300);
        setTimeout(() => t.remove(), 1700);
    }
    async function savePng() {
        const blob = await toBlob(composeFlat());
        const a = h("a", { href: URL.createObjectURL(blob), download: `jezzwtf_draw_${stamp()}.png` });
        document.body.append(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 5000);
        toast("Saved PNG");
    }
    async function copyImage() {
        try {
            if (!navigator.clipboard?.write || typeof ClipboardItem === "undefined") throw new Error("unsupported");
            await navigator.clipboard.write([new ClipboardItem({ "image/png": toBlob(composeFlat()) })]);
            toast("Copied image");
        } catch {
            toast("Copying images isn't supported here");
        }
    }
    vp.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        const type = e.pointerType || ed.lastPointerType;
        if (type && type !== "mouse") return;
        closeMenu();
        const rr = root.getBoundingClientRect(), ls = rr.width / root.offsetWidth || 1;
        const item = (label, fn) => h("button", { type: "button", onclick: () => { closeMenu(); fn(); } }, label);
        menu = h("div.jwtf-dr-menu", { style: { left: `${(e.clientX - rr.left) / ls}px`, top: `${(e.clientY - rr.top) / ls}px` } },
            item("Save PNG", savePng), item("Copy image", copyImage), item("Fit", fit), item("1:1", oneToOne));
        root.append(menu);
    });

    // -- toolbar + side panel ------------------------------------------------------------------
    const btn = (label, onclick, title) => h("button.jwtf-btn", { type: "button", onclick, title }, label);
    const toolBtns = {};
    for (const [id, label] of [["brush", "Brush"], ["eraser", "Eraser"], ["pan", "Pan"]]) {
        toolBtns[id] = btn(label, () => setTool(id));
    }
    function setTool(id) {
        ed.tool = id;
        for (const [k, b] of Object.entries(toolBtns)) b.classList.toggle("on", k === id);
        vp.classList.toggle("pan", id === "pan");
        updateRing(null, true);
    }
    const sizeLabel = h("span", { style: { minWidth: "34px" } }, `${ed.size}px`);
    const sizeInput = h("input", { type: "range", min: 1, max: 150, value: ed.size, style: { width: "90px" },
        oninput: () => { ed.size = Number(sizeInput.value); sizeLabel.textContent = `${ed.size}px`; } });
    const zoomLabel = h("span", { style: { minWidth: "40px", textAlign: "center" } }, "100%");
    const bar = h("div.jwtf-dr-bar", {},
        toolBtns.brush, toolBtns.eraser, toolBtns.pan, h("span.sep"), sizeInput, sizeLabel, h("span.sep"),
        btn("−", () => zoomAt(1 / 1.25), "Zoom out"), zoomLabel, btn("+", () => zoomAt(1.25), "Zoom in"),
        btn("Fit", fit), btn("1:1", oneToOne), h("span.sep"),
        btn("Undo", undo, "Ctrl+Z"), btn("Clear all", () => clearAll()));

    const wheel = h("canvas.jwtf-dr-wheel", { width: 110, height: 110 });
    const brightness = h("input", { type: "range", min: 0, max: 1, step: 0.01, value: 0, style: { width: "100%" } });
    const hexBox = h("input.jwtf-input", { type: "text", value: "#000000", maxLength: 7, style: { width: "100%" } });

    function drawWheel() {
        const c = wheel.getContext("2d"), R = wheel.width / 2;
        const img = c.createImageData(wheel.width, wheel.height);
        for (let y = 0; y < wheel.height; y++) {
            for (let x = 0; x < wheel.width; x++) {
                const dx = x + 0.5 - R, dy = y + 0.5 - R, r = Math.hypot(dx, dy) / R;
                if (r > 1) continue;
                const hue = (Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360;
                const [rr, gg, bb] = hsvToRgb(hue, r, Math.max(ed.hsv[2], 0.15));
                const i = (y * wheel.width + x) * 4;
                img.data.set([rr, gg, bb, 255], i);
            }
        }
        c.putImageData(img, 0, 0);
        const a = ed.hsv[0] * Math.PI / 180, rad = ed.hsv[1] * R;
        c.beginPath();
        c.arc(R + Math.cos(a) * rad, R + Math.sin(a) * rad, 5, 0, Math.PI * 2);
        c.strokeStyle = "#fff";
        c.lineWidth = 2;
        c.stroke();
        c.strokeStyle = "#000";
        c.lineWidth = 1;
        c.stroke();
    }

    function syncColorUi() {
        drawWheel();
        brightness.value = String(ed.hsv[2]);
        brightness.style.background = `linear-gradient(to right, #000, ${rgbToHex(hsvToRgb(ed.hsv[0], ed.hsv[1], 1))})`;
        hexBox.value = rgbToHex(hsvToRgb(...ed.hsv));
    }

    function pickColor(hsv) {
        ed.hsv = hsv;
        syncColorUi();
        setTool("brush");
    }

    function wheelPick(e) {
        const r = wheel.getBoundingClientRect(), R = r.width / 2;
        const dx = e.clientX - r.left - R, dy = e.clientY - r.top - R;
        const hue = (Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360;
        const sat = clamp(Math.hypot(dx, dy) / R, 0, 1);
        pickColor([hue, sat, ed.hsv[2] < 0.05 ? 1 : ed.hsv[2]]);
    }
    let wheelDrag = false;
    wheel.addEventListener("pointerdown", (e) => { wheelDrag = true; wheel.setPointerCapture(e.pointerId); wheelPick(e); });
    wheel.addEventListener("pointermove", (e) => { if (wheelDrag) wheelPick(e); });
    wheel.addEventListener("pointerup", () => { wheelDrag = false; });
    brightness.addEventListener("input", () => pickColor([ed.hsv[0], ed.hsv[1], Number(brightness.value)]));
    hexBox.addEventListener("change", () => {
        const m = /^#?([0-9a-f]{6})$/i.exec(hexBox.value.trim());
        if (!m) return syncColorUi();
        const n = parseInt(m[1], 16);
        pickColor(rgbToHsv((n >> 16) & 255, (n >> 8) & 255, n & 255));
    });
    const swatches = h("div.jwtf-dr-sw", {}, SWATCHES.map((hex) => {
        const n = parseInt(hex.slice(1), 16);
        return h("button", { type: "button", title: hex, style: { background: hex },
            onclick: () => pickColor(rgbToHsv((n >> 16) & 255, (n >> 8) & 255, n & 255)) });
    }));

    const layerList = h("div.jwtf-dr-layers");
    function renderLayerList() {
        layerList.replaceChildren();
        for (const l of [...ed.layers].reverse()) {
            const thumb = h("canvas", { width: 34, height: 34 });
            l._thumb = thumb;
            ed.thumbsDirty.add(l.id);
            const small = (label, title, fn) => h("button.jwtf-btn", { type: "button", title,
                onclick: (e) => { e.stopPropagation(); fn(); } }, label);
            layerList.append(h("div.jwtf-dr-layer", { class: l.id === ed.activeId ? "jwtf-dr-layer active" : "jwtf-dr-layer",
                onclick: () => { ed.activeId = l.id; renderLayerList(); } },
            thumb, h("span.nm", { title: l.name }, l.name),
            small(l.visible ? "◉" : "○", "Toggle visibility", () => { l.visible = !l.visible; touch(null); renderLayerList(); }),
            small("▲", "Move up", () => moveLayer(l.id, 1)),
            small("▼", "Move down", () => moveLayer(l.id, -1)),
            small("✕", "Remove", () => removeLayer(l.id))));
        }
        scheduleRender();
    }

    function refreshThumbs() {
        for (const id of ed.thumbsDirty) {
            const l = layerById(id), t = l?._thumb;
            if (!t?.isConnected) continue;
            const c = t.getContext("2d");
            c.clearRect(0, 0, 34, 34);
            const s = Math.min(34 / l.canvas.width, 34 / l.canvas.height);
            const w = l.canvas.width * s, hh = l.canvas.height * s;
            c.drawImage(l.canvas, (34 - w) / 2, (34 - hh) / 2, w, hh);
        }
        ed.thumbsDirty.clear();
    }

    const side = h("div.jwtf-dr-side", {}, wheel, brightness, hexBox, swatches,
        h("div.jwtf-row", {}, h("b", { style: { flex: "1" } }, "Layers"), btn("Add", addLayer)), layerList);
    root.append(bar, h("div.jwtf-dr-main", {}, vp, side));
    wheel.addEventListener("pointerdown", closeMenu);

    // -- doc resize / background ---------------------------------------------------------------
    function resizeDoc() {
        const { w, h: hh } = doc();
        for (const l of ed.layers) {
            if (l.canvas.width === w && l.canvas.height === hh) continue;
            const next = newCanvas(w, hh);
            next.getContext("2d").drawImage(l.canvas, 0, 0); // anchored top-left: grow pads, shrink crops
            l.canvas = next;
            l.ctx = next.getContext("2d");
            dropTexture(l);
            touch(l);
        }
        ed.undo = [];
        applyView();
    }
    onWidget(W.width, resizeDoc);
    onWidget(W.height, resizeDoc);
    onWidget(W.background, () => { touch(null); applyView(); });

    // -- persistence ---------------------------------------------------------------------------
    function stateJson() {
        const { w, h: hh } = doc();
        return JSON.stringify({ uid: ed.uid, w, h: hh, active: ed.activeId, counter: ed.counter,
            layers: ed.layers.map((l) => ({ id: l.id, name: l.name, visible: l.visible })) });
    }

    const upload = async (blob, filename) => {
        const body = new FormData();
        body.append("image", new File([blob], filename, { type: "image/png" }));
        body.append("type", "input");
        body.append("subfolder", SUBFOLDER);
        body.append("overwrite", "true");
        const res = await api.fetchApi("/upload/image", { method: "POST", body });
        if (!res.ok) throw new Error(`upload ${filename}: HTTP ${res.status}`);
    };

    async function saveNow() {
        await ed.restoring;
        if (!ed.dirty.size && !ed.pendingFlat) return;
        const uploaded = [...ed.dirty].filter(([id]) => layerById(id));
        const flatWanted = ed.pendingFlat || uploaded.length > 0;
        ed.pendingFlat = false;
        try {
            for (const [id, rev] of uploaded) {
                const l = layerById(id);
                await upload(await toBlob(l.canvas), `layer_${ed.uid}_${id}.png`);
                if (ed.dirty.get(id) === rev) ed.dirty.delete(id);
            }
            if (flatWanted) await upload(await toBlob(composeFlat()), `flat_${ed.uid}.png`);
            for (const id of [...ed.dirty.keys()]) if (!layerById(id)) ed.dirty.delete(id);
            if (W.image) W.image.value = `${SUBFOLDER}/flat_${ed.uid}.png`;
            if (W.state) W.state.value = stateJson();
            node.graph?.change?.();
        } catch (err) {
            ed.pendingFlat = true; // keep the flags so the next save retries
            console.warn("[JezzWTF] Draw Image save failed:", err);
            toast("Save failed, will retry");
            throw err;
        }
    }

    function scheduleSave() {
        clearTimeout(ed.saveTimer);
        ed.saveTimer = setTimeout(() => { ed.chain = ed.chain.then(saveNow).catch(() => {}); }, SAVE_DELAY);
    }

    /** Finish any pending save now; used before the prompt is built. */
    ed.flush = async () => {
        clearTimeout(ed.saveTimer);
        ed.chain = ed.chain.then(saveNow).catch(() => {});
        await ed.chain;
    };

    function loadLayerImage(l) {
        return new Promise((resolve) => {
            const img = new Image();
            img.onload = () => {
                l.ctx.drawImage(img, 0, 0);
                l.rev++; // re-upload the GPU texture; the file on the server already matches
                ed.thumbsDirty.add(l.id);
                scheduleRender();
                resolve();
            };
            img.onerror = () => resolve(); // a missing file is an empty layer
            const q = new URLSearchParams({ type: "input", subfolder: SUBFOLDER, filename: `layer_${ed.uid}_${l.id}.png`, t: String(Date.now()) });
            img.src = api.apiURL(`/view?${q}`);
        });
    }

    ed.restore = () => {
        let state = null;
        try { state = JSON.parse(String(W.state?.value || "null")); } catch { /* ignore */ }
        if (!state || typeof state.uid !== "string" || !Array.isArray(state.layers) || !state.layers.length) {
            if (!ed.layers.length) resetLayers();
            renderLayerList();
            applyView();
            return;
        }
        ed.uid = state.uid;
        ed.counter = Number(state.counter) || state.layers.length;
        ed.layers = state.layers.slice(0, MAX_LAYERS).map((s) => {
            const l = makeLayer(String(s.name ?? "Layer"), String(s.id));
            l.visible = s.visible !== false;
            return l;
        });
        ed.activeId = ed.layers.some((l) => l.id === state.active) ? state.active : ed.layers[ed.layers.length - 1].id;
        ed.undo = [];
        ed.dirty.clear();
        ed.restoring = Promise.all(ed.layers.map(loadLayerImage)).then(() => {
            ed.dirty.clear();
            ed.pendingFlat = false;
            scheduleRender();
        });
        renderLayerList();
        applyView();
    };

    /** A pasted or duplicated node arrives with its source's uid: whoever finds a collision re-keys. */
    ed.dedupe = async () => {
        await ed.restoring;
        if (!collidesWithOther(editors, ed)) return;
        ed.uid = uid8(); // always re-key on collision: node ids repeat across graphs, so neither side is "older"
        for (const l of ed.layers) {
            l.rev++;
            ed.dirty.set(l.id, l.rev);
        }
        ed.pendingFlat = true;
        scheduleSave();
    };

    ed.destroy = () => {
        clearTimeout(ed.saveTimer);
        gpu.listeners.delete(pickBackend);
        ro.disconnect();
        editors.delete(ed);
        closeMenu();
        const spare = new Set(ed.layers);
        for (const e of ed.undo) {
            if (e.layer) spare.add(e.layer);
            for (const l of e.layers ?? []) spare.add(l);
        }
        for (const l of spare) dropTexture(l);
        try { gpuCtx?.unconfigure?.(); } catch { /* ignore */ }
    };

    const ro = new ResizeObserver(() => applyView());
    ro.observe(vp);
    ed.root = root;
    ed.vp = vp;
    resetLayers();
    setTool("brush");
    syncColorUi();
    renderLayerList();
    editors.add(ed);
    node.addDOMWidget("jwtf_draw", "jwtf_draw", root, { serialize: false, getMinHeight: () => 320 });
    requestAnimationFrame(() => { applyView(); render(); });
    return ed;
}

app.registerExtension({
    name: "JezzWTF.UtilityCore.DrawImage",

    setup() {
        const orig = app.graphToPrompt;
        app.graphToPrompt = async function (...args) {
            try {
                await Promise.all([...editors].map((ed) => ed.flush()));
            } catch (e) {
                console.warn("[JezzWTF] Draw Image flush failed:", e);
            }
            return orig.apply(this, args);
        };
        window.JezzWTFDraw = { editorOf: (node) => node?._jwtfDraw?.root ?? null };
    },

    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== TYPE) return;
        chain(nodeType.prototype, "onNodeCreated", function () {
            this._jwtfDraw = createEditor(this);
            this.setSize([Math.max(this.size[0], 720), Math.max(this.size[1], 640)]);
        });
        chain(nodeType.prototype, "onConfigure", function () {
            const ed = this._jwtfDraw;
            if (!ed) return;
            ed.restore();
            setTimeout(() => ed.dedupe(), 300);
        });
        chain(nodeType.prototype, "onRemoved", function () {
            this._jwtfDraw?.destroy();
            this._jwtfDraw = null;
        });
    },
});
