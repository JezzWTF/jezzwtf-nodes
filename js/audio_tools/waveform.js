import { api } from "../../../scripts/api.js";
import { chain, findWidget, h, onWidget } from "../utility_core/_shared.js";

export const trimRange = (duration, start, length) => {
  const first = Math.max(0, Math.min(duration, Number(start) || 0));
  return [first, Number(length) > 0 ? Math.min(duration, first + Number(length)) : duration];
};

export function createWaveform(node, player) {
  const canvas = h("canvas", { width: 1000, height: 110, tabIndex: 0, role: "img", "aria-label": "Audio waveform. Drag either selection edge to trim; drag elsewhere to scrub.", style: { width: "100%", height: "110px", touchAction: "none", background: "#181b20", borderRadius: "5px" } });
  const label = h("output", { style: { font: "12px system-ui", color: "#aeb6c3" } }, "Select audio to show its waveform.");
  const body = h("div", {}, canvas, label);
  const start = findWidget(node, "start"), length = findWidget(node, "length");
  let data = null, controller = null, dragging = null, disposed = false;
  const draw = () => {
    const ctx = canvas.getContext("2d"), w = canvas.width, hh = canvas.height;
    ctx.clearRect(0, 0, w, hh);
    if (!data) return;
    const [first, last] = trimRange(data.duration, start.value, length.value);
    const left = first / data.duration * w, right = last / data.duration * w;
    ctx.fillStyle = "#293f39"; ctx.fillRect(left, 0, right - left, hh);
    data.peaks.forEach((p, i) => {
      ctx.fillStyle = "#91b9ac";
      ctx.fillRect(i / data.peaks.length * w, hh / 2 - p * hh * 0.43, Math.max(1, w / data.peaks.length - 1), Math.max(1, p * hh * 0.86));
    });
    ctx.fillStyle = "#c8e1d8"; ctx.fillRect(left, 0, 3, hh); ctx.fillRect(Math.min(w - 3, right - 3), 0, 3, hh);
    ctx.fillStyle = "#f0c78c"; ctx.fillRect(player.currentTime / data.duration * w, 0, 2, hh);
    label.textContent = `${first.toFixed(2)} – ${last.toFixed(2)}s · ${(last - first).toFixed(2)}s selected · drag edges to trim`;
  };
  const setTrim = (first, last) => {
    start.value = first; length.value = Math.max(0.001, last - first);
    start.callback?.(start.value); length.callback?.(length.value);
    node.graph?.change?.(); node.setDirtyCanvas?.(true, true); draw();
  };
  const timeAt = e => Math.max(0, Math.min(data.duration, (e.clientX - canvas.getBoundingClientRect().left) / canvas.getBoundingClientRect().width * data.duration));
  canvas.addEventListener("pointerdown", e => {
    if (!data || e.button !== 0) return;
    const [first, last] = trimRange(data.duration, start.value, length.value), time = timeAt(e);
    const threshold = data.duration * 14 / canvas.getBoundingClientRect().width;
    dragging = Math.abs(time - first) <= threshold ? "start" : Math.abs(time - last) <= threshold ? "end" : "scrub";
    canvas.setPointerCapture(e.pointerId);
    if (dragging === "scrub") player.currentTime = time;
  });
  canvas.addEventListener("pointermove", e => {
    if (!dragging || !canvas.hasPointerCapture(e.pointerId)) return;
    const [first, last] = trimRange(data.duration, start.value, length.value), time = timeAt(e);
    if (dragging === "start") setTrim(Math.min(time, last - 0.001), last);
    else if (dragging === "end") setTrim(first, Math.max(first + 0.001, time));
    else player.currentTime = time;
    draw();
  });
  canvas.addEventListener("pointerup", e => { dragging = null; if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId); });
  canvas.addEventListener("pointercancel", () => { dragging = null; });
  player.addEventListener("timeupdate", () => {
    if (!data) return;
    const [first, last] = trimRange(data.duration, start.value, length.value);
    if (!player.paused && player.currentTime >= last) { player.pause(); player.currentTime = first; }
    draw();
  });
  player.addEventListener("play", () => { if (data) { const [first, last] = trimRange(data.duration, start.value, length.value); if (player.currentTime < first || player.currentTime >= last) player.currentTime = first; } });
  onWidget(start, draw); onWidget(length, draw);
  chain(node, "onRemoved", () => { disposed = true; controller?.abort(); player.pause(); player.removeAttribute("src"); player.load(); });
  return { body, async load(name) {
    controller?.abort(); controller = new AbortController(); const current = controller;
    data = null; draw();
    if (!name) { label.textContent = "Select audio to show its waveform."; return; }
    label.textContent = "Loading waveform…";
    try {
      const response = await api.fetchApi(`/jezzwtf/audio/waveform?${new URLSearchParams({file: name})}`, { signal: current.signal });
      if (!response.ok) throw new Error(await response.text());
      const payload = await response.json();
      if (disposed || current.signal.aborted) return;
      data = payload; draw();
    } catch (error) { if (!current.signal.aborted && !disposed) label.textContent = `Waveform unavailable: ${error.message}`; }
  } };
}
