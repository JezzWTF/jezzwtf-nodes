import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { chain, fitHeight, h, injectCss } from "./_shared.js";

injectCss("jwtf-image-compare", `
.jwtf-ic {display:flex;flex-direction:column;gap:8px;padding:10px;background:#202228;color:#dce0e5;border:1px solid #393d46;border-radius:8px;font:12px system-ui}
.jwtf-ic .controls {display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.jwtf-ic label {display:flex;align-items:center;gap:5px}
.jwtf-ic select,.jwtf-ic input {accent-color:#7fb7a5;max-width:130px}
.jwtf-ic canvas {display:block;width:100%;max-height:420px;object-fit:contain;touch-action:none;background:#15171b}
.jwtf-ic output {color:#aeb6c3;font-variant-numeric:tabular-nums}
`);

function setup(node) {
  const mode = h("select", { "aria-label": "Comparison mode" }, ...["Wipe", "Blend", "Difference", "Toggle", "Mask"].map(text => h("option", { value: text }, text)));
  const frame = h("select", { "aria-label": "Batch frame" });
  const amount = h("input", { type: "range", min: 0, max: 100, value: 50, "aria-label": "Wipe position or blend amount" });
  const canvas = h("canvas", { width: 640, height: 360, "aria-label": "Image comparison preview" });
  const status = h("output", {}, "Connect A and B, then run to compare.");
  const root = h("div.jwtf-ic", {}, h("div.controls", {}, h("label", {}, "Mode", mode), h("label", {}, "Frame", frame), amount), canvas, status);
  let data = null, images = {}, generation = 0;
  const draw = () => {
    const a = images.a, b = images.b;
    if (!a || !b) return;
    const ctx = canvas.getContext("2d"), w = canvas.width, hh = canvas.height, mix = Number(amount.value) / 100;
    ctx.clearRect(0, 0, w, hh);
    ctx.drawImage(a, 0, 0, w, hh);
    if (mode.value === "Wipe") {
      ctx.save(); ctx.beginPath(); ctx.rect(0, 0, w * mix, hh); ctx.clip(); ctx.drawImage(b, 0, 0, w, hh); ctx.restore();
      ctx.fillStyle = "#9bcbbb"; ctx.fillRect(Math.round(w * mix), 0, 2, hh);
    } else if (mode.value === "Blend") {
      ctx.globalAlpha = mix; ctx.drawImage(b, 0, 0, w, hh); ctx.globalAlpha = 1;
    } else {
      const image = mode.value === "Difference" ? images.difference : mode.value === "Mask" ? images.mask : mix < 0.5 ? a : b;
      if (image) ctx.drawImage(image, 0, 0, w, hh);
    }
  };
  const loadFrame = async () => {
    const entry = data?.frames?.[Number(frame.value)];
    if (!entry) return;
    const token = ++generation;
    status.textContent = "Loading comparison…";
    try {
      const loaded = await Promise.all(Object.entries(entry).map(async ([key, descriptor]) => {
        const image = new Image();
        image.src = api.apiURL(`/view?${new URLSearchParams(descriptor)}`);
        await image.decode();
        return [key, image];
      }));
      if (token !== generation) return;
      images = Object.fromEntries(loaded);
      canvas.width = images.a.naturalWidth; canvas.height = images.a.naturalHeight;
      mode.querySelector('option[value="Mask"]').disabled = !images.mask;
      if (!images.mask && mode.value === "Mask") mode.value = "Wipe";
      const metric = data.metrics[Number(frame.value)];
      status.textContent = `MAE ${metric.mae.toFixed(5)} · PSNR ${metric.psnr_db == null ? "∞" : metric.psnr_db.toFixed(2)} dB${data.total > 32 ? " · showing first 32 frames" : ""}`;
      draw();
    } catch (error) { if (token === generation) status.textContent = `Preview unavailable: ${error.message}`; }
  };
  amount.addEventListener("input", draw); mode.addEventListener("change", draw); frame.addEventListener("change", loadFrame);
  const pointer = e => {
    if (mode.value !== "Wipe") return;
    const rect = canvas.getBoundingClientRect();
    amount.value = Math.max(0, Math.min(100, 100 * (e.clientX - rect.left) / rect.width)); draw();
  };
  canvas.addEventListener("pointerdown", e => { canvas.setPointerCapture(e.pointerId); pointer(e); });
  canvas.addEventListener("pointermove", e => { if (canvas.hasPointerCapture(e.pointerId)) pointer(e); });
  canvas.addEventListener("pointerup", e => { pointer(e); canvas.releasePointerCapture(e.pointerId); });
  node.addDOMWidget("jwtf_compare", "jwtf_compare", root, { serialize: false, getMinHeight: () => 300 });
  node._jwtfImageCompare = payload => {
    data = payload;
    frame.replaceChildren(...data.frames.map((_, i) => h("option", { value: i }, String(i + 1))));
    loadFrame();
  };
  chain(node, "onRemoved", () => { generation++; images = {}; data = null; });
  fitHeight(node, 470);
}

app.registerExtension({
  name: "JezzWTF.ImageCompare",
  beforeRegisterNodeDef(type, data) {
    if (data.name !== "JWTFImageCompare") return;
    chain(type.prototype, "onNodeCreated", function () { setup(this); });
    chain(type.prototype, "onExecuted", function (message) { if (message.jwtf_compare?.[0]) this._jwtfImageCompare?.(message.jwtf_compare[0]); });
  },
});
