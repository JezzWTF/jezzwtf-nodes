import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { chain, findWidget, fitHeight, h, hideWidget, injectCss } from "./_shared.js";

const editors = new Set();
injectCss("jwtf-mask-editor", `
.jwtf-me {display:flex;flex-direction:column;gap:8px;padding:10px;background:#202228;border:1px solid #393d46;border-radius:8px;color:#dce0e5;font:12px system-ui}
.jwtf-me .bar {display:flex;flex-wrap:wrap;gap:6px;align-items:center}.jwtf-me button,.jwtf-me select {font:inherit}
.jwtf-me .viewport {height:330px;overflow:auto;background:#15171b;position:relative}
.jwtf-me canvas {display:block;touch-action:none;max-width:none}.jwtf-me output {color:#aeb6c3}
.jwtf-me label {display:flex;gap:4px;align-items:center}.jwtf-me input {max-width:85px}
`);

const imageFrom = async descriptor => {
  const image = new Image();
  image.src = api.apiURL(`/view?${new URLSearchParams({...descriptor, t: Date.now()})}`);
  await image.decode(); return image;
};

function setup(node) {
  const saved = findWidget(node, "painted_mask"); hideWidget(node, saved);
  const paint = document.createElement("canvas"), ctx = paint.getContext("2d", { willReadFrequently: true });
  const view = h("canvas", { width: 640, height: 360, "aria-label": "Paint white to select a mask region. Use the erase tool to remove it." });
  const viewport = h("div.viewport", {}, view);
  const tool = h("select", { "aria-label": "Mask tool" }, h("option", { value: "paint" }, "Paint"), h("option", { value: "erase" }, "Erase"));
  const radius = h("input", { type: "number", min: 1, max: 512, value: 32, "aria-label": "Brush radius in pixels" });
  const zoom = h("input", { type: "range", min: 25, max: 400, step: 25, value: 100, "aria-label": "Mask zoom" });
  const status = h("output", {}, "Connect an image and run once to begin.");
  const undoButton = h("button", { type: "button" }, "Undo"), clearButton = h("button", { type: "button" }, "Clear"), fillButton = h("button", { type: "button" }, "Fill"), maskButton = h("button", { type: "button" }, "Mask view");
  const resetButton = h("button", { type: "button" }, "Use input mask");
  const root = h("div.jwtf-me", {}, h("div.bar", {}, tool, h("label", {}, "Radius", radius), undoButton, clearButton, fillButton, maskButton, resetButton, h("label", {}, "Zoom", zoom)), viewport, status);
  let background = null, undo = [], stroke = null, timer = 0, revision = 0, savedRevision = 0, chainSave = Promise.resolve(), loading = Promise.resolve(), generation = 0, removed = false, maskOnly = false;
  const uid = crypto.randomUUID();
  const draw = () => {
    const v = view.getContext("2d"); v.clearRect(0, 0, view.width, view.height);
    if (background && !maskOnly) v.drawImage(background, 0, 0, view.width, view.height);
    if (!maskOnly && background) { v.globalCompositeOperation = "screen"; v.globalAlpha = 0.6; }
    v.drawImage(paint, 0, 0, view.width, view.height); v.globalCompositeOperation = "source-over"; v.globalAlpha = 1;
    const scale = Number(zoom.value) / 100;
    const base = Math.min(1, Math.max(1, viewport.clientWidth) / Math.max(1, view.width));
    view.style.width = `${view.width * base * scale}px`; view.style.height = `${view.height * base * scale}px`;
  };
  const remember = () => {
    undo.push(ctx.getImageData(0, 0, paint.width, paint.height));
    const limit = Math.max(1, Math.min(12, Math.floor(64 * 1024 * 1024 / (paint.width * paint.height * 4))));
    while (undo.length > limit) undo.shift();
  };
  const saveNow = async () => {
    if (savedRevision === revision || removed) return;
    await loading;
    const captured = revision;
    const blob = await new Promise((resolve, reject) => paint.toBlob(value => value ? resolve(value) : reject(new Error("Could not encode mask")), "image/png"));
    const body = new FormData();
    body.append("image", new File([blob], `${uid}.png`, { type: "image/png" }));
    body.append("type", "input"); body.append("subfolder", "jezzwtf_masks"); body.append("overwrite", "true");
    const response = await api.fetchApi("/upload/image", { method: "POST", body });
    if (!response.ok) throw new Error(`Mask upload failed (${response.status})`);
    const descriptor = await response.json();
    if (removed) return;
    saved.value = descriptor.subfolder ? `${descriptor.subfolder}/${descriptor.name}` : descriptor.name;
    savedRevision = captured; status.textContent = "Mask saved · white selects the region"; node.graph?.change?.();
  };
  const flush = () => {
    clearTimeout(timer);
    if (stroke) { stroke = null; revision++; }
    chainSave = chainSave.catch(() => {}).then(saveNow).catch(error => {
      if (!removed) status.textContent = `Mask save failed: ${error.message}`;
      throw error;
    });
    return chainSave;
  };
  const changed = () => {
    revision++; draw(); status.textContent = "Saving mask…";
    clearTimeout(timer); timer = setTimeout(() => flush().catch(error => { status.textContent = error.message; }), 350);
  };
  const load = payload => {
    if (revision !== savedRevision || stroke) return;
    // A result from an earlier run must not replace newer painting saved while it ran.
    if (saved.value && payload.background) {
      const path = String(saved.value).replaceAll("\\", "/"), at = path.lastIndexOf("/");
      payload = {...payload, mask: {type: "input", filename: path.slice(at + 1), subfolder: at < 0 ? "" : path.slice(0, at)}};
    }
    const token = ++generation;
    loading = (async () => {
      const [base, mask] = await Promise.all([payload.background ? imageFrom(payload.background) : null, imageFrom(payload.mask)]);
      if (removed || token !== generation) return;
      background = base; paint.width = view.width = mask.naturalWidth; paint.height = view.height = mask.naturalHeight;
      ctx.drawImage(mask, 0, 0); undo = []; draw(); status.textContent = "Paint white to select · erase to remove · scroll to pan when zoomed";
    })().catch(error => { status.textContent = `Cannot load mask: ${error.message}`; throw error; });
    loading.catch(() => {});
  };
  const point = e => {
    const r = view.getBoundingClientRect();
    return [(e.clientX - r.left) / r.width * paint.width, (e.clientY - r.top) / r.height * paint.height];
  };
  const brush = (a, b, e) => {
    ctx.strokeStyle = ctx.fillStyle = tool.value === "erase" ? "black" : "white";
    ctx.lineCap = ctx.lineJoin = "round";
    const pressure = e.pointerType === "pen" ? Math.max(0.1, e.pressure || 0.5) : 1;
    const width = 2 * Math.max(1, Math.min(512, Number(radius.value) || 32)) * pressure;
    ctx.lineWidth = width; ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(...b); ctx.stroke();
    ctx.beginPath(); ctx.arc(b[0], b[1], width / 2, 0, Math.PI * 2); ctx.fill(); draw();
  };
  view.addEventListener("pointerdown", e => { if (e.button !== 0 || !paint.width || !background && !saved.value) return; e.preventDefault(); remember(); stroke = point(e); view.setPointerCapture(e.pointerId); brush(stroke, stroke, e); });
  view.addEventListener("pointermove", e => { if (!stroke || !view.hasPointerCapture(e.pointerId)) return; const next = point(e); brush(stroke, next, e); stroke = next; });
  const finish = e => { if (!stroke) return; stroke = null; if (view.hasPointerCapture(e.pointerId)) view.releasePointerCapture(e.pointerId); changed(); };
  view.addEventListener("pointerup", finish); view.addEventListener("pointercancel", finish);
  undoButton.addEventListener("click", () => { if (!undo.length) return; ctx.putImageData(undo.pop(), 0, 0); changed(); });
  const fill = colour => { if (!background && !saved.value) return; remember(); ctx.fillStyle = colour; ctx.fillRect(0, 0, paint.width, paint.height); changed(); };
  clearButton.addEventListener("click", () => fill("black")); fillButton.addEventListener("click", () => fill("white"));
  resetButton.addEventListener("click", async () => {
    resetButton.disabled = true;
    try { await flush(); } catch { /* clearing a failed painting does not need an upload */ }
    saved.value = ""; revision = savedRevision = 0; background = null; undo = [];
    ctx.fillStyle = "black"; ctx.fillRect(0, 0, paint.width, paint.height); draw();
    node.graph?.change?.(); status.textContent = "Incoming mask selected · run to refresh the editor";
    resetButton.disabled = false;
  });
  maskButton.addEventListener("click", () => { maskOnly = !maskOnly; maskButton.textContent = maskOnly ? "Image view" : "Mask view"; draw(); });
  zoom.addEventListener("input", draw);
  const observer = new ResizeObserver(draw); observer.observe(viewport);
  const editor = { flush, load, restore() { if (saved.value) { const path = String(saved.value).replaceAll("\\", "/"), at = path.lastIndexOf("/"); load({mask: {type: "input", filename: path.slice(at + 1), subfolder: at < 0 ? "" : path.slice(0, at)}}); } }, destroy() { removed = true; generation++; clearTimeout(timer); observer.disconnect(); editors.delete(editor); } };
  node._jwtfMaskEditor = editor; editors.add(editor);
  node.addDOMWidget("jwtf_mask_editor", "jwtf_mask_editor", root, {serialize: false, getMinHeight: () => 410}); fitHeight(node, 570);
}

app.registerExtension({
  name: "JezzWTF.MaskEditor",
  setup() {
    const previous = app.graphToPrompt;
    app.graphToPrompt = async function (...args) { await Promise.all([...editors].map(editor => editor.flush())); return previous.apply(this, args); };
  },
  beforeRegisterNodeDef(type, data) {
    if (data.name !== "JWTFMaskEditor") return;
    chain(type.prototype, "onNodeCreated", function () { setup(this); });
    chain(type.prototype, "onConfigure", function () { this._jwtfMaskEditor?.restore(); });
    chain(type.prototype, "onExecuted", function (message) { if (message.jwtf_mask_editor?.[0]) this._jwtfMaskEditor?.load(message.jwtf_mask_editor[0]); });
    chain(type.prototype, "onRemoved", function () { this._jwtfMaskEditor?.destroy(); });
  },
});
